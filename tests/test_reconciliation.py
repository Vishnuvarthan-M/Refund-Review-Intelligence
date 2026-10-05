import pandas as pd
import pytest

from src.analytics import get_monthly_refunds
from src.pipeline import clean_and_reconcile, load_data
from src.policy_checks import get_double_dip_cases, get_gw_other_over_cap_cases, get_sla_breach_summary
from src.ai_review import review_refund_ticket
from src.validation import run_reconciliation_assertions


@pytest.fixture(scope="module")
def reconciled():
    raw, agents, orders, products, customers = load_data(".")
    cleaned, metadata = clean_and_reconcile(raw, agents, orders, products, customers)
    return raw, cleaned, metadata


def test_duplicate_ticket_ids_are_removed_and_current_copy_is_kept(reconciled):
    raw, cleaned, metadata = reconciled
    duplicate_ids = raw.loc[raw.ticket_id.duplicated(False), "ticket_id"].unique()
    assert len(duplicate_ids) == metadata["duplicate_ticket_ids"]
    assert cleaned.ticket_id.is_unique
    assert metadata["duplicate_rows_removed"] == len(raw) - len(cleaned)
    retained = cleaned.set_index("ticket_id").loc[duplicate_ids]
    assert retained.source_system.eq("helpdesk").all()


def test_legacy_amounts_are_normalized_to_inr(reconciled):
    _, cleaned, metadata = reconciled
    legacy_refunds = cleaned.loc[cleaned.source_system.eq("legacy_fd") & cleaned.refund_amount_raw.notna()]
    assert len(legacy_refunds) > 0
    assert (legacy_refunds.refund_amount_cleaned * 100).equals(legacy_refunds.refund_amount_raw.astype(float))
    assert metadata["legacy_raw_refund_total"] == pytest.approx(metadata["legacy_normalized_refund_total"] * 100)


def test_refund_totals_reconcile_against_input_data(reconciled):
    raw, cleaned, metadata = reconciled
    raw_total = pd.to_numeric(raw.refund_amount_inr, errors="coerce").sum()
    assert metadata["raw_refund_total"] == pytest.approx(raw_total)
    assert metadata["refund_ticket_count"] == cleaned.refund_amount_cleaned.notna().sum()
    assert metadata["total_refund_cleaned"] == pytest.approx(cleaned.refund_amount_cleaned.sum())
    assert run_reconciliation_assertions(cleaned, metadata)["status"] == "PASSED"


def test_refund_and_replacement_cases_require_both_flags():
    tickets = pd.DataFrame(
        {
            "ticket_id": ["a", "b", "c"],
            "is_refund_replacement": [True, False, False],
            "refund_amount_cleaned": [100.0, 100.0, None],
        }
    )
    cases = get_double_dip_cases(tickets)
    assert cases.ticket_id.tolist() == ["a"]


def test_goodwill_over_threshold_finds_only_amounts_above_cap():
    tickets = pd.DataFrame(
        {
            "ticket_id": ["a", "b", "c", "d"],
            "is_refund": [True, True, True, False],
            "refund_reason_code": ["GW-OTHER"] * 4,
            "refund_amount_cleaned": [500.0, 500.01, 700.0, 900.0],
        }
    )
    cases = get_gw_other_over_cap_cases(tickets)
    assert cases.ticket_id.tolist() == ["c", "b"]


def test_monthly_aggregation_counts_tickets_and_sums_refunds():
    tickets = pd.DataFrame(
        {
            "ticket_id": ["a", "b", "c"],
            "month": ["2026-01", "2026-01", "2026-02"],
            "refund_amount_cleaned": [100.0, 50.0, 80.0],
        }
    )
    monthly = get_monthly_refunds(tickets).set_index("month")
    assert monthly.loc["2026-01", "refund_ticket_count"] == 2
    assert monthly.loc["2026-01", "refund_amount_inr"] == pytest.approx(150.0)
    assert monthly.loc["2026-02", "refund_amount_inr"] == pytest.approx(80.0)


def test_refund_settlement_wording_is_not_mistaken_for_product_return():
    result = review_refund_ticket("refund status please", "Amount returned to card; fresh unit shipped", "GW-OTHER")
    assert result["likely_reason"] == "Unclear"
    assert result["assessment"] == "ambiguous"


def test_specific_reason_supported_by_both_text_fields_flags_gw_other():
    result = review_refund_ticket("Card charged two times", "Confirmed duplicate payment and refunded", "GW-OTHER")
    assert result["likely_reason"] == "Payment"
    assert result["assessment"] == "unsupported"


def test_sla_credit_estimate_only_includes_resolved_or_closed_tickets():
    tickets = pd.DataFrame(
        {
            "ticket_id": ["a", "b", "c"],
            "channel": ["chat", "email", "chat"],
            "is_sla_breach": [True, True, False],
            "status": ["resolved", "pending", "closed"],
        }
    )
    summary = get_sla_breach_summary(tickets)
    assert summary["total_sla_breaches"] == 2
    assert summary["resolved_or_closed_breaches"] == 1
    assert summary["open_or_pending_breaches"] == 1
    assert summary["estimated_credit_inr"] == pytest.approx(350.0)
