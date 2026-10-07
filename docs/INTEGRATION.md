# Integration contract: where Shurokkha sits in the upay send-money flow

OpenAPI spec: `GET /openapi.json` (interactive at `/docs`).

```
Customer app        upay core (wallet ledger)            Shurokkha API                    Analyst console
     │  send ৳X to Y        │                                   │                                 │
     │─────────────────────>│  POST /api/v1/score  (≤150 ms budget, Idempotency-Key = upay txn id)
     │                      │──────────────────────────────────>│ features → detectors → policy    │
     │                      │<──────────────────────────────────│ ALLOW | WARN | HOLD + reasons    │
     │                      │                                   │──── WARN/HOLD alert ───────────>│
     │   ALLOW: post ledger │                                   │                                 │
     │   WARN: show Bangla warning; customer cancels or sends   │                                 │
     │   HOLD: transfer paused; customer may appeal             │                                 │
     │                      │  POST /transactions/{id}/confirm  {sent|cancelled}                  │
     │                      │──────────────────────────────────>│ only "sent" becomes history     │
     │                      │                                   │<── analyst label (legit releases HOLD)
     │                      │  POST /events  (SIM swap, PIN reset from telco / auth)              │
     │                      │──────────────────────────────────>│                                 │
```

**Timeout rule.** upay calls `/score` synchronously with a timeout (recommended 300 ms). If the call times out, upay applies its own fallback (recommended: allow and log, as in `shadow` mode). Inside Shurokkha, a failed detector is treated as 0, and a scoring failure returns the `on_scoring_error` decision from the policy (`WARN` by default).

## Sample request
```json
POST /api/v1/score
Idempotency-Key: UPAY-20261007-000123
{
  "tx_id": "UPAY-20261007-000123",
  "type": "send_money",
  "amount": 2000,
  "sender": "C00002",
  "receiver": "C90900",
  "device_id": "DC00002-0",
  "geo_cell": "DHA-04",
  "channel": "app",
  "on_call": true
}
```

## Sample response (abridged)
```json
{
  "transaction_id": "UPAY-20261007-000123",
  "decision": "WARN",
  "policy_decision": "WARN",
  "mode": "enforce",
  "risk_score": 0.081,
  "reason_codes": ["R_ON_CALL", "R_NEW_RECIPIENT", "R_RECIPIENT_HIGH_FANIN"],
  "customer_message": {"bn": {"title": "একটু থামুন, এটি প্রতারণা হতে পারে", "reasons": ["..."], "body": "..."}, "en": {"...": "..."}},
  "model_version": "lgbm-…",
  "policy_version": 4,
  "latency_ms": 5.2,
  "degraded": false,
  "alert_id": 812
}
```

## Guarantees
| Concern | How |
|---|---|
| Retries | Same `Idempotency-Key` or `tx_id` → the stored decision is replayed (`idempotent_replay: true`); the key is claimed across workers before scoring |
| Ordering per wallet | Wallet state is updated under a per-wallet Redis lock, in the order transfers are confirmed; production path: Kafka partitioned by wallet id |
| Consistency | PENDING → SENT/CANCELLED by one conditional update; a held transfer cannot be sent until an analyst releases it |
| Model version | Each request pins one model + detector set; the version is in the response and the audit log |
| Rollout | `mode: shadow → warn → enforce` in the policy, hot-reloaded, no redeploy |
