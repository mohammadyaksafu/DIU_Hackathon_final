# Governance, privacy and security (one page)

## Decisions and human oversight
- **The AI explains; people decide.** No permanent automated block. A HOLD pauses one transfer until an analyst reviews it (SOP-05 target: 15 minutes).
- **Customer appeal.** Any WARN or HOLD shows "Not a scam? Appeal this decision". The case jumps the analyst queue with an SLA badge; a `legit` label releases a held transfer automatically and is stored as a feedback label for retraining (`POST /transactions/{id}/appeal`).
- **Rollout modes** in `config/policy.yaml`: `shadow` (decide and log, customer always sees ALLOW) → `warn` (WARN-only pilot) → `enforce`. Changing mode is an audited admin action.
- **Model promotion needs a person.** New versions are written to the registry; only an admin activates one (audit-logged), after reviewing the model card, fairness report and evaluation pack.

## Access control
| Role | Can | Cannot |
|---|---|---|
| customer | score own transfers, confirm/cancel, appeal, take part in the user study | see other customers, alerts |
| analyst | alert queue, case evidence, AI summaries, labels, drift and impact pages | change policy or model |
| admin | activate models, edit the live policy (validated, hot-reloaded) | — every action is audit-logged |

JWT roles; the admin password is never shipped to the browser; production disables admin when `ADMIN_PASSWORD` is unset. Production path: SSO with a separate supervisor role for policy approval (four-eyes).

## Audit
Append-only `audit_log`: every decision (shown decision, policy decision, mode, model and policy version, reasons), every customer action, appeal, analyst label, status change, policy edit and model activation.

## Privacy and data handling
- Prototype data is 100% synthetic (`docs/DATA_ASSUMPTIONS.md` is the datasheet).
- The LLM sees pseudonymous wallet ids and case facts only, never names, phones or NIDs; untrusted text is fenced in `<untrusted_data>`; numeric grounding check; deterministic fallback; prompts and outputs are cached by evidence hash for review.
- Production requirements: TLS in transit (Caddy), encryption at rest for the database volume, retention limits on feature history (the online state keeps 7 days per wallet; graph 14 days), data minimisation in logs (no PII in JSON logs).
- Align with Bangladesh Bank MFS regulations and the national data-protection framework. **Verify the current legal status of the data-protection ordinance before relying on it**; this document does not assert it.

## Fairness
Segment report each retrain: FPR, FNR, warning rate and calibration per division, age band, KYC level, persona and tenure (`reports/evaluation.md §8`). Constraint: equalise false-positive burden **without lowering recall for high-risk groups**. Merchant-aware features reduce false alarms for registered shops and sellers; transfers by anyone to a *new* person keep full protection. **Segment-specific thresholds ship in shadow:** the `merchant_sender` override is evaluated and logged on every decision (`merchant_sender (shadow)` in the decision trace) but not applied until it is validated on independently governed data.

## Drift and retraining
`GET /metrics/drift`: PSI of key live features against the training window (shared across workers via Redis). PSI > 0.25 recommends retraining; the retrained model goes through the evaluation pack and a human sign-off before activation.

## Security threats addressed
| Threat | Mitigation |
|---|---|
| Fraudsters probing thresholds | Per-IP rate limit (shared in Redis); scores are not shown to customers, only plain-language reasons; policy can add randomised review; adversarial rounds in the evaluation pack |
| Prompt injection via memo / chat | Memo never interpreted; untrusted fencing; output schema + grounding check |
| Policy tampering | Sandboxed expression evaluator (no attribute access or builtins), validation before swap, audit log, admin-only |
| Replay / double submit | Idempotency key claimed across workers before scoring; PENDING → SENT/CANCELLED by a conditional update, so one transfer cannot be both sent and cancelled |
| Outage of a dependency | Detector failure → treated as 0, others decide; scoring failure → `on_scoring_error` policy (WARN by default, fail-safe without blocking) |
| Secrets | Environment only; gitleaks in CI; `pip-audit` and `npm audit` |
