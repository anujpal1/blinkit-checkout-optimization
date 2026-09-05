from pathlib import Path

import numpy as np
import pandas as pd


STAGE_LABELS = [
    "App Open", "Search", "Product View", "Add to Cart", "Cart View",
    "Checkout Started", "Payment Attempt", "Order Completed",
]
STAGE_COLUMNS = [stage.lower().replace(" ", "_") for stage in STAGE_LABELS]
FEE_BAND_ORDER = ["Free", "Low (1-30)", "Medium (31-50)", "High (51+)"]


def required_files(root: Path) -> dict[str, Path]:
    return {
        "sessions": root / "outputs" / "tables" / "session_funnel.csv",
        "orders": root / "data" / "raw" / "orders.csv",
        "kpis": root / "outputs" / "tables" / "kpi_summary.csv",
        "revenue": root / "outputs" / "tables" / "revenue_impact.csv",
        "experiment_groups": root / "outputs" / "tables" / "ab_test_group_metrics.csv",
        "experiment_inference": root / "outputs" / "tables" / "ab_test_inference.csv",
    }


def add_delivery_fee_band(sessions: pd.DataFrame) -> pd.DataFrame:
    prepared = sessions.copy()
    conditions = [
        prepared.delivery_fee.eq(0),
        prepared.delivery_fee.le(30),
        prepared.delivery_fee.le(50),
    ]
    prepared["delivery_fee_band"] = np.select(
        conditions,
        FEE_BAND_ORDER[:3],
        default=FEE_BAND_ORDER[3],
    )
    prepared["delivery_fee_band"] = pd.Categorical(
        prepared.delivery_fee_band, categories=FEE_BAND_ORDER, ordered=True
    )
    prepared["session_start"] = pd.to_datetime(prepared.session_start)
    return prepared


def load_dashboard_data(root: Path) -> dict[str, pd.DataFrame]:
    paths = required_files(root)
    sessions = add_delivery_fee_band(pd.read_csv(paths["sessions"]))
    return {
        "sessions": sessions,
        "orders": pd.read_csv(paths["orders"]),
        "kpis": pd.read_csv(paths["kpis"]),
        "revenue": pd.read_csv(paths["revenue"]),
        "experiment_groups": pd.read_csv(paths["experiment_groups"]),
        "experiment_inference": pd.read_csv(paths["experiment_inference"]),
    }


def filter_sessions(sessions: pd.DataFrame, filters: dict[str, str]) -> pd.DataFrame:
    filtered = sessions
    for column, selected in filters.items():
        if selected != "All":
            filtered = filtered.loc[filtered[column].astype(str) == selected]
    return filtered.copy()


def safe_percentage(numerator: float, denominator: float) -> float | None:
    return 100 * numerator / denominator if denominator else None


def calculate_kpis(sessions: pd.DataFrame, orders: pd.DataFrame) -> dict[str, float | int | None]:
    selected_orders = orders.loc[orders.session_id.isin(sessions.session_id)]
    successful = selected_orders.loc[selected_orders.payment_status == "Success"]
    completed_orders = int(sessions.order_completed.sum())
    checkout_starts = int(sessions.checkout_started.sum())
    cart_views = int(sessions.cart_view.sum())
    payment_attempts = len(selected_orders)
    failed_payments = int((selected_orders.payment_status == "Failed").sum())
    return {
        "sessions": len(sessions),
        "completed_orders": completed_orders,
        "overall_conversion_pct": safe_percentage(completed_orders, len(sessions)),
        "cart_abandonment_pct": None if not cart_views else 100 * (1 - checkout_starts / cart_views),
        "checkout_completion_pct": safe_percentage(completed_orders, checkout_starts),
        "payment_failure_pct": safe_percentage(failed_payments, payment_attempts),
        "average_order_value": None if successful.empty else float(successful.order_value.mean()),
        "synthetic_revenue": float(successful.order_value.sum()),
    }


def build_funnel(sessions: pd.DataFrame) -> pd.DataFrame:
    counts = [int(sessions[column].sum()) for column in STAGE_COLUMNS]
    rows = []
    first_count = counts[0] if counts else 0
    for index, (stage, count) in enumerate(zip(STAGE_LABELS, counts)):
        next_count = counts[index + 1] if index + 1 < len(counts) else None
        rows.append({
            "stage_order": index + 1,
            "stage": stage,
            "sessions": count,
            "percent_of_app_opens": safe_percentage(count, first_count),
            "next_stage_conversion_pct": safe_percentage(next_count, count) if next_count is not None else None,
            "dropoff_sessions": count - next_count if next_count is not None else None,
            "dropoff_pct": safe_percentage(count - next_count, count) if next_count is not None else None,
        })
    return pd.DataFrame(rows)


def largest_dropoff(funnel: pd.DataFrame) -> pd.Series | None:
    candidates = funnel.dropna(subset=["dropoff_pct"])
    if candidates.empty or candidates.sessions.max() == 0:
        return None
    return candidates.loc[candidates.dropoff_pct.idxmax()]


def segment_performance(sessions: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if sessions.empty:
        return pd.DataFrame(columns=["segment", "sessions", "completed_orders", "conversion_pct", "checkout_completion_pct"])
    rows = []
    for segment, group in sessions.groupby(dimension, observed=True):
        rows.append({
            "segment": str(segment),
            "sessions": len(group),
            "completed_orders": int(group.order_completed.sum()),
            "conversion_pct": safe_percentage(group.order_completed.sum(), len(group)),
            "checkout_completion_pct": safe_percentage(group.order_completed.sum(), group.checkout_started.sum()),
        })
    return pd.DataFrame(rows).sort_values("conversion_pct", ascending=False, ignore_index=True)


def delivery_fee_performance(sessions: pd.DataFrame) -> pd.DataFrame:
    cart_sessions = sessions.loc[sessions.cart_view == 1]
    rows = []
    for fee_band in FEE_BAND_ORDER:
        group = cart_sessions.loc[cart_sessions.delivery_fee_band.astype(str) == fee_band]
        if group.empty:
            continue
        checkout_starts = int(group.checkout_started.sum())
        rows.append({
            "fee_band": fee_band,
            "cart_view_sessions": len(group),
            "checkout_starts": checkout_starts,
            "cart_to_checkout_pct": safe_percentage(checkout_starts, len(group)),
            "cart_abandonment_pct": 100 * (1 - checkout_starts / len(group)),
        })
    return pd.DataFrame(rows)


def payment_performance(sessions: pd.DataFrame, orders: pd.DataFrame, dimension: str) -> pd.DataFrame:
    selected = orders.loc[orders.session_id.isin(sessions.session_id)].merge(
        sessions[["session_id", dimension]], on="session_id", how="left"
    )
    rows = []
    for segment, group in selected.groupby(dimension):
        rows.append({
            "segment": str(segment),
            "payment_attempts": len(group),
            "failed_payments": int((group.payment_status == "Failed").sum()),
            "payment_failure_pct": safe_percentage((group.payment_status == "Failed").sum(), len(group)),
        })
    if not rows:
        return pd.DataFrame(columns=["segment", "payment_attempts", "failed_payments", "payment_failure_pct"])
    return pd.DataFrame(rows).sort_values("payment_failure_pct", ascending=False, ignore_index=True)


def payment_method_performance(sessions: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    selected = orders.loc[orders.session_id.isin(sessions.session_id)]
    rows = []
    for method, group in selected.groupby("payment_method"):
        rows.append({
            "segment": method,
            "payment_attempts": len(group),
            "failed_payments": int((group.payment_status == "Failed").sum()),
            "payment_failure_pct": safe_percentage((group.payment_status == "Failed").sum(), len(group)),
        })
    if not rows:
        return pd.DataFrame(columns=["segment", "payment_attempts", "failed_payments", "payment_failure_pct"])
    return pd.DataFrame(rows).sort_values("payment_failure_pct", ascending=False, ignore_index=True)


def revenue_impact(sessions: pd.DataFrame, recovery_pct: float) -> dict[str, float | int | str | None]:
    checkout_transitions = []
    checkout_stage_indexes = range(4, len(STAGE_COLUMNS) - 1)
    for index in checkout_stage_indexes:
        from_column, next_column = STAGE_COLUMNS[index], STAGE_COLUMNS[index + 1]
        losses = sessions.loc[(sessions[from_column] == 1) & (sessions[next_column] == 0)]
        checkout_transitions.append((index, losses))
    largest_index, largest_losses = max(checkout_transitions, key=lambda item: len(item[1]))
    abandonment = sessions.loc[(sessions.cart_view == 1) & (sessions.order_completed == 0)]
    downstream_completion = safe_percentage(sessions.order_completed.sum(), sessions.checkout_started.sum())
    downstream_rate = 0 if downstream_completion is None else downstream_completion / 100
    largest_value = float(largest_losses.cart_value.sum())
    return {
        "largest_checkout_transition": f"{STAGE_LABELS[largest_index]} → {STAGE_LABELS[largest_index + 1]}",
        "largest_stage_dropoff_sessions": len(largest_losses),
        "cart_abandonment_value": float(abandonment.cart_value.sum()),
        "largest_stage_value": largest_value,
        "downstream_completion_pct": downstream_completion,
        "recovery_pct": recovery_pct,
        "opportunity": largest_value * recovery_pct / 100 * downstream_rate,
    }
