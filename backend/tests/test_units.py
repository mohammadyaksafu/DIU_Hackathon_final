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


# --------------------------------------------- shared online state (Redis)
def _scenario(eng: FeatureEngine, t0: float) -> None:
    eng.register_wallet("C1", t0 - 400 * DAY, "D1")
    eng.ingest_event({"wallet": "C1", "event": "password_reset", "ts": t0 - HOUR})
    for i in range(8):
        eng.update(_tx(t0 + i * HOUR, amount=400 + i))
    for i in range(4):
        eng.update(_tx(t0 + 9 * HOUR + i * 60, sender=f"C{i + 20}", receiver="C9"))


def test_redis_store_gives_identical_features_and_is_shared_by_workers():
    import fakeredis

    from app.features.store import RedisWalletStore

    server = fakeredis.FakeServer()
    worker_a, worker_b, local = FeatureEngine(), FeatureEngine(), FeatureEngine()
    worker_a.wallets = RedisWalletStore(fakeredis.FakeRedis(server=server))
    worker_b.wallets = RedisWalletStore(fakeredis.FakeRedis(server=server))
    t0 = 4_000_000.0
    _scenario(local, t0)
    _scenario(worker_a, t0)  # history written by one worker ...
    probe = _tx(t0 + 10 * HOUR, receiver="C9", amount=3000, device="DNEW")
    assert worker_b.compute(probe) == local.compute(probe)  # ... is seen exactly the same by another
    worker_b.update(probe)
    assert worker_a.compute(_tx(t0 + 11 * HOUR, receiver="C9"))["is_new_recipient"] == 0


def test_seed_copies_warm_state_once_and_keeps_live_updates():
    import fakeredis

    from app.features.store import RedisWalletStore, seed

    client = fakeredis.FakeRedis()
    warm = FeatureEngine()
    _scenario(warm, 5_000_000.0)
    assert seed(client, warm.wallets, "v1:1") is True
    shared = FeatureEngine()
    shared.wallets = RedisWalletStore(client)
    shared.update(_tx(5_000_000.0 + 20 * HOUR, receiver="C77"))
    assert seed(client, warm.wallets, "v1:1") is False  # restart: live history kept
    assert "C77" in shared.wallets["C1"].known_out
    assert seed(client, warm.wallets, "v2:1") is True  # new dataset: reseeded
    assert "C77" not in shared.wallets["C1"].known_out


def test_graph_edges_are_shared_between_workers():
    import fakeredis

    from app.features.store import SharedEdges
    from app.graph.store import GraphStore

    server = fakeredis.FakeServer()
    a, b = GraphStore(), GraphStore()
    a.shared = SharedEdges(fakeredis.FakeRedis(server=server))
    b.shared = SharedEdges(fakeredis.FakeRedis(server=server))
    a.add_edge({"ts": 1.0, "sender": "C1", "receiver": "C2", "amount": 100.0, "type": "send_money"})
    sub = b.subgraph("C2")
    assert {"C1", "C2"} <= {n["id"] for n in sub["nodes"]}
    assert len(a.edges) == len(b.edges) == 1


def test_rate_limit_is_shared_through_redis():
    import fakeredis

    from app.core.ratelimit import RateLimitMiddleware

    client = fakeredis.FakeRedis()
    w1, w2 = RateLimitMiddleware(None, per_minute=3), RateLimitMiddleware(None, per_minute=3)
    results = [w._allow_redis(client, "1.2.3.4") for w in (w1, w2, w1, w2)]
    assert results == [True, True, True, False]


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


# ----------------------------------------------------------------- migrations
def _schema_diff(conn):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.database import Base

    return compare_metadata(MigrationContext.configure(conn), Base.metadata)


def test_migrations_build_the_same_schema_as_the_models(tmp_path):
    from sqlalchemy import create_engine

    from app.db.database import migrate

    engine = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    with engine.begin() as conn:
        migrate(conn)
        assert _schema_diff(conn) == []  # a model change without a migration fails here
    engine.dispose()


def test_migrations_adopt_a_database_created_before_alembic(tmp_path):
    from sqlalchemy import create_engine, text

    from app.db.database import Base, migrate

    from alembic import command
    from alembic.config import Config

    from app.core.config import BACKEND_DIR

    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as conn:
        # A database from before Alembic: the original schema (revision 0001), no version table.
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
        conn.execute(text("DROP TABLE alembic_version"))
        conn.execute(text("INSERT INTO feedback (alert_id, analyst, label, notes, created_at) VALUES (1, 'a', 'fraud', '', 0)"))
        migrate(conn)
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
        assert conn.execute(text("SELECT count(*) FROM study_responses")).scalar() == 0  # later migrations applied
        assert conn.execute(text("SELECT count(*) FROM feedback")).scalar() == 1  # data kept
    engine.dispose()


# ------------------------------------------------------------ new detectors / policy modes
def test_agent_cashout_detector_flags_fresh_drain_with_agent_velocity():
    from app.detectors.agent_cashout import agent_cashout_risk

    f = {"type_code": 1, "s_mins_since_inflow": 15, "s_inflow_ratio_24h": 0.97, "s_new_sender_inflow_1h": 1,
         "s_tenure_days": 400, "a_new_customers_1h": 4, "a_cashout_rate_ratio": 6}
    score, parts = agent_cashout_risk(f)
    assert score >= 0.8 and parts["agent_velocity"] == 1.0
    assert agent_cashout_risk({**f, "type_code": 0})[0] == 0.0
    assert agent_cashout_risk({**f, "s_merchant_profile": 1})[0] < score  # shops cash out takings daily


def test_graph_risk_is_merchant_aware():
    from app.detectors.graph import graph_risk

    f = {"type_code": 0, "r_g_comm_fanin": 4.0, "r_new_senders_24h": 10, "r_tenure_days": 20}
    assert graph_risk({**f, "r_merchant_profile": 1})[0] < graph_risk(f)[0]


@pytest.mark.parametrize("mode,hold,warn", [("enforce", "HOLD", "WARN"), ("warn", "WARN", "WARN"), ("shadow", "ALLOW", "ALLOW")])
def test_policy_rollout_modes(tmp_path, mode, hold, warn):
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY + f"\nmode: {mode}\n", encoding="utf-8")
    eng = PolicyEngine(p)
    assert eng.apply_mode("HOLD") == hold and eng.apply_mode("WARN") == warn and eng.apply_mode("ALLOW") == "ALLOW"


def test_policy_rejects_unknown_mode(tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY + "\nmode: yolo\n", encoding="utf-8")
    with pytest.raises(ValueError):
        PolicyEngine(p)


def test_psi_is_zero_for_same_distribution_and_large_for_shift():
    import numpy as np

    from app.services.drift import psi

    e = np.array([0.25, 0.25, 0.25, 0.25])
    assert psi(e, e) < 1e-9
    assert psi(e, np.array([0.7, 0.1, 0.1, 0.1])) > 0.25


def test_wilson_interval():
    from app.api.v1.study import wilson

    lo, hi = wilson(45, 60)
    assert lo < 0.75 < hi and wilson(0, 0) is None
