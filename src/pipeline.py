import os

import numpy as np
import pandas as pd


REFUND_REASON_CODES = {
    "GW-OTHER",
    "DOA-REPL",
    "LOST-TRANSIT",
    "DUP-PAYMENT",
    "CANCEL",
    "PRICE-ADJ",
    "RETURN-QC-OK",
    "WTY-BUYBACK",
}
SOURCE_PRIORITY = {"helpdesk": 0, "legacy_fd": 1}
SLA_MINUTES = {"chat": 15, "voice": 120, "social": 240, "email": 480}


def load_data(data_dir: str = "."):
    """Read the supplied CSVs without modifying their source files."""
    files = ("tickets", "agents", "orders", "products", "customers")
    return tuple(pd.read_csv(os.path.join(data_dir, f"{name}.csv")) for name in files)


def _unique_order_fallback(tickets: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Fill missing order IDs only where customer+SKU identifies one order."""
    candidate_counts = orders.groupby(["customer_id", "sku"]).size()
    unique_pairs = candidate_counts[candidate_counts == 1].index
    fallback = orders.set_index(["customer_id", "sku"])
    missing = tickets["order_id"].isna()
    keys = pd.MultiIndex.from_arrays(
        [tickets.loc[missing, "customer_id"], tickets.loc[missing, "product_sku"]]
    )
    eligible = keys.isin(unique_pairs)
    ticket_indexes = tickets.index[missing][eligible]
    order_keys = pd.MultiIndex.from_arrays(
        [tickets.loc[ticket_indexes, "customer_id"], tickets.loc[ticket_indexes, "product_sku"]]
    )
    matched = fallback.loc[order_keys].reset_index()
    tickets.loc[ticket_indexes, "order_id"] = matched["order_id"].to_numpy()
    return tickets


def clean_and_reconcile(
    tickets: pd.DataFrame,
    agents: pd.DataFrame,
    orders: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
):
    """Deduplicate by ticket ID, normalize legacy money, and enrich conservatively."""
    raw = tickets.copy()
    raw_rows = len(raw)
    duplicate_mask = raw["ticket_id"].duplicated(keep=False)
    duplicate_rows = raw.loc[duplicate_mask].copy()
    duplicate_groups = duplicate_rows.groupby("ticket_id", dropna=False)
    duplicate_id_count = int(duplicate_groups.ngroups)
    all_cross_system_pairs = bool(
        duplicate_groups.size().eq(2).all()
        and duplicate_groups["source_system"].apply(lambda values: set(values) == {"helpdesk", "legacy_fd"}).all()
    ) if duplicate_id_count else True
    duplicate_pair_refund_count = 0
    duplicate_pair_ratio_100_count = 0
    duplicate_non_amount_conflicting_ids = 0
    if duplicate_id_count:
        pair_amounts = duplicate_rows.pivot(index="ticket_id", columns="source_system", values="refund_amount_inr")
        if {"helpdesk", "legacy_fd"}.issubset(pair_amounts.columns):
            paired_refunds = pair_amounts[["helpdesk", "legacy_fd"]].dropna()
            duplicate_pair_refund_count = int(len(paired_refunds))
            ratios = paired_refunds["legacy_fd"].div(paired_refunds["helpdesk"].replace(0, np.nan))
            duplicate_pair_ratio_100_count = int(np.isclose(ratios.dropna(), 100.0).sum())
        comparable_columns = [
            column for column in duplicate_rows.columns
            if column not in {"ticket_id", "source_system", "refund_amount_inr"}
        ]
        conflicting = duplicate_rows.groupby("ticket_id")[comparable_columns].nunique(dropna=False).gt(1).any(axis=1)
        duplicate_non_amount_conflicting_ids = int(conflicting.sum())

    # Current helpdesk is authoritative for duplicate IDs; preserve original order as tie-break.
    raw["_source_priority"] = raw["source_system"].map(SOURCE_PRIORITY).fillna(2)
    canonical = raw.sort_values(["_source_priority"], kind="stable").drop_duplicates("ticket_id", keep="first")
    canonical = canonical.drop(columns="_source_priority").copy()
    duplicate_rows_removed = raw_rows - len(canonical)
    raw_refund_total = float(pd.to_numeric(raw["refund_amount_inr"], errors="coerce").sum())

    canonical["refund_amount_raw"] = pd.to_numeric(canonical["refund_amount_inr"], errors="coerce")
    legacy_mask = canonical["source_system"].eq("legacy_fd")
    canonical["refund_amount_cleaned"] = canonical["refund_amount_raw"].where(
        ~legacy_mask, canonical["refund_amount_raw"] / 100.0
    )
    canonical["created_at_dt"] = pd.to_datetime(canonical["created_at"], errors="coerce")
    canonical["month"] = canonical["created_at_dt"].dt.strftime("%Y-%m")
    canonical["quarter"] = canonical["created_at_dt"].dt.to_period("Q").astype("string")
    canonical["first_response_dt"] = pd.to_datetime(canonical["first_response_at"], errors="coerce")

    roster = agents.rename(
        columns={"name": "agent_name", "team": "agent_team", "site": "agent_site", "shift": "agent_shift", "tier": "agent_tier"}
    )
    roster_columns = ["agent_id", "agent_name", "agent_team", "agent_site", "agent_shift", "agent_tier", "from_date", "to_date"]
    roster = roster[[column for column in roster_columns if column in roster.columns]].drop_duplicates("agent_id")
    canonical = canonical.merge(roster, on="agent_id", how="left", validate="many_to_one")

    product_columns = ["sku", "product_name", "family", "unit_cost_inr", "retail_price_inr", "warranty_months"]
    canonical = canonical.merge(
        products[product_columns], left_on="product_sku", right_on="sku", how="left", validate="many_to_one"
    )

    order_columns = ["order_id", "customer_id", "sku", "order_value_inr", "qty", "order_date", "channel"]
    orders_slim = orders[order_columns].rename(
        columns={"customer_id": "order_customer_id", "sku": "order_sku", "channel": "order_channel"}
    )
    canonical = canonical.merge(orders_slim, on="order_id", how="left", validate="many_to_one")

    # A fallback is used only for a unique customer+SKU order, never by amount/date guesswork.
    if canonical["order_id"].isna().any():
        missing_order = canonical.loc[canonical["order_id"].isna(), ["ticket_id", "customer_id", "product_sku"]].copy()
        candidate_counts = orders.groupby(["customer_id", "sku"]).size()
        fallback = orders.set_index(["customer_id", "sku"])
        keys = pd.MultiIndex.from_arrays([missing_order["customer_id"], missing_order["product_sku"]])
        unique_keys = candidate_counts[candidate_counts == 1].index
        eligible = keys.isin(unique_keys)
        selected = missing_order.loc[eligible]
        selected_keys = pd.MultiIndex.from_arrays([selected["customer_id"], selected["product_sku"]])
        if not selected.empty:
            fallback_rows = fallback.loc[selected_keys].reset_index().set_index(selected.index)
            canonical.loc[selected.index, "order_id"] = fallback_rows["order_id"].to_numpy()
            canonical.loc[selected.index, "order_value_inr"] = fallback_rows["order_value_inr"].to_numpy()
            canonical.loc[selected.index, "qty"] = fallback_rows["qty"].to_numpy()
            canonical.loc[selected.index, "order_date"] = fallback_rows["order_date"].to_numpy()
            canonical.loc[selected.index, "order_channel"] = fallback_rows["channel"].to_numpy()
            canonical.loc[selected.index, "order_customer_id"] = fallback_rows["customer_id"].to_numpy()
            canonical.loc[selected.index, "order_sku"] = fallback_rows["sku"].to_numpy()

    canonical = canonical.merge(
        customers[["customer_id", "city", "state", "care_plus"]], on="customer_id", how="left", validate="many_to_one"
    )
    canonical["is_refund"] = canonical["refund_amount_cleaned"].gt(0)
    canonical["is_refund_replacement"] = canonical["is_refund"] & canonical["replacement_issued"].eq("Y")
    canonical["replacement_cost_policy"] = np.where(
        canonical["replacement_issued"].eq("Y"), canonical["unit_cost_inr"] + 340.0, 0.0
    )
    canonical["response_time_mins"] = (
        canonical["first_response_dt"] - canonical["created_at_dt"]
    ).dt.total_seconds() / 60.0
    canonical["target_sla_mins"] = canonical["channel"].map(SLA_MINUTES)
    canonical["is_sla_breach"] = canonical["response_time_mins"].gt(canonical["target_sla_mins"])

    refund_rows = canonical["refund_amount_cleaned"].notna()
    canonical_source_counts = canonical["source_system"].value_counts(dropna=False).to_dict()
    canonical_legacy_mask = canonical["source_system"].eq("legacy_fd")
    metadata = {
        "raw_rows": raw_rows,
        "unique_tickets": int(raw["ticket_id"].nunique()),
        "duplicate_rows_removed": duplicate_rows_removed,
        "duplicate_ticket_ids": duplicate_id_count,
        "duplicate_cross_system_pairs": all_cross_system_pairs,
        "duplicate_pair_refund_count": duplicate_pair_refund_count,
        "duplicate_pair_ratio_100_count": duplicate_pair_ratio_100_count,
        "duplicate_non_amount_conflicting_ids": duplicate_non_amount_conflicting_ids,
        "raw_refund_ticket_count": int(raw["refund_amount_inr"].notna().sum()),
        "raw_refund_total": raw_refund_total,
        "deduplicated_raw_refund_total": float(canonical["refund_amount_raw"].sum()),
        "total_refund_cleaned": float(canonical["refund_amount_cleaned"].sum()),
        "refund_ticket_count": int(refund_rows.sum()),
        "refund_rate": float(refund_rows.mean()) if len(canonical) else 0.0,
        "raw_source_counts": raw["source_system"].value_counts(dropna=False).to_dict(),
        "canonical_source_counts": canonical_source_counts,
        "legacy_raw_refund_total": float(canonical.loc[canonical_legacy_mask, "refund_amount_raw"].sum()),
        "legacy_normalized_refund_total": float(canonical.loc[canonical_legacy_mask, "refund_amount_cleaned"].sum()),
        "unmapped_agents": int(canonical["agent_name"].isna().sum()),
        "unmatched_orders": int(canonical["order_value_inr"].isna().sum()),
        "unresolved_order_ids": int(canonical["order_id"].isna().sum()),
        "invalid_dates": int(canonical["created_at_dt"].isna().sum()),
        "refunds_missing_reason": int((refund_rows & canonical["refund_reason_code"].isna()).sum()),
        "refunds_unknown_reason": int((refund_rows & ~canonical["refund_reason_code"].isin(REFUND_REASON_CODES)).sum()),
    }
    return canonical, metadata
