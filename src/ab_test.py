import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

from build_database import ROOT


SEED = 2025
N_PER_VARIANT = 4500
ALPHA = 0.05
TABLE_DIR = ROOT / "outputs" / "tables"
CHART_DIR = ROOT / "outputs" / "charts"
PROCESSED_DIR = ROOT / "data" / "processed"


def simulate_experiment() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    variants = np.repeat(["Control", "Treatment"], N_PER_VARIANT)
    rng.shuffle(variants)
    rows = []
    for index, variant in enumerate(variants, start=1):
        treatment = variant == "Treatment"
        checkout_started = rng.random() < (0.815 if treatment else 0.780)
        payment_attempt = checkout_started and rng.random() < 0.95
        payment_failed = payment_attempt and rng.random() < (0.102 if treatment else 0.105)
        order_completed = payment_attempt and not payment_failed
        order_value = round(float(np.clip(rng.lognormal(np.log(755 if treatment else 760), 0.34), 180, 2300)), 2) if order_completed else 0.0
        rows.append({
            "experiment_session_id": f"EXP{index:05d}", "variant": variant,
            "checkout_started": int(checkout_started), "payment_attempt": int(payment_attempt),
            "payment_failed": int(payment_failed), "order_completed": int(order_completed),
            "order_value": order_value,
        })
    return pd.DataFrame(rows)


def two_proportion_test(control_success: int, control_n: int, treatment_success: int, treatment_n: int) -> dict[str, float | bool]:
    control_rate = control_success / control_n
    treatment_rate = treatment_success / treatment_n
    difference = treatment_rate - control_rate
    pooled = (control_success + treatment_success) / (control_n + treatment_n)
    pooled_se = np.sqrt(pooled * (1 - pooled) * (1 / control_n + 1 / treatment_n))
    z_statistic = difference / pooled_se
    p_value = 2 * norm.sf(abs(z_statistic))
    unpooled_se = np.sqrt(control_rate * (1 - control_rate) / control_n + treatment_rate * (1 - treatment_rate) / treatment_n)
    critical = norm.ppf(1 - ALPHA / 2)
    return {
        "control_conversion_pct": 100 * control_rate,
        "treatment_conversion_pct": 100 * treatment_rate,
        "absolute_uplift_pp": 100 * difference,
        "relative_uplift_pct": 100 * difference / control_rate,
        "ci_95_lower_pp": 100 * (difference - critical * unpooled_se),
        "ci_95_upper_pp": 100 * (difference + critical * unpooled_se),
        "z_statistic": z_statistic,
        "p_value": p_value,
        "alpha": ALPHA,
        "statistically_significant": bool(p_value < ALPHA),
    }


def run_experiment() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    experiment = simulate_experiment()
    assert experiment.experiment_session_id.is_unique
    assert len(experiment) == 2 * N_PER_VARIANT
    assert set(experiment.variant) == {"Control", "Treatment"}
    assert (experiment.order_completed <= experiment.payment_attempt).all()
    assert (experiment.payment_attempt <= experiment.checkout_started).all()
    experiment.to_csv(PROCESSED_DIR / "experiment.csv", index=False)

    rows = []
    for variant, group in experiment.groupby("variant"):
        attempts = group.payment_attempt.sum()
        rows.append({
            "variant": variant, "eligible_sessions": len(group),
            "checkout_starts": int(group.checkout_started.sum()),
            "payment_attempts": int(attempts), "completed_orders": int(group.order_completed.sum()),
            "conversion_pct": 100 * group.order_completed.mean(),
            "checkout_completion_pct": 100 * group.order_completed.sum() / group.checkout_started.sum(),
            "average_order_value": group.loc[group.order_completed == 1, "order_value"].mean(),
            "payment_failure_pct": 100 * group.payment_failed.sum() / attempts,
        })
    group_summary = pd.DataFrame(rows).sort_values("variant")
    group_summary.to_csv(TABLE_DIR / "ab_test_group_metrics.csv", index=False)

    control = experiment.loc[experiment.variant == "Control"]
    treatment = experiment.loc[experiment.variant == "Treatment"]
    inference = two_proportion_test(int(control.order_completed.sum()), len(control), int(treatment.order_completed.sum()), len(treatment))
    assert np.isclose(inference["absolute_uplift_pp"], group_summary.set_index("variant").loc["Treatment", "conversion_pct"] - group_summary.set_index("variant").loc["Control", "conversion_pct"])
    pd.DataFrame([inference]).to_csv(TABLE_DIR / "ab_test_inference.csv", index=False)
    (TABLE_DIR / "ab_test_summary.json").write_text(json.dumps({"group_metrics": group_summary.to_dict(orient="records"), "inference": inference}, indent=2), encoding="utf-8")

    conversions = group_summary.set_index("variant").loc[["Control", "Treatment"], "conversion_pct"]
    sample_sizes = group_summary.set_index("variant").loc[["Control", "Treatment"], "eligible_sessions"]
    errors = 100 * 1.96 * np.sqrt((conversions / 100) * (1 - conversions / 100) / sample_sizes)
    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    bars = ax.bar(conversions.index, conversions.values, yerr=errors.values, capsize=6, color=["#8A8A8A", "#0C831F"])
    ax.bar_label(bars, labels=[f"{value:.1f}%" for value in conversions], padding=8)
    ax.set_ylim(0, max(conversions) + 12)
    ax.set_ylabel("Order completed / eligible sessions (%)")
    ax.set_title("Simulated A/B Test: 1-Click Reorder & Micro-Cart", weight="bold")
    ax.text(
        0.5, 0.88, f"Uplift {inference['absolute_uplift_pp']:.2f} pp | p={inference['p_value']:.4f}",
        transform=ax.transAxes, ha="center", bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none"},
    )
    fig.tight_layout()
    fig.savefig(CHART_DIR / "ab_test_conversion.png", dpi=160)
    plt.close(fig)
    print(f"Simulated A/B test complete: {inference['absolute_uplift_pp']:.2f} pp uplift, p={inference['p_value']:.4f}.")


if __name__ == "__main__":
    run_experiment()
