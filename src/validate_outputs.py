import re
import sqlite3
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pandas as pd
from scipy.stats import norm

from build_database import DATABASE_PATH, ROOT


TABLE_DIR = ROOT / "outputs" / "tables"
CHART_DIR = ROOT / "outputs" / "charts"


def validate_outputs() -> None:
    required = [
        ROOT / "README.md", ROOT / "INTERVIEW_NOTES.md",
        ROOT / "dashboard" / "dashboard_guide.md", ROOT / "design" / "checkout_redesign.md",
        ROOT / "demo" / "app.py", ROOT / "demo" / "dashboard_data.py",
        DATABASE_PATH, ROOT / "data" / "processed" / "experiment.csv",
        TABLE_DIR / "funnel_stage_counts.csv", TABLE_DIR / "kpi_summary.csv",
        TABLE_DIR / "revenue_impact.csv", TABLE_DIR / "root_cause_summary.csv",
        TABLE_DIR / "ab_test_group_metrics.csv", TABLE_DIR / "ab_test_inference.csv",
        CHART_DIR / "funnel_overview.png", CHART_DIR / "segment_conversion.png",
        CHART_DIR / "delivery_fee_abandonment.png", CHART_DIR / "ab_test_conversion.png",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists() or path.stat().st_size == 0]
    assert not missing, f"Missing or empty outputs: {missing}"

    with sqlite3.connect(DATABASE_PATH) as connection:
        for table in ["users", "sessions", "events", "orders"]:
            database_count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            csv_count = len(pd.read_csv(ROOT / "data" / "raw" / f"{table}.csv"))
            assert database_count == csv_count, f"Database/CSV count mismatch for {table}"

    funnel = pd.read_csv(TABLE_DIR / "funnel_stage_counts.csv")
    assert funnel.sessions.is_monotonic_decreasing, "Funnel output is not monotonic"
    cart = float(funnel.loc[funnel.stage == "Cart View", "sessions"].iloc[0])
    checkout = float(funnel.loc[funnel.stage == "Checkout Started", "sessions"].iloc[0])
    completed = float(funnel.loc[funnel.stage == "Order Completed", "sessions"].iloc[0])
    calculated_cart_abandonment = 100 * (1 - checkout / cart)
    calculated_checkout_completion = 100 * completed / checkout
    kpis = pd.read_csv(TABLE_DIR / "kpi_summary.csv").set_index("metric").value
    assert np.isclose(calculated_cart_abandonment, kpis["cart_abandonment_pct"])
    assert np.isclose(calculated_checkout_completion, kpis["checkout_completion_pct"])

    session_funnel = pd.read_csv(TABLE_DIR / "session_funnel.csv")
    largest_stage_value = session_funnel.loc[(session_funnel.cart_view == 1) & (session_funnel.checkout_started == 0), "cart_value"].sum()
    revenue = pd.read_csv(TABLE_DIR / "revenue_impact.csv")
    reported_stage_value = revenue.loc[revenue.estimate.str.contains("Cart View drop-off"), "synthetic_amount"].iloc[0]
    assert np.isclose(largest_stage_value, reported_stage_value), "Revenue-stage estimate mismatch"

    experiment = pd.read_csv(ROOT / "data" / "processed" / "experiment.csv")
    assert experiment.groupby("variant").size().to_dict() == {"Control": 4500, "Treatment": 4500}
    successes = experiment.groupby("variant").order_completed.sum()
    n = experiment.groupby("variant").size()
    control_rate = successes.Control / n.Control
    treatment_rate = successes.Treatment / n.Treatment
    pooled = successes.sum() / n.sum()
    z_score = (treatment_rate - control_rate) / np.sqrt(pooled * (1 - pooled) * (1 / n.Control + 1 / n.Treatment))
    p_value = 2 * norm.sf(abs(z_score))
    inference = pd.read_csv(TABLE_DIR / "ab_test_inference.csv").iloc[0]
    assert np.isclose(p_value, inference.p_value), "A/B p-value mismatch"
    assert np.isclose(100 * (treatment_rate - control_rate), inference.absolute_uplift_pp), "A/B uplift mismatch"
    assert inference.ci_95_lower_pp < inference.absolute_uplift_pp < inference.ci_95_upper_pp

    for chart_path in CHART_DIR.glob("*.png"):
        image = mpimg.imread(chart_path)
        assert image.ndim in (2, 3) and image.size > 0, f"Unreadable chart: {chart_path.name}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notes = (ROOT / "INTERVIEW_NOTES.md").read_text(encoding="utf-8")
    assert "synthetic data" in readme.lower() and "simulated" in readme.lower() and "no Blinkit internal data" in readme
    resume_section = notes.split("## Three resume bullets", 1)[1].split("## Honest limitations", 1)[0]
    assert len(re.findall(r"^- ", resume_section, flags=re.MULTILINE)) == 3, "Resume bullet count must be exactly three"
    assert len(re.findall(r"^\d+\. \*\*", notes, flags=re.MULTILINE)) == 20, "Expected 20 interview questions"

    print("Final validation passed: required artifacts, DB counts, formulas, experiment statistics, charts, and documentation are consistent.")


if __name__ == "__main__":
    validate_outputs()
