"""Fast unit tests: expression sandbox, policy engine, feature engine, explanations, RAG, grounding."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.detectors.base import Signal
from app.explain.reason_codes import CONDITIONS, render_reason, select_reasons
from app.features.engine import DAY, HOUR, FeatureEngine
from app.genai.copilot import numbers_grounded, template_narrative
from app.genai.rag import BM25Retriever
from app.policy.engine import PolicyEngine
from app.policy.expr import ExpressionError, evaluate

BACKEND = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- expressions
def test_expression_basic_and_missing_names_default_to_zero():
    assert evaluate("lgbm >= 0.5 and rules < 1", {"lgbm": 0.7, "rules": 0}) is True
    assert evaluate("graph >= 0.7", {}) is False  # missing detector => 0
    assert evaluate("min(a, b) * 2", {"a": 3, "b": 1}) == 2


@pytest.mark.parametrize("bad", ["__import__('os')", "x.__class__", "[1,2][0]", "lambda: 1", "open('f')"])
def test_expression_sandbox_rejects_unsafe_code(bad):
    with pytest.raises(ExpressionError):
        evaluate(bad, {"x": 1})


# --------------------------------------------------------------------- policy
POLICY = """
version: 7
variables: {warn_t: model, hold_t: 0.9}
tiers:
  - {action: HOLD, when: "lgbm >= hold_t or rule_hit('ATO')"}
  - {action: WARN, when: "lgbm >= warn_t"}
  - {action: ALLOW, when: "true"}
segment_overrides:
  - {name: young, when: "s_tenure_days < 30", set: {warn_t: "warn_t * 0.5"}}
"""


def test_policy_tiers_overrides_and_rule_hits(tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY, encoding="utf-8")
    eng = PolicyEngine(p)
    eng.set_model_thresholds({"warn_t": 0.4})
    assert eng.decide({"lgbm": 0.95}, set()).action == "HOLD"
    assert eng.decide({"lgbm": 0.5, "s_tenure_days": 400}, set()).action == "WARN"
    assert eng.decide({"lgbm": 0.3, "s_tenure_days": 400}, set()).action == "ALLOW"
    young = eng.decide({"lgbm": 0.3, "s_tenure_days": 5}, set())
    assert young.action == "WARN" and young.overrides_applied == ["young"]
    assert eng.decide({"lgbm": 0.0}, {"ATO"}).action == "HOLD"


def test_policy_hot_reload_and_broken_edit_keeps_previous(tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY, encoding="utf-8")
    eng = PolicyEngine(p)
    time.sleep(0.05)
    p.write_text(POLICY.replace("version: 7", "version: 8"), encoding="utf-8")
    eng.decide({"lgbm": 0.1}, set())
    assert eng.version == 8
    time.sleep(0.05)
    p.write_text("version: 9\ntiers:\n  - {action: EXPLODE, when: 'true'}\n", encoding="utf-8")
    assert eng.decide({"lgbm": 0.95}, set()).action == "HOLD"
    assert eng.version == 8


# ------------------------------------------------------------- feature engine
def _tx(ts, sender="C1", receiver="C2", amount=500.0, ttype="send_money", device="D1"):
    return {"tx_id": "t", "ts": ts, "type": ttype, "amount": amount, "sender": sender, "receiver": receiver,
            "device_id": device, "geo_cell": "DHA-01"}


def test_features_are_point_in_time_and_update_only_on_commit():
    eng = FeatureEngine()
    t0 = 1_000_000.0
    eng.register_wallet("C1", t0 - 400 * DAY, "D1")
    for i in range(10):
        eng.update(_tx(t0 + i * HOUR, amount=500))
    f = eng.compute(_tx(t0 + 11 * HOUR, receiver="C9", amount=5000))
    assert f["is_new_recipient"] == 1
    assert f["amount_ratio"] > 8
    assert f["s_out_cnt_24h"] == 10
    # compute() must not change state: scoring the same tx twice gives the same features
    assert eng.compute(_tx(t0 + 11 * HOUR, receiver="C9", amount=5000)) == f
    eng.update(_tx(t0 + 11 * HOUR, receiver="C9", amount=5000))
    assert eng.compute(_tx(t0 + 12 * HOUR, receiver="C9"))["is_new_recipient"] == 0


def test_features_device_and_security_events():
    eng = FeatureEngine()
    t0 = 2_000_000.0
    eng.register_wallet("C1", t0 - 100 * DAY, "D1")
    eng.ingest_event({"wallet": "C1", "event": "sim_swap", "ts": t0 - 2 * HOUR})
    f = eng.compute(_tx(t0, device="DNEW"))
    assert f["is_new_device"] == 1 and f["s_device_age_hrs"] == 0.0
    assert abs(f["hrs_since_sim_swap"] - 2.0) < 1e-6
    eng.update(_tx(t0, device="DNEW"))
    g = eng.compute(_tx(t0 + 600, device="DNEW"))
    assert g["is_new_device"] == 0 and g["s_device_age_hrs"] < 1


def test_receiver_fanin_counts_new_senders():
    eng = FeatureEngine()
    t0 = 3_000_000.0
    for i in range(6):
        eng.update(_tx(t0 + i * 60, sender=f"C{i + 10}", receiver="C99"))
    f = eng.compute(_tx(t0 + 3600, sender="C1", receiver="C99"))
    assert f["r_new_senders_24h"] == 6 and f["r_distinct_senders_24h"] == 6


# ---------------------------------------------------------------- explanations
def test_reason_codes_are_only_emitted_when_true():
    feats = {"is_new_recipient": 0, "amount_ratio": 1.0, "recent_device": 0}
    sig = Signal(detector="lgbm", score=0.9, details={"contributions": [
        {"feature": "is_new_recipient", "value": 0, "contribution": 2.0},
        {"feature": "amount_ratio", "value": 1.0, "contribution": 1.0}]})
    assert select_reasons(feats, {"lgbm": sig}) == []
    feats.update(is_new_recipient=1, amount_ratio=4.2)
    assert select_reasons(feats, {"lgbm": sig}) == ["R_NEW_RECIPIENT", "R_UNUSUAL_AMOUNT"]
    assert CONDITIONS["R_NEW_DEVICE"]({"recent_device": 1})


def test_bangla_rendering_uses_bangla_digits():
    text = render_reason("R_RECIPIENT_HIGH_FANIN", {"r_new_senders_24h": 37}, "bn")
    assert "৩৭" in text and "37" not in text
    assert "37" in render_reason("R_RECIPIENT_HIGH_FANIN", {"r_new_senders_24h": 37}, "en")


# ----------------------------------------------------------------- GenAI parts
def test_rag_retrieves_relevant_sop():
    hits = BM25Retriever(BACKEND / "knowledge" / "sop").search("SIM swap account takeover new device", k=2)
    assert hits and hits[0]["id"].startswith("SOP-01")


def test_grounding_rejects_invented_numbers():
    evidence = {"alert": {"amount_bdt": 2000, "risk_score": 0.91}, "key_facts": {"recipient_new_senders_24h": 37}}
    ok, _ = numbers_grounded({"summary": "2,000 BDT sent; 37 new senders; score 0.91"}, evidence)
    assert ok
    bad, ungrounded = numbers_grounded({"summary": "Customer lost 75,000 BDT"}, evidence)
    assert not bad and "75000" in ungrounded


def test_grounding_ignores_identifiers():
    """SOP / reason-code ids are not amounts: 'SOP-05' must not be read as the number 5."""
    evidence = {"alert": {"amount_bdt": 2000}}
    ok, ungrounded = numbers_grounded({"recommended_actions": ["Verify the customer (SOP-05).", "Check R_X12 and SOP-04#2."]}, evidence)
    assert ok, ungrounded


def test_template_narrative_without_llm():
    evidence = {
        "alert": {"alert_id": 1, "decision": "HOLD", "risk_score": 0.99, "transaction_type": "send_money", "amount_bdt": 9000,
                  "sender": "C1", "receiver": "C2", "time_dhaka": "2026-08-30 02:10"},
        "reasons": [{"code": "R_ATO_COMBO", "text": "SIM change + new phone + large transfer."}],
        "key_facts": {}, "sop_excerpts": [{"id": "SOP-01#1"}],
    }
    out = template_narrative(evidence)
    assert out["recommended_actions"][0].startswith("Follow the account-takeover procedure")
    assert "R_ATO_COMBO" in out["citations"]


def test_compiled_isolation_forest_matches_sklearn():
    import numpy as np
    from sklearn.ensemble import IsolationForest

    from app.detectors.anomaly import CompiledIsolationForest

    rng = np.random.default_rng(0)
    X = rng.normal(size=(3000, 6))
    model = IsolationForest(n_estimators=50, max_samples=512, random_state=0).fit(X)
    fast = CompiledIsolationForest(model)
    probe = np.vstack([X[:50], rng.normal(scale=4, size=(50, 6))])
    expected = -model.score_samples(probe)
    got = np.array([fast.score_one(row) for row in probe])
    assert np.allclose(got, expected, atol=1e-9)
