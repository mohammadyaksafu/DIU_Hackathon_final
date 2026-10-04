"""Evaluate the AI case summaries for groundedness, citation accuracy and decision consistency.

Runs against a live API (so it tests exactly what analysts see) and writes reports/genai_eval.md.
Checks per summary:
  - grounded      every number in the text appears in the evidence (the same rule the API enforces)
  - citations     every cited id is a reason code of the alert or a retrieved SOP chunk
  - consistent    the summary states the alert's real decision and never a different one
  - actionable    at least one recommended action references an SOP (SOP-0x)
It also runs an adversarial check: a fabricated narrative with invented numbers must be rejected
by the grounding guard.

Usage:  python -m pipelines.genai_eval --api http://127.0.0.1:8000 --n 20 [--password demo123]
With an LLM key configured the summaries come from Gemini/Claude; without one, from the template
fallback (the report says which).
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

from app.genai.copilot import numbers_grounded

BACKEND = Path(__file__).resolve().parents[1]
DECISIONS = ("ALLOW", "WARN", "HOLD")


def _call(api: str, path: str, token: str | None = None, body: dict | None = None, method: str | None = None) -> dict:
    req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def check(summary: dict, alert: dict) -> dict:
    ev = summary["evidence"]
    narrative = {k: summary.get(k) for k in ("summary", "what_happened", "why_risky", "recommended_actions")}
    grounded, ungrounded = numbers_grounded(narrative, ev)
    allowed = {r["code"] for r in ev.get("reasons", [])} | {c["id"] for c in ev.get("sop_excerpts", [])} | {"lgbm"}
    cited = list(summary.get("citations") or [])
    bad_cites = [c for c in cited if c not in allowed]
    text = json.dumps(narrative, ensure_ascii=False)
    stated = {d for d in DECISIONS if re.search(rf"\b{d}\b", text)}
    consistent = alert["decision"] in stated and not (stated - {alert["decision"]})
    actionable = any(re.search(r"SOP-\d+", a) for a in summary.get("recommended_actions") or [])
    return {"id": alert["id"], "decision": alert["decision"], "source": summary.get("source"),
            "grounded": grounded, "ungrounded": ungrounded, "citations_ok": not bad_cites, "bad_citations": bad_cites,
            "consistent": consistent, "actionable": actionable}


def adversarial(evidence: dict) -> bool:
    """A narrative with invented amounts must fail the grounding check."""
    fake = {"summary": "HOLD on 987,654 BDT sent to 4,321 wallets in 77 minutes.", "what_happened": "x",
            "why_risky": [{"point": "risk 0.9999", "evidence": []}], "recommended_actions": []}
    ok, _ = numbers_grounded(fake, evidence)
    return not ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--password", default="demo123")
    args = ap.parse_args()
    base = args.api.rstrip("/") + "/api/v1"
    tok = _call(base, "/auth/login", body={"username": "analyst", "password": args.password})["access_token"]
    items = []
    for decision in ("HOLD", "WARN"):  # a balanced sample of both flagged decisions
        items += _call(base, f"/alerts?size={args.n // 2}&sort=risk&decision={decision}&status=", tok)["items"]
    rows, last_ev = [], None
    for a in items:
        s = _call(base, f"/copilot/case-summary/{a['id']}?refresh=true", tok, body={})
        last_ev = s["evidence"]
        rows.append(check(s, a))
    n = len(rows)
    rate = lambda k: sum(r[k] for r in rows) / n if n else 0.0
    sources = Counter(r["source"] for r in rows)
    out = {"n": n, "sources": dict(sources), "grounded": rate("grounded"), "citations_ok": rate("citations_ok"),
           "consistent": rate("consistent"), "actionable": rate("actionable"),
           "adversarial_rejected": adversarial(last_ev) if last_ev else None, "rows": rows}
    reports = BACKEND / "reports"
    (reports / "genai_eval.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["# GenAI case-summary evaluation", "",
          f"{n} alerts ({sum(r['decision'] == 'HOLD' for r in rows)} HOLD, {sum(r['decision'] == 'WARN' for r in rows)} WARN), "
          f"summary source: {', '.join(f'{k} {v}' for k, v in sources.items())}.", "",
          "| Check | Pass rate |", "|---|---|",
          f"| Every number grounded in the evidence | {out['grounded']:.0%} |",
          f"| Every citation is a real reason code or retrieved SOP | {out['citations_ok']:.0%} |",
          f"| States the alert's real decision, never another | {out['consistent']:.0%} |",
          f"| Recommends at least one SOP-referenced action | {out['actionable']:.0%} |",
          f"| Fabricated numbers are rejected by the guard | {'yes' if out['adversarial_rejected'] else 'NO'} |", "",
          "Failures:" if any(not (r['grounded'] and r['citations_ok'] and r['consistent']) for r in rows) else "No failures.", ""]
    for r in rows:
        if not (r["grounded"] and r["citations_ok"] and r["consistent"]):
            md.append(f"- #{r['id']} {r['decision']}: ungrounded={r['ungrounded']} bad_citations={r['bad_citations']} consistent={r['consistent']}")
    (reports / "genai_eval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
