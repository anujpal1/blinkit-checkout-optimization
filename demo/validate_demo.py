from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard_data import (
    build_funnel,
    calculate_kpis,
    delivery_fee_performance,
    filter_sessions,
    load_dashboard_data,
    revenue_impact,
)


ROOT = Path(__file__).resolve().parents[1]


def validate_calculations() -> None:
    data = load_dashboard_data(ROOT)
    sessions, orders = data["sessions"], data["orders"]
    calculated = calculate_kpis(sessions, orders)
    expected = data["kpis"].set_index("metric").value
    for metric in [
        "sessions", "completed_orders", "overall_conversion_pct", "cart_abandonment_pct",
        "checkout_completion_pct", "payment_failure_pct", "average_order_value", "synthetic_revenue",
    ]:
        assert np.isclose(calculated[metric], expected[metric]), f"Default dashboard mismatch: {metric}"

    dashboard_funnel = build_funnel(sessions)
    pipeline_funnel = pd.read_csv(ROOT / "outputs" / "tables" / "funnel_stage_counts.csv")
    assert dashboard_funnel.sessions.tolist() == pipeline_funnel.sessions.tolist(), "Funnel counts differ"
    assert np.allclose(
        dashboard_funnel.dropoff_pct.dropna(), pipeline_funnel.dropoff_pct.dropna(), atol=0.01
    ), "Funnel drop-off rates differ"

    dashboard_revenue = revenue_impact(sessions, 10)
    pipeline_revenue = data["revenue"]
    expected_largest = pipeline_revenue.loc[
        pipeline_revenue.estimate.str.contains("Cart View drop-off"), "synthetic_amount"
    ].iloc[0]
    expected_opportunity = pipeline_revenue.loc[
        pipeline_revenue.estimate == "Potential incremental revenue", "synthetic_amount"
    ].iloc[0]
    assert np.isclose(dashboard_revenue["largest_stage_value"], expected_largest)
    assert np.isclose(dashboard_revenue["opportunity"], expected_opportunity)
    assert np.isclose(revenue_impact(sessions, 20)["opportunity"], 2 * expected_opportunity)

    returning = filter_sessions(sessions, {"user_type": "Returning"})
    expected_returning = pd.read_csv(ROOT / "outputs" / "tables" / "user_type_performance.csv")
    expected_count = int(expected_returning.loc[expected_returning.segment == "Returning", "sessions"].iloc[0])
    assert len(returning) == expected_count, "Filtered session count differs"
    assert calculate_kpis(returning, orders)["sessions"] == expected_count

    fee_table = delivery_fee_performance(sessions)
    expected_fees = pd.read_csv(ROOT / "outputs" / "tables" / "delivery_fee_performance.csv")
    assert fee_table.cart_view_sessions.tolist() == expected_fees.cart_view_sessions.tolist()
    assert np.allclose(fee_table.cart_to_checkout_pct, expected_fees.cart_to_checkout_pct, atol=0.01)

    empty = filter_sessions(sessions, {"city": "Not a city"})
    empty_metrics = calculate_kpis(empty, orders)
    assert empty.empty and empty_metrics["overall_conversion_pct"] is None

    experiment = pd.read_csv(ROOT / "data" / "processed" / "experiment.csv")
    experiment_rates = 100 * experiment.groupby("variant").order_completed.mean()
    reported = data["experiment_groups"].set_index("variant").conversion_pct
    assert np.allclose(experiment_rates.sort_index(), reported.sort_index())


def validate_streamlit_app() -> None:
    app = AppTest.from_file(str(ROOT / "demo" / "app.py"), default_timeout=45).run()
    assert not app.exception, f"Streamlit default render failed: {app.exception}"
    assert app.title[0].value == "Blinkit Checkout Funnel Optimization"
    assert len(app.sidebar.selectbox) == 5

    app.sidebar.selectbox[0].set_value("Returning")
    app.run()
    assert not app.exception, f"Streamlit filtered render failed: {app.exception}"
    assert not any("Returning and Returning" in item.value for item in app.markdown)

    app.slider[0].set_value(15)
    app.run()
    assert not app.exception, f"Streamlit slider render failed: {app.exception}"

    app.sidebar.button[0].click()
    app.run()
    assert not app.exception, f"Streamlit reset failed: {app.exception}"


if __name__ == "__main__":
    validate_calculations()
    validate_streamlit_app()
    print("Streamlit validation passed: calculations, filters, reset, slider, experiment, and default render are consistent.")
