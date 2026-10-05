import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.ai_review import review_refund_frame, review_refund_ticket
from src.analytics import (
    get_agent_summary,
    get_monthly_reason_refunds,
    get_monthly_refunds,
    get_quarterly_reconciliation,
    get_reason_summary,
    get_reconciled_metrics,
    get_team_tier_summary,
)
from src.pipeline import clean_and_reconcile, load_data
from src.policy_checks import get_policy_exceptions, get_sla_breach_summary
from src.validation import run_reconciliation_assertions


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Vireo Audio | Refund Review", layout="wide")
st.markdown(
    """
    <style>
    :root { --ink: #202a2e; --muted: #66747a; --line: #d9e0dd; --accent: #167d72; --warning: #b85d38; }
    .block-container { max-width: 1480px; padding-top: 1.25rem; }
    h1, h2, h3 { color: var(--ink); }
    [data-testid="stMetric"] { background: #f2f6f3; border-top: 2px solid var(--accent); padding: .8rem; }
    div[data-testid="stTabs"] button { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def money(value: float) -> str:
    return f"₹{value:,.0f}"


def lakhs(value: float) -> str:
    return f"₹{value / 100_000:,.2f} L"


@st.cache_data(show_spinner="Reconciling supplied CSV files...")
def load_clean_data(data_dir: str):
    raw_tickets, agents, orders, products, customers = load_data(data_dir)
    return clean_and_reconcile(raw_tickets, agents, orders, products, customers)


@st.cache_data(show_spinner=False)
def local_ai_review(frame: pd.DataFrame) -> pd.DataFrame:
    return review_refund_frame(frame, use_llm=False)


cleaned, metadata = load_clean_data(str(ROOT))
checks = run_reconciliation_assertions(cleaned, metadata)
metrics = get_reconciled_metrics(cleaned, metadata)
monthly = get_monthly_refunds(cleaned)
monthly_reasons = get_monthly_reason_refunds(cleaned)
reasons = get_reason_summary(cleaned)
quarterly = get_quarterly_reconciliation(cleaned)
agents = get_agent_summary(cleaned)
team_tiers = get_team_tier_summary(cleaned)
exceptions = get_policy_exceptions(cleaned)
double_dips = exceptions[exceptions["exception_type"].eq("Refund + replacement")]

st.title("Vireo Audio | Refund Intelligence")
st.caption("Finance reconciliation and support policy review · 1 Jan 2025 to 30 Jun 2026")

exec_tab, recon_tab, refunds_tab, agents_tab, ai_tab, policy_tab = st.tabs(
    ["Executive Summary", "Reconciliation", "Refund Analysis", "Agent Analysis", "AI Review", "Policy Exceptions"]
)

with exec_tab:
    st.subheader("Board-pack view")
    columns = st.columns(4)
    columns[0].metric("Reconciled refunds", lakhs(metrics["total_cleaned_refund_value"]))
    columns[1].metric("Refund tickets", f"{metrics['refund_ticket_count']:,}", f"{metrics['refund_rate_pct']:.2f}% of unique tickets")
    columns[2].metric("Average per quarter", lakhs(metrics["quarterly_avg"]))
    columns[3].metric("Candidate exposure", lakhs(double_dips["candidate_exposure_inr"].sum()))

    left, right = st.columns([1.2, 1])
    with left:
        trend = px.line(
            monthly,
            x="month",
            y="refund_amount_inr",
            markers=True,
            title="Monthly refund value",
            labels={"month": "Month", "refund_amount_inr": "Refund value (INR)"},
        )
        trend.update_traces(line_color="#167d72", marker_color="#b85d38")
        trend.update_layout(margin=dict(l=10, r=10, t=55, b=10), height=330)
        st.plotly_chart(trend, width="stretch")
    with right:
        reason_chart = px.bar(
            reasons.head(8).sort_values("refund_amount_inr"),
            x="refund_amount_inr",
            y="refund_reason_code",
            orientation="h",
            title="Refund value by reason code",
            labels={"refund_amount_inr": "Refund value (INR)", "refund_reason_code": "Reason"},
        )
        reason_chart.update_traces(marker_color="#167d72")
        reason_chart.update_layout(margin=dict(l=10, r=10, t=55, b=10), height=330)
        st.plotly_chart(reason_chart, width="stretch")

    st.subheader("Decision opportunity")
    recorded_cases = len(double_dips)
    recorded_candidate_exposure = float(double_dips["candidate_exposure_inr"].sum())
    observed_quarters = max(quarterly["quarter"].nunique(), 1)
    reduction_target = 0.25
    quarterly_candidate_baseline = recorded_candidate_exposure / observed_quarters
    quarterly_opportunity = quarterly_candidate_baseline * reduction_target
    target_cases = round(recorded_cases * (1 - reduction_target))
    st.write(
        f"Reduce recorded refund-plus-replacement cases from {recorded_cases:,} to approximately {target_cases:,} per comparable 18-month period, "
        f"a proposed 25% reduction in flagged cases. At the observed candidate-exposure rate, that is approximately "
        f"{money(quarterly_opportunity)} per quarter in potential preventable leakage."
    )
    st.caption(
        f"Baseline: {money(recorded_candidate_exposure)} candidate exposure over {observed_quarters} quarters. "
        "This is a planning opportunity, not confirmed loss: 8 of the 166 flagged tickets have no order ID, and the export does not prove dispatch or payment settlement."
    )
    top_reason = reasons.iloc[0]
    st.info(
        f"Largest recorded reason bucket: {top_reason['refund_reason_code']} — {money(top_reason['refund_amount_inr'])} "
        f"across {int(top_reason['refund_ticket_count']):,} tickets. GW-OTHER is a combined Goodwill / Other dropdown value, not a confirmed goodwill total."
    )

with recon_tab:
    st.subheader("Reconciliation bridge")
    bridge = pd.DataFrame(
        [
            {"Stage": "Raw export", "Records": metrics["raw_row_count"], "Refund tickets": metrics["raw_refund_ticket_count"], "Refund amount": metrics["raw_refund_total"], "Interpretation": "Mixed rupees and legacy native units; duplicates included"},
            {"Stage": "Canonical records", "Records": metrics["unique_ticket_count"], "Refund tickets": metrics["refund_ticket_count"], "Refund amount": metrics["deduplicated_raw_refund_total"], "Interpretation": "Helpdesk retained for duplicate ticket IDs; legacy amounts still unnormalized"},
            {"Stage": "Normalized INR", "Records": metrics["unique_ticket_count"], "Refund tickets": metrics["refund_ticket_count"], "Refund amount": metrics["total_cleaned_refund_value"], "Interpretation": "legacy_fd amount divided by 100; helpdesk amounts unchanged"},
        ]
    )
    st.dataframe(bridge, width="stretch", hide_index=True, column_config={"Refund amount": st.column_config.NumberColumn(format="₹%,.2f")})
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Raw source rows**")
        st.dataframe(pd.Series(metadata["raw_source_counts"], name="rows").rename_axis("source_system").reset_index(), hide_index=True, width="stretch")
    with col2:
        st.markdown("**Canonical source rows**")
        st.dataframe(pd.Series(metadata["canonical_source_counts"], name="rows").rename_axis("source_system").reset_index(), hide_index=True, width="stretch")
    st.markdown("**Reconciliation checks**")
    check_frame = pd.DataFrame(checks["checks"]).astype(str)
    st.dataframe(check_frame, hide_index=True, width="stretch")
    st.write(
        f"Duplicate ticket IDs: {metadata['duplicate_ticket_ids']:,}; rows removed: {metadata['duplicate_rows_removed']:,}. "
        f"Legacy amount before conversion: {money(metadata['legacy_raw_refund_total'])}; after conversion: {money(metadata['legacy_normalized_refund_total'])}."
    )
    st.warning(
        f"Unresolved order enrichment: {metadata['unresolved_order_ids']:,} tickets have no usable order ID after only unambiguous customer+SKU matching; "
        f"{metadata['unmatched_orders']:,} tickets lack an order-value match."
    )
    st.download_button("Download reconciliation CSV", bridge.to_csv(index=False).encode("utf-8"), "reconciliation.csv", "text/csv")

with refunds_tab:
    st.subheader("Monthly, reason, and source views")
    st.dataframe(monthly, width="stretch", hide_index=True, column_config={"refund_amount_inr": st.column_config.NumberColumn(format="₹%,.2f")})
    st.markdown("**Monthly by reason**")
    st.dataframe(
        monthly_reasons,
        width="stretch",
        hide_index=True,
        column_config={
            "refund_amount_inr": st.column_config.NumberColumn(format="₹%,.2f"),
            "percentage_of_month_value": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    source_summary = cleaned[cleaned["is_refund"]].groupby("source_system", as_index=False).agg(
        refund_ticket_count=("ticket_id", "nunique"), refund_amount_inr=("refund_amount_cleaned", "sum")
    )
    st.markdown("**Normalized refunds by source system**")
    st.dataframe(source_summary, width="stretch", hide_index=True, column_config={"refund_amount_inr": st.column_config.NumberColumn(format="₹%,.2f")})
    st.download_button("Download monthly reason CSV", monthly_reasons.to_csv(index=False).encode("utf-8"), "monthly_refunds_by_reason.csv", "text/csv")

with agents_tab:
    st.subheader("Resolving-agent attribution")
    st.caption("Descriptive workload and reason mix only. Returns Desk processes many refunds by design; Tier 2 should not be compared with Tier 1 on volume.")
    team_filter = st.selectbox("Team filter", ["All teams", *sorted(agents["team"].dropna().unique())])
    tier_filter = st.selectbox("Tier filter", ["All tiers", *sorted(agents["tier"].dropna().unique())])
    agent_view = agents.copy()
    if team_filter != "All teams":
        agent_view = agent_view[agent_view["team"].eq(team_filter)]
    if tier_filter != "All tiers":
        agent_view = agent_view[agent_view["tier"].eq(tier_filter)]
    st.dataframe(
        agent_view,
        width="stretch",
        hide_index=True,
        column_config={
            "refund_amount_inr": st.column_config.NumberColumn(format="₹%,.2f"),
            "average_refund_inr": st.column_config.NumberColumn(format="₹%,.2f"),
        },
    )
    st.markdown("**Team and tier context**")
    st.dataframe(
        team_tiers,
        width="stretch",
        hide_index=True,
        column_config={"refund_amount_inr": st.column_config.NumberColumn(format="₹%,.2f"), "refund_rate_pct": st.column_config.NumberColumn(format="%.2f%%")},
    )
    st.download_button("Download agent CSV", agent_view.to_csv(index=False).encode("utf-8"), "agent_refund_activity.csv", "text/csv")

with ai_tab:
    st.subheader("Structured reason evidence review")
    st.caption("Offline review uses transparent keyword evidence rules. Gemini is optional and is never called without an explicit button action. No independent human validation has been completed; treat classifications as triage only.")
    review_data = local_ai_review(cleaned)
    review_month = st.multiselect("Month", sorted(review_data["month"].dropna().unique()), key="ai_month")
    review_team = st.multiselect("Team", sorted(review_data["agent_team"].dropna().unique()), key="ai_team")
    review_reason = st.multiselect("Reason code", sorted(review_data["refund_reason_code"].dropna().unique()), key="ai_reason")
    review_status = st.multiselect("Assessment", sorted(review_data["assessment"].unique()), key="ai_assessment")
    visible = review_data.copy()
    for values, column in ((review_month, "month"), (review_team, "agent_team"), (review_reason, "refund_reason_code"), (review_status, "assessment")):
        if values:
            visible = visible[visible[column].isin(values)]
    ai_columns = ["ticket_id", "month", "agent_id", "agent_team", "refund_reason_code", "likely_reason", "assessment", "confidence", "reviewer", "review_status", "customer_message", "agent_notes", "evidence_summary"]
    st.dataframe(visible[ai_columns], width="stretch", hide_index=True, height=420)
    api_key = st.text_input("Gemini API key (optional)", type="password", key="gemini_key")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    selected_id = st.selectbox("Single ticket for optional Gemini review", visible["ticket_id"].tolist() if not visible.empty else [])
    if st.button("Review selected ticket with Gemini", disabled=not bool(api_key) or not selected_id):
        record = visible.loc[visible["ticket_id"].eq(selected_id)].iloc[0]
        result = review_refund_ticket(record["customer_message"], record["agent_notes"], record["refund_reason_code"], use_llm=True)
        st.json(result)
    st.download_button("Download review CSV", visible[ai_columns].to_csv(index=False).encode("utf-8"), "reason_text_review.csv", "text/csv")

with policy_tab:
    st.subheader("Policy signals for review")
    st.caption("A data flag is not proof of an actual shipment, unapproved credit, or realized loss.")
    filter_cols = st.columns(5)
    month_options = sorted(exceptions["month"].dropna().unique())
    months_filter = filter_cols[0].multiselect("Month", month_options, key="policy_month")
    team_options = sorted(exceptions["team"].dropna().unique())
    teams_filter = filter_cols[1].multiselect("Team", team_options, key="policy_team")
    agent_options = sorted(exceptions["agent_name"].dropna().unique())
    agents_filter = filter_cols[2].multiselect("Agent", agent_options, key="policy_agent")
    reason_options = sorted(exceptions["refund_reason_code"].dropna().unique())
    reasons_filter = filter_cols[3].multiselect("Reason", reason_options, key="policy_reason")
    exception_options = sorted(exceptions["exception_type"].dropna().unique())
    types_filter = filter_cols[4].multiselect("Exception type", exception_options, key="policy_type")
    visible_exceptions = exceptions.copy()
    for values, column in ((months_filter, "month"), (teams_filter, "team"), (agents_filter, "agent_name"), (reasons_filter, "refund_reason_code"), (types_filter, "exception_type")):
        if values:
            visible_exceptions = visible_exceptions[visible_exceptions[column].isin(values)]
    st.metric("Visible exception records", f"{len(visible_exceptions):,}")
    st.caption("Amounts are shown per finding. Tickets can have multiple findings, so amounts across rows are not additive and do not represent total loss.")
    st.dataframe(visible_exceptions, width="stretch", hide_index=True, height=480)
    st.download_button("Download policy review CSV", visible_exceptions.to_csv(index=False).encode("utf-8"), "policy_review.csv", "text/csv")
    sla_summary = get_sla_breach_summary(cleaned)
    st.caption(
        f"First-response breaches: {sla_summary['total_sla_breaches']:,} ({sla_summary['breach_rate_pct']:.2f}%); "
        f"{sla_summary['resolved_or_closed_breaches']:,} are resolved/closed and {sla_summary['open_or_pending_breaches']:,} remain open/pending. "
        f"Policy-derived credit amount for resolved/closed cases: {money(sla_summary['estimated_credit_inr'])}. Issuance cannot be verified from supplied tables."
    )
