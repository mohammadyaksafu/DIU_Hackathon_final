# Description / Abstract

**Shurokkha (সুরক্ষা): AI Trust & Financial-Safety Copilot for upay**

## Short description

Shurokkha is a real-time AI copilot that stops mobile-money scams before the money leaves the wallet. It scores every transfer in milliseconds, warns the customer in plain Bangla, uncovers money-mule rings in the transaction graph, and gives fraud analysts an AI case summary grounded only in evidence.

## Abstract

First-time and low-digital-literacy mobile financial service (MFS) users in Bangladesh, such as remittance receivers and garment workers, are the main targets of social-engineering scams ("you won a prize, pay the fee", "wrong send, please refund"), account takeovers after SIM swaps, and money-mule networks that cash out stolen funds within minutes. Once a transfer completes, the loss is effectively permanent. Risk teams, meanwhile, review alerts manually, slowly, and with little context.

Shurokkha intervenes *before* the money moves and answers three questions for every transfer: **What happened? Why is it risky? What should upay do next?** A single point-in-time feature engine, shared by training and live serving, computes 46 behavioural, device, SIM-swap and transaction-graph features. Four plug-in detectors produce risk signals: deterministic rules, an Isolation Forest anomaly score, a calibrated LightGBM model, and a mule-network graph score based on Louvain communities and PageRank. A transparent, hot-reloadable YAML policy turns these signals into **ALLOW**, **WARN** or **HOLD**. Exact TreeSHAP contributions become reason codes, which are shown only when their factual condition is true, in Bangla and English. A WARN interrupts the customer with a plain-language scam warning before the payment is sent. A HOLD goes to a human analyst, who sees a ranked queue, the mule-ring network, SHAP drivers, and a generative-AI case summary. That summary is grounded only in the case evidence and retrieved standard operating procedures (SOPs), and it falls back to deterministic templates if the AI is unavailable. The AI explains; it never decides.

On a held-out 10-day test window of 22,126 synthetic transactions, Shurokkha reaches a **PR-AUC of 0.995** and **99.5% recall at 1% false-positive rate**, compared with 0.166 PR-AUC for rules alone. Through the real decision policy, the full system achieves **96.2% recall at 91.7% precision** with a **0.24% false-positive rate**, and HOLD precision is 98.2%. It flags **94.3% of victim-loss value** before completion, with about 5 ms server-side scoring latency. A fairness audit, human review for every HOLD, and fully synthetic data keep the system responsible. A Dockerised FastAPI and Next.js deployment, with plug-in detectors and live policy editing, makes it ready to integrate as a pre-authorisation hook in upay's payment flow.

**Keywords:** fraud detection, scam prevention, mobile financial services, LightGBM, graph analytics, explainable AI, SHAP, generative AI, Bangla, human-in-the-loop
