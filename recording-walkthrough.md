# Three-Minute Recording Walkthrough

**Target duration:** 2:30–2:50. Record the real dashboard and prompt files; no slides. The script is intentionally concise so it can be delivered naturally.

## 0:00–0:25 | Start with the finding

Show the Executive Summary.

“Finance's raw export sums to ₹230 million, but the export mixes legacy-native amounts and migration duplicates. After retaining one row per ticket and converting legacy values based on 125 matched duplicate pairs, the data contains ₹6.71 million across 2,340 refund tickets for 18 months. That is about ₹11.18 lakh per observed quarter.”

## 0:25–0:55 | Show the bridge

Open Reconciliation.

“There are 12,238 raw rows, 11,600 unique ticket IDs, and 638 extra rows. I retain the helpdesk version when the same ticket exists in both sources. All 125 duplicated refund pairs with amounts have a 100-to-1 legacy/current ratio. The conversion factor is an empirical inference because the policy says ‘native unit’ without naming it.”

## 0:55–1:20 | Show why, not who to blame

Open Refund Analysis, then Agent Analysis.

“GW-OTHER accounts for ₹2.91 million, but the policy describes it as Goodwill / Other, so it is not a reliable goodwill total. Agent activity is shown by team and tier without ranking people; Returns Desk is expected to process refunds, and Tier 2 is not comparable to Tier 1 by volume.”

## 1:20–2:00 | Show policy control opportunity

Open Policy Exceptions and point to refund-plus-replacement and GW-OTHER filters.

“There are 166 tickets with both flags, representing ₹871,161 in candidate refund plus replacement planning exposure. This is not confirmed loss: eight lack an order ID, and there is no payment or shipment ledger. A proposed 25% reduction targets about 125 flags, equivalent to about ₹36,298 per quarter in candidate exposure, subject to verification.”

## 2:00–2:35 | Show prompts and explain iteration

Open `prompts/refund_reason_v1.txt`, then `prompts/refund_reason_v2.txt`, then the AI Review tab.

“Version 1 asks whether text supports the dropdown reason. Version 2 defines the four outcomes, treats GW-OTHER as a catch-all, forbids inferring from product names or amounts, and tells the reviewer to preserve ambiguity. The local reviewer is a deterministic heuristic. Gemini is optional and only runs when I request one ticket. The sample's provisional labels were created during rule tuning, so the 30-out-of-30 agreement is not independent accuracy; true human error rate is unknown.”

## 2:35–2:50 | Say what was discarded

“I discarded the reference project's hard-coded totals and pre-labeled benchmark, amount/date guesses for missing orders, batch LLM review, and automatic accusations of leakage. The next step is a fresh human-adjudicated holdout and Finance's payment, shipment, approval, and SLA-credit records.”

## Recording checklist

- Keep the whole recording under three minutes.
- Use the live dashboard at `http://localhost:8501` and show the two prompt files on screen.
- Do not display an API key, customer personal details beyond what is essential, or a private browser/profile.
- Upload the recording to an approved public or assessor-accessible location, then paste the actual URL in `submission-form.md`.
- Do not claim the local heuristic is a trained AI model or describe 30/30 self-agreement as accuracy.
