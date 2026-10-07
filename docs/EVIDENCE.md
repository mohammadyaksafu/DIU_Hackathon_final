# Problem evidence: why the pre-transaction moment

Every number below is labelled. **Cited** = published figure with its source. **Estimate** = our own assumption, shown so it can be challenged. Synthetic results from this prototype are in [reports/evaluation.md](reports/evaluation.md) and are never presented as real-world statistics.

## 1. Scale of MFS in Bangladesh (cited)

| Figure | Value | Source |
|---|---|---|
| Registered MFS accounts, January 2025 | 239.3 million (+9.2% year on year) | Bangladesh Bank data, reported by [The Financial Express](https://thefinancialexpress.com.bd/economy/bangladesh-mfs-accounts-surge-by-20-million-in-a-year-transactions-up-32pc) |
| MFS transaction value, January 2025 | Tk 1.72 trillion in one month (+32.6% year on year) | Same |
| MFS transaction value, mid-2025 | Tk 1.46–1.51 trillion per month (June–August 2025) | Bangladesh Bank data, reported by [The Financial Express](https://thefinancialexpress.com.bd/economy/bangladesh/mfs-transactions-rebound-in-aug) |

## 2. Fraud against MFS users (cited)

| Figure | Value | Source |
|---|---|---|
| Users who experienced MFS fraud | about 1 in 10 | Policy Research Institute (PRI) national survey, 9,279 respondents + 2,000 agents, Aug–Sep 2021, reported by [Dhaka Tribune](https://www.dhakatribune.com/business/266888/1-out-of-every-10-are-victims-of-mfs-fraud) |
| Average loss per victim | more than Tk 9,000 | Same survey |
| Main fraud types | compromised PINs and impersonation scams | Same survey |
| Complaints never resolved | about one third | Same survey |
| Regional spread | Sylhet more than 3× the national average | Same survey |
| Annual losses | "over Tk 1,200 crore" per year; only 7.6% of victims report | Letter in [The Financial Express](https://today.thefinancialexpress.com.bd/print/mfs-fraud-a-growing-threat-1751901200), July 2025. **Source not attributed in the article: treat as an unverified estimate.** |

**What upay should add before a pilot:** its own governed figures for scam losses by type, ATO cases after SIM replacement, mule-account closures and analyst workload. The prototype reads these as configuration (cost function, thresholds) so they drop straight in.

## 3. Fraud type × loss × segment (priority order)

Qualitative ranking from the sources above and the upay guideline; frequencies are **estimates** until upay data replaces them.

| Fraud type | Frequency | Typical loss | Reversible after completion? | Most affected | Shurokkha control |
|---|---|---|---|---|---|
| Social engineering (prize, refund, "account blocked", OTP) | High (most reported type, PRI) | Small–medium, repeated | No | First-time users, remittance receivers, elderly | WARN with verified Bangla reasons, on-call signal, cooling-off, voice warning |
| SIM swap / account takeover | Medium | Whole balance | No | Any; higher for remittance receivers | HOLD (SIM swap + new device + large amount), human review |
| Money-mule networks | Medium (enabler of both above) | Aggregates many victims | No once cashed out | Recruited young / dormant wallets | Graph detector, live fan-in, mule-ring HOLD |
| Agent cash-out of stolen funds | Medium | Full stolen amount | No | Agents and the victims upstream | Agent cash-out detector (fresh inflow drained at an agent, agent velocity) |
| Structuring below limits | Low | Regulatory exposure | n/a | Small businesses, mules | Deterministic rule + HOLD |

The order of work follows this table: interrupt social engineering and ATO first (largest irreversible customer loss), then cut the mule and cash-out chain that makes those scams pay.

## 4. Control-point analysis: where to stop the money

| Stage | Control available | What is still recoverable | Cost of the control |
|---|---|---|---|
| Account opening | e-KYC, NID check | Nothing lost yet; cannot see the future scam | Low per account, does not stop scams on genuine accounts |
| Login / SIM change / new device | Device binding, SIM-swap feeds | Everything, but no transaction to judge yet | False alarms on genuine phone changes |
| Beneficiary add | Name confirmation | Everything | Friction on every new payee |
| **Send money (Shurokkha)** | **Real-time score + explained WARN / HOLD** | **Everything: the money has not left** | **≈ 5 ms per transfer; friction only on flagged transfers (≈ 0.2% of legitimate traffic in the prototype)** |
| Cash-out at agent | Agent cash-out detector, OTP / voice confirm | Only if this hop is stopped; previous hops already moved | Agent friction |
| After the fact | Investigation, reversal requests | Usually nothing: cashed out within minutes | Analyst time, complaints, lost trust |

The send-money step is the last point where (a) the full context exists (who, to whom, how much, which device, the recipient's network) and (b) the whole amount is still recoverable. That is why Shurokkha's main control sits there, with the agent cash-out detector as a second net.

## 5. False positives vs losses prevented

The decision thresholds are judged with one explicit cost function (see [reports/evaluation.md §2](reports/evaluation.md)):

```
Cost = missed victim loss + (1 − warn_heeded) × warned victim loss
     + missed other fraud × ৳200
     + false WARN × ৳20 + false HOLD × ৳150
     + analyst minutes × ৳8
```

Every term is an **estimate** stated in `pipelines/evaluation.py` (`COST`) and `app/api/v1/insights.py`, so upay can replace it with real figures and re-derive cost-optimal thresholds.
