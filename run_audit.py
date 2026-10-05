from pathlib import Path

import pandas as pd

from src.analytics import get_monthly_refunds, get_reason_summary
from src.pipeline import clean_and_reconcile, load_data
from src.policy_checks import get_double_dip_cases, get_gw_other_over_cap_cases, get_sla_breach_summary
from src.validation import run_reconciliation_assertions


ROOT = Path(__file__).resolve().parent


def money(value: float) -> str:
    return f"₹{value:,.2f}"


def markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(column) for column in frame.columns]
    rows = [[str(value).replace("|", "\\|").replace("\n", " ") for value in row] for row in frame.itertuples(index=False, name=None)]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def build_report() -> str:
    raw, agent_roster, orders, products, customers = load_data(str(ROOT))
    cleaned, metadata = clean_and_reconcile(raw, agent_roster, orders, products, customers)
    checks = run_reconciliation_assertions(cleaned, metadata)
    monthly = get_monthly_refunds(cleaned).rename(columns={"refund_ticket_count": "Refund tickets", "refund_amount_inr": "Refund INR"})
    reasons = get_reason_summary(cleaned).rename(
        columns={"refund_reason_code": "Reason code", "refund_ticket_count": "Tickets", "refund_amount_inr": "Refund INR", "average_refund_inr": "Average INR", "value_share_pct": "Value share %"}
    )
    double_dips = get_double_dip_cases(cleaned)
    gw_over = get_gw_other_over_cap_cases(cleaned)
    sla = get_sla_breach_summary(cleaned)
    null_summary = pd.DataFrame(
        [{"table": name, "rows": len(frame), "columns": len(frame.columns), "null_cells_pct": round(frame.isna().to_numpy().mean() * 100, 2)}
         for name, frame in zip(("tickets", "agents", "orders", "products", "customers"), (raw, agent_roster, orders, products, customers))]
    )
    source_rows = pd.Series(metadata["raw_source_counts"], name="Raw rows").rename_axis("source system").reset_index()
    canonical_sources = pd.Series(metadata["canonical_source_counts"], name="Canonical rows").rename_axis("source system").reset_index()
    checks_table = pd.DataFrame(checks["checks"])
    monthly["Refund INR"] = monthly["Refund INR"].map(money)
    reasons["Refund INR"] = reasons["Refund INR"].map(money)
    reasons["Average INR"] = reasons["Average INR"].map(money)
    reasons["Value share %"] = reasons["Value share %"].map(lambda value: f"{value:.2f}%")
    checks_table["actual"] = checks_table["actual"].map(str)
    checks_table["expected"] = checks_table["expected"].map(str)
    dates = pd.to_datetime(raw["created_at"], errors="coerce")
    refund_replacement_refund = float(double_dips["refund_amount_cleaned"].sum())
    replacement_cost = float(double_dips["replacement_cost_policy"].sum())
    candidate_total = refund_replacement_refund + replacement_cost
    return f"""# Data Audit and Reconciliation

Generated from the supplied CSVs by `python run_audit.py`. Source data is not modified.

## Data Profile

- Ticket dates: {dates.min()} through {dates.max()}.
- Exact full-row duplicates: {int(raw.duplicated().sum())}.
- Ticket ID groups with repeated records: {metadata['duplicate_ticket_ids']:,}; extra rows removed: {metadata['duplicate_rows_removed']:,}.
- Source rows: {len(raw):,}; canonical unique ticket IDs: {len(cleaned):,}.

{markdown_table(null_summary)}

Raw source split:

{markdown_table(source_rows)}

Canonical source split after retaining the current helpdesk row for duplicate IDs:

{markdown_table(canonical_sources)}

## Refund Reconciliation

| Stage | Refund tickets | Amount |
|---|---:|---:|
| Raw export, mixed units and duplicates | {metadata['raw_refund_ticket_count']:,} | {money(metadata['raw_refund_total'])} |
| After canonical deduplication, before conversion | {metadata['refund_ticket_count']:,} | {money(metadata['deduplicated_raw_refund_total'])} |
| Normalized INR | {metadata['refund_ticket_count']:,} | {money(metadata['total_refund_cleaned'])} |

Canonical legacy values total {money(metadata['legacy_raw_refund_total'])} before conversion and {money(metadata['legacy_normalized_refund_total'])} after division by 100. {metadata['duplicate_pair_ratio_100_count']:,} of {metadata['duplicate_pair_refund_count']:,} duplicate pairs with two recorded amounts show the same ×100 relationship. {metadata['duplicate_non_amount_conflicting_ids']:,} duplicate ID groups conflict on fields other than source system and refund amount.

The normalized amount averages {money(metadata['total_refund_cleaned'] / max(cleaned['quarter'].nunique(), 1))} per observed quarter across {cleaned['quarter'].nunique()} quarters. This is a dataset-derived average, not a forecast.

{markdown_table(checks_table)}

## Monthly Refunds

{markdown_table(monthly)}

## Refund Reasons

{markdown_table(reasons)}

## Policy Signals

- Refund plus replacement recorded: {len(double_dips):,} tickets.
- Refund component: {money(refund_replacement_refund)}.
- Replacement planning cost (unit cost + ₹340): {money(replacement_cost)}.
- Combined candidate exposure: {money(candidate_total)}. This is not proven loss; fulfillment and payment settlement are not supplied.
- Missing order ID among those flags: {int(double_dips['order_id'].isna().sum()):,}.
- GW-OTHER refunds above ₹500: {len(gw_over):,}; this combined code does not prove the item was goodwill or that approval was absent.
- First-response SLA breaches: {sla['total_sla_breaches']:,} total, including {sla['resolved_or_closed_breaches']:,} resolved/closed and {sla['open_or_pending_breaches']:,} still open/pending. Policy-derived credit value for resolved/closed cases: {money(sla['estimated_credit_inr'])}. Credit transactions are not included, so issuance is not independently verified.
- Refund records with missing reason code: {metadata['refunds_missing_reason']:,}; unsupported code values: {metadata['refunds_unknown_reason']:,}.

## Unresolved Items and Assumptions

- Duplicate IDs retain `helpdesk` over `legacy_fd`; non-duplicate legacy rows remain in analysis.
- Legacy `refund_amount_inr` is divided by 100 based on the cross-system duplicate-pair evidence above and the policy's distinction between legacy native units and current rupees. The PDF does not name the legacy unit.
- Missing order IDs are filled only when customer ID plus SKU identifies exactly one order. No amount/date guessing is used. Remaining records without an order-value match: {metadata['unmatched_orders']:,}; unresolved order IDs: {metadata['unresolved_order_ids']:,}.
- Unmapped resolving agents: {metadata['unmapped_agents']:,}; invalid creation timestamps: {metadata['invalid_dates']:,}.
- A refund plus replacement flag is a potential policy exception, not proof that both benefits reached the customer. Approval and fulfillment logs were not supplied.
- GW-OTHER is a combined Goodwill / Other code. Amounts above ₹500 are review candidates; a specific goodwill decision and Team Lead approval are not encoded in these files.
- SLA credit amounts are policy-derived estimates based on first response and channel target, not confirmed credits in the supplied tables.
"""


def main() -> None:
    report = build_report()
    output = ROOT / "DATA_AUDIT.md"
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output.name}")


if __name__ == "__main__":
    main()
