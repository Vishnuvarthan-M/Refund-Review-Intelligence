# Data Audit and Reconciliation

Generated from the supplied CSVs by `python run_audit.py`. Source data is not modified.

## Data Profile

- Ticket dates: 2025-01-01 09:17:00 through 2026-06-30 23:14:00.
- Exact full-row duplicates: 0.
- Ticket ID groups with repeated records: 638; extra rows removed: 638.
- Source rows: 12,238; canonical unique ticket IDs: 11,600.

| table | rows | columns | null_cells_pct |
| --- | --- | --- | --- |
| tickets | 12238 | 21 | 12.07 |
| agents | 44 | 8 | 12.5 |
| orders | 15000 | 8 | 0.0 |
| products | 14 | 7 | 0.0 |
| customers | 9500 | 6 | 0.0 |

Raw source split:

| source system | Raw rows |
| --- | --- |
| helpdesk | 8364 |
| legacy_fd | 3874 |

Canonical source split after retaining the current helpdesk row for duplicate IDs:

| source system | Canonical rows |
| --- | --- |
| helpdesk | 8364 |
| legacy_fd | 3236 |

## Refund Reconciliation

| Stage | Refund tickets | Amount |
|---|---:|---:|
| Raw export, mixed units and duplicates | 2,465 | ₹230,124,081.00 |
| After canonical deduplication, before conversion | 2,340 | ₹194,022,981.00 |
| Normalized INR | 2,340 | ₹6,709,932.00 |

Canonical legacy values total ₹189,205,100.00 before conversion and ₹1,892,051.00 after division by 100. 125 of 125 duplicate pairs with two recorded amounts show the same ×100 relationship. 0 duplicate ID groups conflict on fields other than source system and refund amount.

The normalized amount averages ₹1,118,322.00 per observed quarter across 6 quarters. This is a dataset-derived average, not a forecast.

| metric | expected | actual | passed |
| --- | --- | --- | --- |
| Raw rows reconcile to retained plus removed | 12238 | 12238 | True |
| Retained IDs are unique | 11600 | 11600 | True |
| Unique ticket count reconciles | 11600 | 11600 | True |
| Refund count reconciles | 2340 | 2340 | True |
| Normalized total reconciles | 6709932.0 | 6709932.0 | True |
| Raw refund sum is finite | finite | 230124081.0 | True |
| Normalized refund amounts are non-negative | True | True | True |
| Duplicate source pairs are consistent | True | True | True |

## Monthly Refunds

| month | Refund tickets | Refund INR |
| --- | --- | --- |
| 2025-01 | 58 | ₹141,048.00 |
| 2025-02 | 63 | ₹177,938.00 |
| 2025-03 | 91 | ₹290,597.00 |
| 2025-04 | 79 | ₹250,089.00 |
| 2025-05 | 86 | ₹217,464.00 |
| 2025-06 | 88 | ₹259,869.00 |
| 2025-07 | 119 | ₹356,986.00 |
| 2025-08 | 125 | ₹367,821.00 |
| 2025-09 | 161 | ₹482,284.00 |
| 2025-10 | 185 | ₹575,637.00 |
| 2025-11 | 186 | ₹575,984.00 |
| 2025-12 | 171 | ₹475,954.00 |
| 2026-01 | 153 | ₹449,868.00 |
| 2026-02 | 139 | ₹372,797.00 |
| 2026-03 | 163 | ₹435,773.00 |
| 2026-04 | 154 | ₹402,265.00 |
| 2026-05 | 149 | ₹426,737.00 |
| 2026-06 | 170 | ₹450,821.00 |

## Refund Reasons

| Reason code | Tickets | Refund INR | Average INR | Value share % |
| --- | --- | --- | --- | --- |
| GW-OTHER | 991 | ₹2,907,036.00 | ₹2,933.44 | 43.32% |
| RETURN-QC-OK | 452 | ₹1,181,386.00 | ₹2,613.69 | 17.61% |
| DUP-PAYMENT | 321 | ₹884,586.00 | ₹2,755.72 | 13.18% |
| CANCEL | 222 | ₹612,950.00 | ₹2,761.04 | 9.13% |
| DOA-REPL | 147 | ₹471,190.00 | ₹3,205.37 | 7.02% |
| WTY-BUYBACK | 89 | ₹289,154.00 | ₹3,248.92 | 4.31% |
| PRICE-ADJ | 71 | ₹207,073.00 | ₹2,916.52 | 3.09% |
| LOST-TRANSIT | 47 | ₹156,557.00 | ₹3,331.00 | 2.33% |

## Policy Signals

- Refund plus replacement recorded: 166 tickets.
- Refund component: ₹574,191.00.
- Replacement planning cost (unit cost + ₹340): ₹296,970.00.
- Combined candidate exposure: ₹871,161.00. This is not proven loss; fulfillment and payment settlement are not supplied.
- Missing order ID among those flags: 8.
- GW-OTHER refunds above ₹500: 879; this combined code does not prove the item was goodwill or that approval was absent.
- First-response SLA breaches: 1,060 total, including 998 resolved/closed and 62 still open/pending. Policy-derived credit value for resolved/closed cases: ₹349,300.00. Credit transactions are not included, so issuance is not independently verified.
- Refund records with missing reason code: 0; unsupported code values: 0.

## Unresolved Items and Assumptions

- Duplicate IDs retain `helpdesk` over `legacy_fd`; non-duplicate legacy rows remain in analysis.
- Legacy `refund_amount_inr` is divided by 100 based on the cross-system duplicate-pair evidence above and the policy's distinction between legacy native units and current rupees. The PDF does not name the legacy unit.
- Missing order IDs are filled only when customer ID plus SKU identifies exactly one order. No amount/date guessing is used. Remaining records without an order-value match: 707; unresolved order IDs: 707.
- Unmapped resolving agents: 0; invalid creation timestamps: 0.
- A refund plus replacement flag is a potential policy exception, not proof that both benefits reached the customer. Approval and fulfillment logs were not supplied.
- GW-OTHER is a combined Goodwill / Other code. Amounts above ₹500 are review candidates; a specific goodwill decision and Team Lead approval are not encoded in these files.
- SLA credit amounts are policy-derived estimates based on first response and channel target, not confirmed credits in the supplied tables.
