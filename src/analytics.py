import pandas as pd


def get_reconciled_metrics(df: pd.DataFrame, metadata: dict) -> dict:
    refund_rows = df["refund_amount_cleaned"].notna()
    total = float(df["refund_amount_cleaned"].sum())
    return {
        "raw_row_count": int(metadata["raw_rows"]),
        "unique_ticket_count": int(len(df)),
        "duplicate_rows_removed": int(metadata["duplicate_rows_removed"]),
        "duplicate_ticket_ids": int(metadata["duplicate_ticket_ids"]),
        "raw_refund_ticket_count": int(metadata["raw_refund_ticket_count"]),
        "raw_refund_total": float(metadata["raw_refund_total"]),
        "deduplicated_raw_refund_total": float(metadata["deduplicated_raw_refund_total"]),
        "total_cleaned_refund_value": total,
        "quarterly_avg": total / max(df["quarter"].nunique(), 1),
        "refund_ticket_count": int(refund_rows.sum()),
        "refund_rate_pct": float(refund_rows.mean() * 100) if len(df) else 0.0,
    }


def get_monthly_refunds(df: pd.DataFrame) -> pd.DataFrame:
    refunds = df[df["refund_amount_cleaned"].notna()]
    return (
        refunds.groupby("month", as_index=False)
        .agg(
            refund_ticket_count=("ticket_id", "nunique"),
            refund_amount_inr=("refund_amount_cleaned", "sum"),
        )
        .sort_values("month")
        .reset_index(drop=True)
    )


def get_monthly_reason_refunds(df: pd.DataFrame) -> pd.DataFrame:
    refunds = df[df["refund_amount_cleaned"].notna()].copy()
    refunds["refund_reason_code"] = refunds["refund_reason_code"].fillna("MISSING")
    grouped = (
        refunds.groupby(["month", "refund_reason_code"], as_index=False)
        .agg(
            refund_ticket_count=("ticket_id", "nunique"),
            refund_amount_inr=("refund_amount_cleaned", "sum"),
        )
    )
    totals = grouped.groupby("month")["refund_amount_inr"].transform("sum")
    grouped["percentage_of_month_value"] = grouped["refund_amount_inr"].div(totals.where(totals.ne(0))).mul(100)
    return grouped.sort_values(["month", "refund_amount_inr"], ascending=[True, False]).reset_index(drop=True)


def get_reason_summary(df: pd.DataFrame) -> pd.DataFrame:
    refunds = df[df["refund_amount_cleaned"].notna()].copy()
    refunds["refund_reason_code"] = refunds["refund_reason_code"].fillna("MISSING")
    total = float(refunds["refund_amount_cleaned"].sum())
    summary = (
        refunds.groupby("refund_reason_code", as_index=False)
        .agg(
            refund_ticket_count=("ticket_id", "nunique"),
            refund_amount_inr=("refund_amount_cleaned", "sum"),
            average_refund_inr=("refund_amount_cleaned", "mean"),
        )
    )
    summary["value_share_pct"] = summary["refund_amount_inr"].div(total).mul(100) if total else 0.0
    return summary.sort_values("refund_amount_inr", ascending=False).reset_index(drop=True)


def get_agent_summary(df: pd.DataFrame) -> pd.DataFrame:
    result = (
        df.groupby(["agent_id", "agent_name", "agent_team", "agent_tier"], dropna=False)
        .agg(
            total_tickets=("ticket_id", "nunique"),
            refund_ticket_count=("is_refund", "sum"),
            refund_amount_inr=("refund_amount_cleaned", "sum"),
            refund_replacement_cases=("is_refund_replacement", "sum"),
        )
        .reset_index()
        .rename(columns={"agent_team": "team", "agent_tier": "tier"})
    )
    result["average_refund_inr"] = result["refund_amount_inr"].div(
        result["refund_ticket_count"].replace(0, pd.NA)
    )
    return result.sort_values(["team", "tier", "agent_name"], na_position="last").reset_index(drop=True)


def get_team_tier_summary(df: pd.DataFrame) -> pd.DataFrame:
    result = (
        df.groupby(["agent_team", "agent_tier"], dropna=False)
        .agg(
            total_tickets=("ticket_id", "nunique"),
            refund_ticket_count=("is_refund", "sum"),
            refund_amount_inr=("refund_amount_cleaned", "sum"),
            refund_replacement_cases=("is_refund_replacement", "sum"),
        )
        .reset_index()
        .rename(columns={"agent_team": "team", "agent_tier": "tier"})
    )
    result["refund_rate_pct"] = result["refund_ticket_count"].div(result["total_tickets"].replace(0, pd.NA)).mul(100)
    return result.sort_values(["tier", "team"]).reset_index(drop=True)


def get_quarterly_reconciliation(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("quarter", as_index=False)
        .agg(
            total_tickets=("ticket_id", "nunique"),
            refund_ticket_count=("is_refund", "sum"),
            refund_amount_inr=("refund_amount_cleaned", "sum"),
        )
        .sort_values("quarter")
        .reset_index(drop=True)
    )
