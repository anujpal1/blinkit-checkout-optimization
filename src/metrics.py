import json
import re
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from build_database import DATABASE_PATH, ROOT


TABLE_DIR = ROOT / "outputs" / "tables"
CHART_DIR = ROOT / "outputs" / "charts"
STAGES = [
    "App Open", "Search", "Product View", "Add to Cart", "Cart View",
    "Checkout Started", "Payment Attempt", "Order Completed",
]


def parse_named_queries(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^-- name: ([\w_]+)\s*$", text, flags=re.MULTILINE))
    queries = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        queries[match.group(1)] = text[start:end].strip().rstrip(";")
    return queries


def session_funnel(connection: sqlite3.Connection) -> pd.DataFrame:
    flags = pd.read_sql_query(
        """
        SELECT s.session_id, s.user_id, s.session_start, s.device, s.city,
               u.user_type, u.acquisition_channel, s.cart_value, s.delivery_fee,
               MAX(e.event_name = 'App Open') AS app_open,
               MAX(e.event_name = 'Search') AS search,
               MAX(e.event_name = 'Product View') AS product_view,
               MAX(e.event_name = 'Add to Cart') AS add_to_cart,
               MAX(e.event_name = 'Cart View') AS cart_view,
               MAX(e.event_name = 'Checkout Started') AS checkout_started,
               MAX(e.event_name = 'Payment Attempt') AS payment_attempt,
               MAX(e.event_name = 'Order Completed') AS order_completed
        FROM sessions s
        JOIN users u ON u.user_id = s.user_id
        JOIN events e ON e.session_id = s.session_id
        GROUP BY s.session_id
        """,
        connection,
    )
    return flags


def validate_metrics(connection: sqlite3.Connection, funnel: pd.DataFrame, sql_results: dict[str, pd.DataFrame]) -> dict[str, float]:
    stage_columns = [stage.lower().replace(" ", "_") for stage in STAGES]
    python_counts = funnel[stage_columns].sum().astype(int).tolist()
    sql_counts = sql_results["funnel_stage_counts"].sessions.astype(int).tolist()
    assert python_counts == sql_counts, f"Python/SQL funnel counts differ: {python_counts} vs {sql_counts}"
    assert all(left >= right for left, right in zip(python_counts, python_counts[1:])), "Funnel counts are not monotonic"

    orders = pd.read_sql_query("SELECT * FROM orders", connection)
    completed = int(funnel.order_completed.sum())
    checkout_starts = int(funnel.checkout_started.sum())
    cart_views = int(funnel.cart_view.sum())
    payment_attempts = len(orders)
    failed_payments = int((orders.payment_status == "Failed").sum())
    successful = orders.loc[orders.payment_status == "Success"]
    metrics = {
        "sessions": len(funnel),
        "completed_orders": completed,
        "overall_conversion_pct": 100 * completed / len(funnel),
        "checkout_completion_pct": 100 * completed / checkout_starts,
        "cart_abandonment_pct": 100 * (1 - checkout_starts / cart_views),
        "payment_failure_pct": 100 * failed_payments / payment_attempts,
        "average_order_value": successful.order_value.mean(),
        "synthetic_revenue": successful.order_value.sum(),
    }
    sql_row = sql_results["core_product_metrics"].iloc[0]
    for name in ["completed_orders", "overall_conversion_pct", "checkout_completion_pct", "cart_abandonment_pct", "payment_failure_pct", "average_order_value", "synthetic_revenue"]:
        assert np.isclose(round(metrics[name], 2), float(sql_row[name]), atol=0.01), f"SQL/Python mismatch for {name}"
    return metrics


def repeat_metrics(connection: sqlite3.Connection) -> dict[str, float]:
    successful = pd.read_sql_query("SELECT user_id, order_value FROM orders WHERE payment_status = 'Success'", connection)
    orders_per_user = successful.groupby("user_id").size()
    return {
        "purchasing_users": int(len(orders_per_user)),
        "repeat_purchasers": int((orders_per_user >= 2).sum()),
        "repeat_purchaser_pct": 100 * (orders_per_user >= 2).mean(),
        "orders_per_purchaser": orders_per_user.mean(),
    }


def revenue_analysis(funnel: pd.DataFrame, funnel_table: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | str]]:
    checkout_rows = funnel_table.loc[funnel_table.stage_order >= 5].dropna(subset=["dropoff_sessions"])
    largest = checkout_rows.sort_values("dropoff_sessions", ascending=False).iloc[0]
    stage_from = str(largest.stage)
    next_stage = STAGES[STAGES.index(stage_from) + 1]
    from_column = stage_from.lower().replace(" ", "_")
    next_column = next_stage.lower().replace(" ", "_")
    stage_losses = funnel.loc[(funnel[from_column] == 1) & (funnel[next_column] == 0)]
    abandonment = funnel.loc[(funnel.cart_view == 1) & (funnel.order_completed == 0)]
    post_checkout_completion = funnel.order_completed.sum() / funnel.checkout_started.sum()
    opportunity = stage_losses.cart_value.sum() * 0.10 * post_checkout_completion
    result = {
        "largest_checkout_transition": f"{stage_from} -> {next_stage}",
        "largest_stage_dropoff_sessions": int(len(stage_losses)),
        "estimated_cart_value_associated_with_all_cart_abandonment": float(abandonment.cart_value.sum()),
        "estimated_cart_value_associated_with_largest_stage": float(stage_losses.cart_value.sum()),
        "assumed_recovery_pct": 10.0,
        "observed_post_checkout_completion_pct": 100 * post_checkout_completion,
        "estimated_incremental_revenue_opportunity": float(opportunity),
    }
    table = pd.DataFrame([
        {"estimate": "Cart value associated with all post-cart abandonment", "synthetic_amount": result["estimated_cart_value_associated_with_all_cart_abandonment"], "formula": "Sum(cart value) for Cart View sessions without Order Completed"},
        {"estimate": f"Cart value associated with {stage_from} drop-off", "synthetic_amount": result["estimated_cart_value_associated_with_largest_stage"], "formula": f"Sum(cart value) for {stage_from} sessions not reaching {next_stage}"},
        {"estimate": "Potential incremental revenue", "synthetic_amount": result["estimated_incremental_revenue_opportunity"], "formula": "Largest-stage cart value x 10% recovery x observed post-checkout completion"},
    ])
    return table, result


def build_root_cause_table(sql_results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    user_type = sql_results["user_type_performance"].set_index("segment")
    fees = sql_results["delivery_fee_performance"].set_index("segment")
    cities = sql_results["city_performance"].set_index("segment")
    devices = sql_results["device_payment_performance"].set_index("segment")
    methods = sql_results["payment_method_performance"].set_index("segment")
    best_city = cities.cart_to_checkout_pct.idxmax()
    best_method = methods.payment_failure_pct.idxmin()
    worst_method = methods.payment_failure_pct.idxmax()
    rows = [
        {
            "potential_driver": "New-user checkout friction",
            "comparison": "New vs Returning",
            "metric": "Cart-to-checkout conversion",
            "lower_group_pct": user_type.loc["New", "cart_to_checkout_pct"],
            "comparison_group_pct": user_type.loc["Returning", "cart_to_checkout_pct"],
            "gap_pp": user_type.loc["Returning", "cart_to_checkout_pct"] - user_type.loc["New", "cart_to_checkout_pct"],
        },
        {
            "potential_driver": "High delivery fee",
            "comparison": "High (51+) vs Free",
            "metric": "Cart-to-checkout conversion",
            "lower_group_pct": fees.loc["High (51+)", "cart_to_checkout_pct"],
            "comparison_group_pct": fees.loc["Free", "cart_to_checkout_pct"],
            "gap_pp": fees.loc["Free", "cart_to_checkout_pct"] - fees.loc["High (51+)", "cart_to_checkout_pct"],
        },
        {
            "potential_driver": "Kolkata checkout friction",
            "comparison": f"Kolkata vs {best_city}",
            "metric": "Cart-to-checkout conversion",
            "lower_group_pct": cities.loc["Kolkata", "cart_to_checkout_pct"],
            "comparison_group_pct": cities.loc[best_city, "cart_to_checkout_pct"],
            "gap_pp": cities.loc[best_city, "cart_to_checkout_pct"] - cities.loc["Kolkata", "cart_to_checkout_pct"],
        },
        {
            "potential_driver": "Android payment reliability",
            "comparison": "Android vs iOS",
            "metric": "Payment failure rate",
            "lower_group_pct": devices.loc["Android", "payment_failure_pct"],
            "comparison_group_pct": devices.loc["iOS", "payment_failure_pct"],
            "gap_pp": devices.loc["Android", "payment_failure_pct"] - devices.loc["iOS", "payment_failure_pct"],
        },
        {
            "potential_driver": "Payment-method reliability",
            "comparison": f"{worst_method} vs {best_method}",
            "metric": "Payment failure rate",
            "lower_group_pct": methods.loc[worst_method, "payment_failure_pct"],
            "comparison_group_pct": methods.loc[best_method, "payment_failure_pct"],
            "gap_pp": methods.loc[worst_method, "payment_failure_pct"] - methods.loc[best_method, "payment_failure_pct"],
        },
    ]
    return pd.DataFrame(rows)


def save_charts(funnel_counts: pd.DataFrame, sql_results: dict[str, pd.DataFrame]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    blinkit_yellow, blinkit_green, dark = "#F8CB2E", "#0C831F", "#303030"

    chart = funnel_counts.sort_values("stage_order", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.barh(chart.stage, chart.sessions, color=blinkit_green)
    for i, value in enumerate(chart.sessions):
        ax.text(value + chart.sessions.max() * 0.01, i, f"{int(value):,}", va="center", fontsize=9)
    ax.set_title("Checkout Funnel: Sessions Reaching Each Stage", weight="bold")
    ax.set_xlabel("Sessions")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "funnel_overview.png", dpi=160)
    plt.close(fig)

    frames = []
    for label, key in [("User type", "user_type_performance"), ("Device", "device_performance"), ("City", "city_performance")]:
        part = sql_results[key][["segment", "overall_conversion_pct"]].copy()
        part["dimension"] = label
        frames.append(part)
    segments = pd.concat(frames, ignore_index=True).sort_values("overall_conversion_pct")
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = [blinkit_green if dimension != "City" else blinkit_yellow for dimension in segments.dimension]
    ax.barh(segments.segment, segments.overall_conversion_pct, color=colors)
    ax.set_title("Overall Conversion by Key Segment", weight="bold")
    ax.set_xlabel("Order completed / sessions (%)")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "segment_conversion.png", dpi=160)
    plt.close(fig)

    fees = sql_results["delivery_fee_performance"]
    abandonment = 100 - fees.cart_to_checkout_pct
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(fees.segment, abandonment, color=[blinkit_green, blinkit_green, blinkit_yellow, "#E85D5D"])
    ax.bar_label(bars, fmt="%.1f%%", padding=3)
    ax.set_ylim(0, max(abandonment) + 8)
    ax.set_title("Cart Abandonment Rises with Delivery Fee", weight="bold")
    ax.set_ylabel("Cart abandonment (%)")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "delivery_fee_abandonment.png", dpi=160)
    plt.close(fig)


def run_analysis() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sql_results: dict[str, pd.DataFrame] = {}
    with sqlite3.connect(DATABASE_PATH) as connection:
        for sql_file in [ROOT / "sql" / "funnel_analysis.sql", ROOT / "sql" / "segment_analysis.sql"]:
            for name, query in parse_named_queries(sql_file).items():
                frame = pd.read_sql_query(query, connection)
                frame.to_csv(TABLE_DIR / f"{name}.csv", index=False)
                sql_results[name] = frame
        funnel = session_funnel(connection)
        funnel.to_csv(TABLE_DIR / "session_funnel.csv", index=False)
        successful_orders = pd.read_sql_query("SELECT * FROM orders WHERE payment_status = 'Success'", connection)
        successful_orders.to_csv(TABLE_DIR / "successful_orders.csv", index=False)
        metrics = validate_metrics(connection, funnel, sql_results)
        repeats = repeat_metrics(connection)

    definitions = {
        "sessions": "Distinct sessions",
        "completed_orders": "Sessions reaching Order Completed",
        "overall_conversion_pct": "Order Completed / all sessions x 100",
        "checkout_completion_pct": "Order Completed / Checkout Started x 100",
        "cart_abandonment_pct": "(1 - Checkout Started / Cart View) x 100",
        "payment_failure_pct": "Failed payment records / all payment attempts x 100",
        "average_order_value": "Successful order value / successful orders",
        "synthetic_revenue": "Sum of successful order value",
        "repeat_purchaser_pct": "Purchasers with 2+ completed orders / purchasing users x 100",
    }
    kpis = {**metrics, **repeats}
    pd.DataFrame([{"metric": key, "value": value, "definition": definitions.get(key, "Supporting metric")} for key, value in kpis.items()]).to_csv(TABLE_DIR / "kpi_summary.csv", index=False)

    revenue_table, revenue = revenue_analysis(funnel, sql_results["funnel_stage_counts"])
    revenue_table.to_csv(TABLE_DIR / "revenue_impact.csv", index=False)
    root_causes = build_root_cause_table(sql_results)
    root_causes.to_csv(TABLE_DIR / "root_cause_summary.csv", index=False)
    save_charts(sql_results["funnel_stage_counts"], sql_results)

    summary = {"metrics": kpis, "revenue_impact": revenue, "root_causes": root_causes.to_dict(orient="records")}
    (TABLE_DIR / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Executed {len(sql_results)} SQL analyses; Python/SQL metric checks passed; exported tables and 3 charts.")


if __name__ == "__main__":
    run_analysis()
