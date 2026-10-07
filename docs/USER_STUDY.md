# WARN user study: protocol

**Question.** How many people cancel a scam transfer after a warning, and how many still complete genuine payments? Today the impact model *assumes* 60% of warned victims cancel. This study *measures* it.

**Status.** The study tool is built into the app (`/study`) and stores results in the database (`study_responses`). **No participants have been run yet**; results will appear on the study page and the Impact page as soon as they are collected. Nothing in the project reports a measured cancel rate until then.

## Design
- **Arms (between subjects, balanced assignment):** A no warning · B generic warning ("verify before sending to a stranger") · C Shurokkha explained Bangla warning (specific reasons).
- **Tasks:** 6 scripted transfers in Bangla, in the same order: 3 scams (prize fee, wrong-send refund, "account will be blocked") and 3 genuine (rent to mother, shop payment, first purchase from a recommended online seller, which also gets a mild warning in arm C, so friction is measured too).
- **Measures:** scam-cancel rate (primary), genuine-continue rate (friction), time to decide, trust in the warning (1–5).
- **Sample:** 60+ participants (20 per arm): students, family members, shopkeepers and rickshaw drivers for realism. 20 per arm detects a 30-point difference in cancel rate (e.g. 45% vs 75%) with ~80% power.

## Ethics
- Verbal + on-screen consent (Bangla), voluntary, can stop at any time.
- Anonymous: a random code (`P` + 8 hex); no names, phone numbers or real money.
- Participants are told at the end that the scams were scripted, and given the "stop, check, call" safety advice.

## Running a session
1. Open the deployed site → **User study** on a phone. Hand it to the participant after consent.
2. The app assigns the arm, shows the six transfers and records each decision and time, then asks the trust question.
3. Press **Next participant** for the next person.

## Analysis
- Per arm: proportions with 95% Wilson intervals (computed by `GET /api/v1/study/results`).
- Primary comparison: arm C vs arm A scam-cancel rate (difference in proportions with CI). Secondary: C vs B (does the explanation beat a generic pop-up?), and genuine-continue rate (friction).
- Use arm C's **lower** CI bound as `warn_heeded` in the impact and ROI model (conservative).

## Analyst workload trial (same idea, for operations)
3–5 people triage 50 seeded cases twice (with and without the AI summary, order randomised). The case page already records `opened_at` and `decided_at` per alert, so time per case and label accuracy (against the synthetic ground truth) come straight from the database.
