# Shurokkha demo video: script and timestamps

`Shurokkha_Demo.mp4` (1920×1080, 5:54, English voice-over, subtitles in `Shurokkha_Demo.srt`). Recorded against the local stack with the seed-42 model; all data is synthetic.

| Time | Section |
|---|---|
| 0:00 | Title |
| 0:16 | The problem |
| 0:43 | Overview page |
| 1:11 | Decision pipeline |
| 1:33 | Customer app: everyday transfer (ALLOW) |
| 1:54 | Customer app: account takeover (HOLD) |
| 2:23 | Customer app: What the AI saw |
| 2:41 | Customer app: mule cash-out (WARN, cooling-off) |
| 3:05 | Analyst console: alert queue |
| 3:17 | Analyst console: case evidence, mule graph, SHAP |
| 3:40 | Analyst console: AI case summary and labelling |
| 4:03 | SOP copilot (RAG) |
| 4:15 | Impact, lift and fairness |
| 4:50 | Admin: live policy and model registry |
| 5:11 | WARN user study |
| 5:24 | Closing |

## Narration

**0:00 · Title**

This is Shurokkha, which means protection in Bangla. It is an AI trust and financial-safety copilot for upay, built for the DIU CPC and upay AI Hackathon. Its goal is simple: stop the scam before the money leaves.

**0:16 · The problem**

For first-time mobile wallet users, prize scams, fake wrong-send refunds, SIM-swap account takeovers and money-mule networks cause losses that are almost impossible to reverse. Risk teams review alerts by hand, slowly, and with little context. Shurokkha answers three questions for every transfer, in milliseconds: what happened, why is it risky, and what should upay do next.

**0:43 · Overview page**

This is the overview page. On the right is Rahima's story. A caller tells her she won a prize and must pay a fee. Shurokkha interrupts her in plain Bangla, with specific reasons. Below are results on a held-out test window: a PR-AUC of 0.992, 96 percent of fraud caught, and only 0.21 percent of legitimate customers flagged. All data in this project is synthetic.

**1:11 · Decision pipeline**

Every decision follows the same pipeline. A transfer request, point-in-time features, four plug-in detectors: rules, an Isolation Forest, a calibrated LightGBM model and mule-graph risk. Then a YAML policy, SHAP reason codes, the action, and analyst feedback that flows back into retraining.

**1:33 · Customer app: everyday transfer (ALLOW)**

Now the customer app: a demo upay wallet, signed in as a synthetic customer. On the right are one-click scenarios. First, an everyday case: sending money to family. The backend scores it in a few milliseconds, finds nothing unusual, and the money is sent. No friction for normal customers.

**1:54 · Customer app: account takeover (HOLD)**

Next, an account takeover at night. Behind the scenes, the scenario records a SIM swap two hours ago and a PIN reset minutes ago, and the transfer comes from a new phone. Shurokkha holds the transfer and explains why, in Bangla: a SIM change, plus a new phone, plus a large amount matches an account-takeover pattern, and the receiver is linked to a cash-out ring. The customer can cancel, listen to a spoken warning, or appeal.

**2:23 · Customer app: What the AI saw**

The What the AI saw tab shows exactly what was sent to the scoring API, with the new phone and the new area highlighted. Below are every detector score, the verified reason codes, and the exact policy rule that caused the hold. The whole decision took only a few milliseconds.

**2:41 · Customer app: mule cash-out (WARN, cooling-off)**

Not every risky transfer needs a hold. Here, a garments worker's wallet receives fresh money and drains it at an agent, a typical mule cash-out. This time the decision is a warning. Instead of a simple pop-up, send anyway is locked behind a cooling-off timer, which breaks the panic that scammers create. The customer can also hear the warning spoken in Bangla.

**3:05 · Analyst console: alert queue**

Every warning and hold lands in the analyst console, ranked by calibrated risk, with customer appeals moved to the top. A start-here pointer opens the highest-risk case.

**3:17 · Analyst console: case evidence, mule graph, SHAP**

The case page brings all the evidence together: the transfer, the reasons in English and Bangla, and each detector's score. The money-flow network shows two hops around the receiver: a dense mule community draining to agent cash-out points, which no single transaction would reveal. The SHAP chart shows which features drove the score.

**3:40 · Analyst console: AI case summary and labelling**

Now the AI investigation copilot. It writes a case summary grounded only in this case's evidence and the standard operating procedures, with citations. The language model narrates; it never decides. If it is unavailable, a rule-based template is used instead. The analyst then labels the case, and that label feeds the next retraining.

**4:03 · SOP copilot (RAG)**

Analysts can also ask procedure questions. The SOP copilot retrieves the relevant procedures with BM25 search, and answers only from them, citing each source.

**4:15 · Impact, lift and fairness**

The impact page shows what this means for upay: victim loss prevented as a range with its assumptions, analyst hours saved, and a simulated return on investment. The lift table shows the AI adds real value: rules alone reach a PR-AUC of 0.17, while LightGBM with graph and anomaly features reaches 0.99. Recall is shown for every fraud scenario, and a fairness audit compares false-positive rates across division, age, KYC level, persona and tenure.

**4:50 · Admin: live policy and model registry**

The admin page lets the risk team adapt without redeploying. The decision policy is a YAML file that is validated, audited and hot-reloaded across all workers, and the model registry keeps versioned models. Visitors get a read-only view; changes need an admin password that is never shipped to the browser.

**5:11 · WARN user study**

Finally, a built-in user study measures, instead of assuming, how many people cancel a scam after a warning, comparing no warning, a generic warning, and Shurokkha's explained warning.

**5:24 · Closing**

Under the hood: FastAPI, LightGBM, scikit-learn and NetworkX on the backend, Next.js and React on the frontend, PostgreSQL and Redis for shared state, all packaged with Docker. In a bank-style load test it handled 800 concurrent users, and killing a worker mid-load lost zero transfers. Shurokkha. The AI explains, humans decide, and the scam is stopped before the money leaves.
