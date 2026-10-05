# Vireo Audio Refund Review

A small Python and Streamlit tool for reconciling the supplied support export, summarizing refunds, and surfacing policy signals for human review. All financial totals, counts, date buckets, and policy thresholds are deterministic calculations over the local CSV files. The optional language-model call only assesses whether ticket text supports its structured refund reason; it never calculates money.

## 1. Problem

Finance's raw export shows a much larger refund total than the helpdesk's approximate quarterly report. The export mixes current helpdesk rows with a Freshdesk legacy source, includes migration re-imports, and contains refund reason and replacement fields that need policy context.

## 2. Business Objective

Establish a traceable INR refund baseline, explain the finance/helpdesk difference, describe refund reasons and resolving-agent workload without misleading rankings, and prioritize records that may represent preventable policy leakage.

## 3. Architecture

- `src/pipeline.py`: CSV loading, duplicate resolution, legacy money normalization, joins, date fields, and policy input flags.
- `src/analytics.py`: reconciliation KPIs, monthly and quarterly totals, reason mix, agent summaries, and team/tier comparisons.
- `src/policy_checks.py`: review ledger for refund-plus-replacement, high `GW-OTHER`, reason-code integrity, and SLA credit estimates.
- `src/ai_review.py`: local evidence-rule reviewer and optional single-ticket Gemini API call.
- `prompts/refund_reason_v1.txt` and `prompts/refund_reason_v2.txt`: versioned model prompts.
- `app.py`: Streamlit dashboard.
- `run_audit.py`: reproducibly generates `DATA_AUDIT.md`.
- `run_validation.py`: reports agreement with the fixed provisional-reference calibration sample and generates `VALIDATION_REPORT.md` and `validation-results.csv`.
- `memo-to-arjun.md`: one-page non-technical finance memo.
- `recording-walkthrough.md`: timed outline for the required screen recording.

## 4. Data Pipeline

The pipeline reads `tickets.csv`, `agents.csv`, `orders.csv`, `products.csv`, and `customers.csv` without changing them. It converts dates, enriches the canonical ticket table with roster, product, customer, and order fields, then computes monthly and quarterly buckets. Missing order IDs are filled only when `customer_id + product_sku` identifies exactly one order; it does not guess from refund amount or date. Ambiguous or unmatched order relationships remain unresolved.

To reproduce the data profile and reconciliation report:

```powershell
python run_audit.py
```

## 5. Reconciliation Approach

Raw figures are recomputed at run time. For repeated ticket IDs, the current `helpdesk` row is retained ahead of `legacy_fd`; unique legacy rows are retained. For legacy records, `refund_amount_inr` is divided by 100. The support policy says legacy money uses its own native unit but does not name the unit; the factor is evidenced by the duplicate pairs: all 125 pairs with refunds in both systems have a 100:1 amount ratio.

Local data results:

- 12,238 raw ticket rows; 11,600 unique IDs; 638 extra rows removed.
- Raw mixed-unit refund sum: ₹230,124,081 across 2,465 refund rows.
- After duplicate resolution but before legacy conversion: ₹194,022,981 across 2,340 refunds.
- Normalized INR refund total: ₹6,709,932 across 2,340 tickets.
- Six observed quarters average ₹1,118,322 per quarter.
- The quarterly average is arithmetic over the observed window, not a forecast.

The difference between raw and normalized totals is due to mixed legacy units and duplicates. The bridge is generated from input data; no reference-repository total is embedded in application logic.

## 6. AI Approach

The offline reviewer is a transparent keyword/evidence heuristic, not a trained classifier or an LLM. It compares the structured reason code against text evidence and returns `supported`, `probably_supported`, `unsupported`, or `ambiguous`. It assigns low-confidence/ambiguous outcomes when evidence is missing or competing. Rules can miss spelling variation, context, and negation, so outputs are for triage only.

Prompt v1 requests a four-way text-support label. Prompt v2 adds definitions for each label, explicitly treats `GW-OTHER` as a catch-all rather than proof of goodwill, prohibits product-name inference and money calculations, and asks the model to preserve uncertainty. Gemini is optional, requires a user-supplied API key, and is called only when the user selects a ticket and presses the review button. The key is not stored in project files.

## 7. Validation

A reproducible uniform sample of 30 refund tickets is selected without replacement with seed `20261005`. Provisional reference labels were assigned by GitHub Copilot while inspecting the sample and compared using exact four-way label agreement. The current report records 30/30 apparent agreement, but those references are not independent human labels and the sample was consulted while iterating the rules. This is self-agreement on calibration data, not human validation or a valid accuracy/error estimate. True human error rate is unknown; a fresh holdout sample and independent reviewer are required before operational use.

```powershell
python run_validation.py
```

Provisional reference labels and disagreement categories are kept in `validation_labels.csv` and summarized by the script. The small calibration set includes wording ambiguity, sparse notes, and multi-cause tickets; ambiguous cases should stay in human review. The labels are not independent human annotations and must not be used to claim measured accuracy.

## 8. Known Limitations

- The input does not include actual payments, refund settlement, replacement shipment, team-lead approval, or SLA-credit transaction ledgers. Policy flags and amounts are candidates for review, not proof of paid loss or misconduct.
- `GW-OTHER` combines Goodwill and Other. Above-₹500 records are review candidates, not confirmed cap breaches.
- 166 canonical refund tickets also have `replacement_issued=Y`. Eight lack an order ID. The recorded refund component is ₹574,191; replacement planning cost is ₹296,970; combined candidate exposure is ₹871,161 over 18 months. This is not verified realized loss.
- There are 707 canonical tickets with unresolved order enrichment; agent roster links and creation timestamps are complete.
- The PDF does not explicitly say the legacy unit is paise. The 100x conversion is an empirical inference from all available duplicate refund pairs.
- Refund reasons are operational descriptions, not causal proof. Agent outputs are descriptive and should be compared within team/tier and volume context. Returns Desk processes refunds by design; Tier 2 is not a Tier 1 volume peer.
- The policy implies 1,060 first-response misses, of which 998 tickets are resolved/closed. At ₹350 each, the policy-derived credit amount for resolved/closed cases is ₹349,300; actual issuance is not in the data.
- The LLM prompt files are versioned, but no paid LLM validation or production monitoring is included.

## 9. Installation

Use Python 3.10 or newer. From the project directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 10. Running the Application

```powershell
streamlit run app.py
```

Open the local URL printed by Streamlit. The app works without an API key.

## 11. Running Tests

```powershell
pytest
```

Tests cover duplicate resolution, legacy conversion, reconciliation arithmetic, refund-plus-replacement detection, the goodwill amount threshold, monthly aggregation, and selected text-review regressions.

## 12. Business Outcome

A measurable initial leakage-control baseline is the 166 tickets with both a positive refund and a replacement flag, with ₹871,161 in combined refund-plus-replacement planning exposure over 18 months. A proposed 25% reduction would target approximately 125 flagged tickets and represents about ₹36,298 per quarter in candidate exposure avoided, using six observed quarters. This is an operational target, not booked savings; order fulfillment/payment evidence is needed to confirm preventability and recoverability.

## Submission Materials

See [DATA_AUDIT.md](DATA_AUDIT.md), [VALIDATION_REPORT.md](VALIDATION_REPORT.md), [memo-to-arjun.md](memo-to-arjun.md), [recording-walkthrough.md](recording-walkthrough.md), and [submission-form.md](submission-form.md). The assessment data files remain unchanged.
