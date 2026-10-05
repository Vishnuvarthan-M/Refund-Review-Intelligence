import pandas as pd


def get_double_dip_cases(df: pd.DataFrame) -> pd.DataFrame:
    cases = df[df["is_refund_replacement"]].copy()
    return cases.sort_values("refund_amount_cleaned", ascending=False).reset_index(drop=True)


def get_gw_other_over_cap_cases(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        df["is_refund"]
        & df["refund_reason_code"].eq("GW-OTHER")
        & df["refund_amount_cleaned"].gt(500)
    )
    return df.loc[mask].sort_values("refund_amount_cleaned", ascending=False).reset_index(drop=True)


def get_policy_exceptions(df: pd.DataFrame) -> pd.DataFrame:
    """Return reviewable policy signals; flags alone do not prove realized loss."""
    rows = []

    for _, ticket in df[df["is_refund_replacement"]].iterrows():
        order_known = pd.notna(ticket.get("order_id")) and str(ticket.get("order_id")).strip() != ""
        replacement_cost = ticket.get("replacement_cost_policy")
        replacement_cost = float(replacement_cost) if pd.notna(replacement_cost) else 0.0
        refund_amount = float(ticket["refund_amount_cleaned"])
        rows.append(
            {
                **_ticket_fields(ticket),
                "exception_type": "Refund + replacement",
                "amount_inr": refund_amount,
                "candidate_exposure_inr": refund_amount + replacement_cost,
                "evidence": "Refund is recorded and replacement_issued=Y; actual shipment/payment not independently evidenced.",
                "policy_rule": "§5: customer must not receive both for the same order; escalate to Team Lead and Finance.",
                "review_status": "Potential exception" if order_known else "Requires review: order ID missing",
            }
        )

    for _, ticket in get_gw_other_over_cap_cases(df).iterrows():
        rows.append(
            {
                **_ticket_fields(ticket),
                "exception_type": "GW-OTHER amount above ₹500",
                "amount_inr": float(ticket["refund_amount_cleaned"]),
                "candidate_exposure_inr": float(ticket["refund_amount_cleaned"]),
                "evidence": "GW-OTHER combines Goodwill and Other; the record does not establish that this was goodwill or that approval was absent.",
                "policy_rule": "§5: goodwill credits are capped at ₹500 per ticket and require Team Lead approval.",
                "review_status": "Requires review",
            }
        )

    refund_rows = df[df["is_refund"]]
    missing_reason = refund_rows["refund_reason_code"].isna() | refund_rows["refund_reason_code"].astype("string").str.strip().eq("")
    known_codes = {"GW-OTHER", "DOA-REPL", "LOST-TRANSIT", "DUP-PAYMENT", "CANCEL", "PRICE-ADJ", "RETURN-QC-OK", "WTY-BUYBACK"}
    unknown_reason = ~refund_rows["refund_reason_code"].isin(known_codes) & ~missing_reason
    for _, ticket in refund_rows.loc[missing_reason | unknown_reason].iterrows():
        missing = pd.isna(ticket["refund_reason_code"]) or not str(ticket["refund_reason_code"]).strip()
        rows.append(
            {
                **_ticket_fields(ticket),
                "exception_type": "Missing reason code" if missing else "Unsupported reason code",
                "amount_inr": float(ticket["refund_amount_cleaned"]),
                "candidate_exposure_inr": float(ticket["refund_amount_cleaned"]),
                "evidence": f"Recorded reason code: {ticket['refund_reason_code']!r}.",
                "policy_rule": "§5: refund reason must be selected from the defined reason-code dropdown.",
                "review_status": "Requires review",
            }
        )

    for _, ticket in df[df["is_sla_breach"]].iterrows():
        rows.append(
            {
                **_ticket_fields(ticket),
                "exception_type": "First-response SLA credit",
                "amount_inr": 350.0,
                "candidate_exposure_inr": 350.0,
                "evidence": f"First human response {ticket['response_time_mins']:.0f} minutes after creation; target {ticket['target_sla_mins']:.0f} minutes.",
                "policy_rule": "§3: each ticket missing first-response SLA automatically issues ₹350 store credit on resolution.",
                "review_status": "Credit may apply; ledger absent" if ticket.get("status") in {"resolved", "closed"} else "Open/pending: credit condition not yet met",
            }
        )

    columns = [
        "exception_type", "ticket_id", "order_id", "month", "amount_inr", "candidate_exposure_inr",
        "agent_id", "agent_name", "team", "tier", "refund_reason_code", "evidence", "policy_rule", "review_status",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(rows).rename(columns={"agent_team": "team", "agent_tier": "tier"})
    return result.reindex(columns=columns).sort_values(["exception_type", "month", "ticket_id"]).reset_index(drop=True)


def _ticket_fields(ticket: pd.Series) -> dict:
    return {
        "ticket_id": ticket.get("ticket_id"),
        "order_id": ticket.get("order_id"),
        "month": ticket.get("month"),
        "agent_id": ticket.get("agent_id"),
        "agent_name": ticket.get("agent_name"),
        "agent_team": ticket.get("agent_team"),
        "agent_tier": ticket.get("agent_tier"),
        "refund_reason_code": ticket.get("refund_reason_code"),
    }


def get_sla_breach_summary(df: pd.DataFrame) -> dict:
    breached = df[df["is_sla_breach"]]
    channel_breakdown = (
        df.groupby("channel", as_index=False)
        .agg(total_tickets=("ticket_id", "nunique"), sla_breaches=("is_sla_breach", "sum"))
    )
    channel_breakdown["breach_rate_pct"] = channel_breakdown["sla_breaches"].div(channel_breakdown["total_tickets"]).mul(100)
    completed_breaches = breached[breached["status"].isin(["resolved", "closed"])]
    credits_by_channel = completed_breaches.groupby("channel").size()
    channel_breakdown["resolved_or_closed_breaches"] = channel_breakdown["channel"].map(credits_by_channel).fillna(0).astype(int)
    channel_breakdown["estimated_credit_inr"] = channel_breakdown["resolved_or_closed_breaches"] * 350
    return {
        "total_sla_breaches": int(len(breached)),
        "resolved_or_closed_breaches": int(len(completed_breaches)),
        "open_or_pending_breaches": int(len(breached) - len(completed_breaches)),
        "breach_rate_pct": float(df["is_sla_breach"].mean() * 100) if len(df) else 0.0,
        "estimated_credit_inr": float(len(completed_breaches) * 350),
        "channel_breakdown": channel_breakdown,
    }


def audit_retail_price_exceedances(df: pd.DataFrame) -> dict:
    above_unit_price = df[df["is_refund"] & df["refund_amount_cleaned"].gt(df["retail_price_inr"])].copy()
    above_order_value = above_unit_price[
        above_unit_price["order_value_inr"].notna()
        & above_unit_price["refund_amount_cleaned"].gt(above_unit_price["order_value_inr"])
    ]
    columns = ["ticket_id", "order_id", "product_sku", "product_name", "qty", "retail_price_inr", "order_value_inr", "refund_amount_cleaned"]
    return {
        "total_exceeding_unit_price": int(len(above_unit_price)),
        "exceeding_order_value": int(len(above_order_value)),
        "exceedance_records": above_unit_price.reindex(columns=columns).head(50),
    }
