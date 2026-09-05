from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from dashboard_data import (
    FEE_BAND_ORDER,
    STAGE_COLUMNS,
    STAGE_LABELS,
    build_funnel,
    calculate_kpis,
    delivery_fee_performance,
    filter_sessions,
    largest_dropoff,
    load_dashboard_data,
    payment_method_performance,
    payment_performance,
    required_files,
    revenue_impact,
    segment_performance,
)


ROOT = Path(__file__).resolve().parents[1]
GREEN = "#0C831F"
YELLOW = "#F8CB2E"
RED = "#E85D5D"
GREY = "#7A7A7A"

st.set_page_config(
    page_title="Blinkit Checkout Funnel Optimization",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 1.7rem; padding-bottom: 3rem;}
    .project-subtitle {font-size: 1.18rem; color: #4a4a4a; margin-top: -0.6rem;}
    .scope-banner {background: #fff8d9; border-left: 5px solid #f8cb2e; padding: 0.8rem 1rem; border-radius: 0.35rem; margin: 1rem 0 1.2rem;}
    .recommendation {background: #f2fbf4; border: 1px solid #b9dfbf; border-left: 6px solid #0c831f; padding: 1.1rem 1.2rem; border-radius: 0.45rem;}
    .section-note {color: #5c5c5c; font-size: 0.92rem;}
    div[data-testid="stMetric"] {background: #ffffff; border: 1px solid #e6e6e6; border-radius: 0.45rem; padding: 0.7rem 0.8rem;}
    @media (max-width: 900px) {
        div[data-testid="stMetricValue"] {font-size: 1.35rem;}
        div[data-testid="stMetricLabel"] p {font-size: 0.72rem;}
        .block-container {padding-left: 1rem; padding-right: 1rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def format_pct(value: float | None) -> str:
    return "N/A" if value is None or pd.isna(value) else f"{value:.2f}%"


def format_currency(value: float | None) -> str:
    return "N/A" if value is None or pd.isna(value) else f"₹{value:,.2f}"


def format_compact_currency(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if abs(value) >= 1_000_000:
        return f"₹{value / 1_000_000:.2f}M"
    if abs(value) >= 100_000:
        return f"₹{value / 1_000:.1f}K"
    return format_currency(value)


def rate_chart(
    frame: pd.DataFrame,
    label_column: str,
    rate_column: str,
    title: str,
    x_label: str,
    highlight_worst: bool = False,
    higher_is_worse: bool = False,
) -> plt.Figure:
    chart = frame.sort_values(rate_column, ascending=True).copy()
    colors = [GREEN] * len(chart)
    if highlight_worst and len(chart):
        colors[-1 if higher_is_worse else 0] = RED
    figure, axis = plt.subplots(figsize=(8.2, max(3.2, 0.48 * len(chart) + 1.7)))
    bars = axis.barh(chart[label_column].astype(str), chart[rate_column], color=colors)
    axis.bar_label(bars, labels=[f"{value:.1f}%" for value in chart[rate_column]], padding=4, fontsize=9)
    axis.set_xlim(0, max(10, chart[rate_column].max() * 1.18))
    axis.set_xlabel(x_label)
    axis.set_title(title, loc="left", weight="bold")
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.grid(axis="x", alpha=0.22)
    axis.grid(axis="y", visible=False)
    figure.tight_layout()
    return figure


def funnel_chart(funnel: pd.DataFrame, largest: pd.Series | None) -> plt.Figure:
    chart = funnel.sort_values("stage_order", ascending=False)
    highlight_stage = None if largest is None else largest.stage
    colors = [YELLOW if stage == highlight_stage else GREEN for stage in chart.stage]
    figure, axis = plt.subplots(figsize=(9.2, 5.3))
    bars = axis.barh(chart.stage, chart.sessions, color=colors)
    max_sessions = max(1, chart.sessions.max())
    for bar, value in zip(bars, chart.sessions):
        axis.text(value + max_sessions * 0.012, bar.get_y() + bar.get_height() / 2, f"{int(value):,}", va="center", fontsize=9)
    axis.set_xlim(0, max_sessions * 1.15)
    axis.set_xlabel("Selected sessions reaching stage")
    axis.set_title("Filtered Checkout Funnel", loc="left", weight="bold")
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.grid(axis="x", alpha=0.22)
    axis.grid(axis="y", visible=False)
    figure.tight_layout()
    return figure


paths = required_files(ROOT)
missing_files = [str(path.relative_to(ROOT)) for path in paths.values() if not path.exists()]
if missing_files:
    st.error("Project outputs not found. Build the validated analytics outputs first:")
    st.code("python src/run_project.py", language="powershell")
    st.caption("Missing: " + ", ".join(missing_files))
    st.stop()


@st.cache_data(show_spinner=False)
def cached_data(root_text: str) -> dict[str, pd.DataFrame]:
    return load_dashboard_data(Path(root_text))


data = cached_data(str(ROOT))
all_sessions = data["sessions"]
orders = data["orders"]

st.title("Blinkit Checkout Funnel Optimization")
st.markdown('<div class="project-subtitle">Blinkit-inspired Product Analytics Case Study</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="scope-banner"><strong>Synthetic data</strong> &nbsp;•&nbsp; '
    '<strong>Simulated experiment</strong> &nbsp;•&nbsp; '
    '<strong>No real Blinkit internal data</strong><br>'
    'Identify where users abandon checkout, investigate affected segments, estimate synthetic value impact, '
    'and evaluate a proposed checkout improvement.</div>',
    unsafe_allow_html=True,
)


filter_columns = {
    "filter_user_type": ("User Type", "user_type"),
    "filter_device": ("Device", "device"),
    "filter_city": ("City", "city"),
    "filter_channel": ("Acquisition Channel", "acquisition_channel"),
    "filter_fee": ("Delivery Fee Band", "delivery_fee_band"),
}
st.sidebar.header("Segment filters")
if st.sidebar.button("Reset filters", width="stretch"):
    for key in filter_columns:
        st.session_state[key] = "All"
    st.rerun()

selected_filters = {}
for key, (label, column) in filter_columns.items():
    if column == "delivery_fee_band":
        values = FEE_BAND_ORDER
    else:
        values = sorted(all_sessions[column].dropna().astype(str).unique())
    selected_filters[column] = st.sidebar.selectbox(label, ["All", *values], key=key)

selected_sessions = filter_sessions(all_sessions, selected_filters)
st.sidebar.metric("Selected Sessions", f"{len(selected_sessions):,}")
st.sidebar.caption("Every rate below uses the selected-session denominator unless marked as experiment-wide.")

if selected_sessions.empty:
    st.warning("No sessions match this filter combination. Reset one or more filters to continue.")
    st.stop()
if len(selected_sessions) < 100:
    st.warning("This selection contains fewer than 100 sessions. Treat percentage comparisons as directional.")


st.header("1. Data scope")
event_count = int(all_sessions[STAGE_COLUMNS].sum().sum())
scope_columns = st.columns(4)
scope_columns[0].metric("Users", f"{all_sessions.user_id.nunique():,}")
scope_columns[1].metric("Sessions", f"{len(all_sessions):,}")
scope_columns[2].metric("Events", f"{event_count:,}")
scope_columns[3].metric("Completed Orders", f"{int(all_sessions.order_completed.sum()):,}")
with st.container(border=True):
    start_date = all_sessions.session_start.min().strftime("%d %b %Y")
    end_date = all_sessions.session_start.max().strftime("%d %b %Y")
    st.markdown(
        f"**Coverage:** {start_date} to {end_date}  ·  "
        f"**Cities:** {all_sessions.city.nunique()}  ·  "
        f"**Devices:** {all_sessions.device.nunique()}  ·  "
        f"**Acquisition channels:** {all_sessions.acquisition_channel.nunique()}"
    )


st.header("2. Selected-segment KPIs")
kpis = calculate_kpis(selected_sessions, orders)
kpi_values = [
    ("Sessions", f"{kpis['sessions']:,}"),
    ("Completed Orders", f"{kpis['completed_orders']:,}"),
    ("Overall Conversion", format_pct(kpis["overall_conversion_pct"])),
    ("Cart Abandonment", format_pct(kpis["cart_abandonment_pct"])),
    ("Checkout Completion", format_pct(kpis["checkout_completion_pct"])),
    ("Payment Failure", format_pct(kpis["payment_failure_pct"])),
    ("Average Order Value", format_currency(kpis["average_order_value"])),
    ("Synthetic Revenue", format_compact_currency(kpis["synthetic_revenue"])),
]
for row in range(2):
    columns = st.columns(4)
    for column, (label, value) in zip(columns, kpi_values[row * 4:(row + 1) * 4]):
        column.metric(label, value)
st.caption("Definitions match the validated pipeline. Payment metrics use payment-attempt records within the selected sessions.")


st.header("3. Funnel performance and biggest drop-off")
funnel = build_funnel(selected_sessions)
largest = largest_dropoff(funnel)
if largest is not None:
    next_stage = STAGE_LABELS[int(largest.stage_order)]
    st.info(
        f"**Largest percentage drop-off:** {largest.stage} → {next_stage}. "
        f"{int(largest.dropoff_sessions):,} sessions drop ({largest.dropoff_pct:.2f}%) for the selected segment."
    )
st.pyplot(funnel_chart(funnel, largest), clear_figure=True, width="stretch")
funnel_display = funnel.copy()
funnel_display["stage_to_stage_conversion"] = funnel_display.next_stage_conversion_pct.map(format_pct)
funnel_display["dropoff_percentage"] = funnel_display.dropoff_pct.map(format_pct)
funnel_display["dropoff_sessions"] = funnel_display.dropoff_sessions.map(lambda value: "—" if pd.isna(value) else f"{int(value):,}")
st.dataframe(
    funnel_display[["stage", "sessions", "stage_to_stage_conversion", "dropoff_sessions", "dropoff_percentage"]],
    hide_index=True,
    width="stretch",
    column_config={
        "stage": "Stage",
        "sessions": st.column_config.NumberColumn("Sessions", format="%d"),
        "stage_to_stage_conversion": "Next-stage conversion",
        "dropoff_sessions": "Drop-off sessions",
        "dropoff_percentage": "Drop-off rate",
    },
)


st.header("4. Segment investigation")
dimension_options = {
    "User Type": "user_type",
    "Device": "device",
    "City": "city",
    "Acquisition Channel": "acquisition_channel",
}
segment_label = st.selectbox("Compare overall conversion by", list(dimension_options), key="segment_dimension")
segment_table = segment_performance(selected_sessions, dimension_options[segment_label])
if len(segment_table) < 2:
    st.warning(f"Only one {segment_label.lower()} is present after filtering. Select All for that sidebar dimension to compare groups.")
else:
    best, worst = segment_table.iloc[0], segment_table.iloc[-1]
    gap = best.conversion_pct - worst.conversion_pct
    st.markdown(
        f"**Best:** {best.segment} ({best.conversion_pct:.2f}%, n={int(best.sessions):,})  ·  "
        f"**Lowest:** {worst.segment} ({worst.conversion_pct:.2f}%, n={int(worst.sessions):,})  ·  "
        f"**Gap:** {gap:.2f} percentage points"
    )
st.pyplot(
    rate_chart(segment_table, "segment", "conversion_pct", f"Conversion by {segment_label}", "Order Completed / Sessions (%)"),
    clear_figure=True,
    width="stretch",
)
st.caption("Segment differences are associations in synthetic observational data; they do not establish causation.")


st.header("5. Root-cause exploration")
root_choice = st.selectbox(
    "Investigate potential contributor",
    ["New vs Returning", "Android vs iOS payment", "City", "Payment Method", "Delivery Fee"],
    key="root_cause_dimension",
)
if root_choice == "New vs Returning":
    root_table = segment_performance(selected_sessions, "user_type")
    rate_column, sample_column = "conversion_pct", "sessions"
    title, axis_label = "Conversion by User Type", "Order Completed / Sessions (%)"
    interpretation = "Returning-user familiarity and saved details appear associated with stronger conversion."
elif root_choice == "Android vs iOS payment":
    root_table = payment_performance(selected_sessions, orders, "device")
    rate_column, sample_column = "payment_failure_pct", "payment_attempts"
    title, axis_label = "Payment Failure by Device", "Failed Payments / Payment Attempts (%)"
    interpretation = "Device-level payment reliability may contribute to losses after checkout starts."
elif root_choice == "City":
    root_table = segment_performance(selected_sessions, "city")
    rate_column, sample_column = "conversion_pct", "sessions"
    title, axis_label = "Conversion by City", "Order Completed / Sessions (%)"
    interpretation = "Geographic differences suggest a useful drill-down, but operational causes would need additional data."
elif root_choice == "Payment Method":
    root_table = payment_method_performance(selected_sessions, orders)
    rate_column, sample_column = "payment_failure_pct", "payment_attempts"
    title, axis_label = "Payment Failure by Method", "Failed Payments / Payment Attempts (%)"
    interpretation = "Higher-failure payment methods are potential contributors to post-checkout loss."
else:
    root_table = delivery_fee_performance(selected_sessions).rename(columns={"fee_band": "segment"})
    rate_column, sample_column = "cart_abandonment_pct", "cart_view_sessions"
    title, axis_label = "Cart Abandonment by Delivery Fee", "1 − Checkout Started / Cart View (%)"
    interpretation = "Higher delivery fees appear associated with more abandonment before checkout starts."

if root_table.empty:
    st.warning("This selection has no observations for the chosen comparison.")
else:
    st.pyplot(
        rate_chart(
            root_table, "segment", rate_column, title, axis_label,
            highlight_worst=True,
            higher_is_worse=rate_column in {"payment_failure_pct", "cart_abandonment_pct"},
        ),
        clear_figure=True,
        width="stretch",
    )
    if len(root_table) < 2:
        st.warning("Only one comparison group remains after filtering. Select All for the related sidebar dimension to calculate a gap.")
    else:
        highest = root_table.loc[root_table[rate_column].idxmax()]
        lowest = root_table.loc[root_table[rate_column].idxmin()]
        st.markdown(
            f"**Potential contributor:** {interpretation} The observed gap between {highest.segment} and "
            f"{lowest.segment} is {highest[rate_column] - lowest[rate_column]:.2f} percentage points "
            f"(sample sizes: {int(highest[sample_column]):,} and {int(lowest[sample_column]):,})."
        )
st.caption("Observational relationships do not establish causation.")


st.header("6. Delivery-fee impact")
fee_table = delivery_fee_performance(selected_sessions)
if fee_table.empty:
    st.warning("No Cart View sessions are available for the selected filters.")
else:
    st.pyplot(
        rate_chart(
            fee_table, "fee_band", "cart_abandonment_pct", "Cart Abandonment by Fee Band",
            "Cart Abandonment (%)", highlight_worst=True, higher_is_worse=True,
        ),
        clear_figure=True,
        width="stretch",
    )
    free_row = fee_table.loc[fee_table.fee_band == "Free"]
    high_row = fee_table.loc[fee_table.fee_band == "High (51+)"]
    if not free_row.empty and not high_row.empty:
        gap = high_row.iloc[0].cart_abandonment_pct - free_row.iloc[0].cart_abandonment_pct
        st.info(f"High-fee carts abandon **{gap:.2f} percentage points** more often than free-delivery carts in this selection.")
    else:
        st.caption("Select All delivery-fee bands to compare Free with High (51+).")
    fee_display = fee_table.rename(columns={
        "fee_band": "Fee band", "cart_view_sessions": "Cart View sessions",
        "cart_to_checkout_pct": "Cart-to-checkout", "cart_abandonment_pct": "Cart abandonment",
    }).copy()
    fee_display["Cart-to-checkout"] = fee_display["Cart-to-checkout"].map(format_pct)
    fee_display["Cart abandonment"] = fee_display["Cart abandonment"].map(format_pct)
    st.dataframe(fee_display[["Fee band", "Cart View sessions", "Cart-to-checkout", "Cart abandonment"]], hide_index=True, width="stretch")


st.header("7. Synthetic revenue impact")
recovery_pct = st.slider("Recovery assumption", min_value=0, max_value=20, value=10, step=1, format="%d%%")
revenue = revenue_impact(selected_sessions, recovery_pct)
revenue_values = [
    ("Synthetic Revenue", format_currency(kpis["synthetic_revenue"])),
    ("Average Order Value", format_currency(kpis["average_order_value"])),
    ("Cart Value After Cart Abandonment", format_currency(revenue["cart_abandonment_value"])),
    ("Largest Checkout-Loss Value", format_currency(revenue["largest_stage_value"])),
]
for row in range(2):
    revenue_columns = st.columns(2)
    for column, (label, value) in zip(revenue_columns, revenue_values[row * 2:(row + 1) * 2]):
        column.metric(label, value)
with st.container(border=True):
    st.subheader("Illustrative Revenue Opportunity")
    st.metric("Scenario estimate", format_currency(revenue["opportunity"]))
    completion_text = format_pct(revenue["downstream_completion_pct"])
    st.markdown(
        f"`{format_currency(revenue['largest_stage_value'])} × {recovery_pct}% recovery × "
        f"{completion_text} observed post-checkout completion`"
    )
    st.caption(
        f"The largest checkout transition by lost sessions is {revenue['largest_checkout_transition']} "
        f"({revenue['largest_stage_dropoff_sessions']:,} sessions). This is a synthetic scenario estimate, not real Blinkit revenue."
    )


st.header("8. Simulated A/B test")
st.markdown("**Treatment:** 1-Click Reorder & Micro-Cart for eligible repeat-customer scenarios")
experiment = data["experiment_groups"].set_index("variant").loc[["Control", "Treatment"]]
inference = data["experiment_inference"].iloc[0]
experiment_columns = st.columns(4)
experiment_columns[0].metric("Control Conversion", format_pct(experiment.loc["Control", "conversion_pct"]))
experiment_columns[1].metric("Treatment Conversion", format_pct(experiment.loc["Treatment", "conversion_pct"]))
experiment_columns[2].metric("Absolute Uplift", f"{inference.absolute_uplift_pp:+.2f} pp")
experiment_columns[3].metric("Relative Uplift", f"{inference.relative_uplift_pct:+.2f}%")

experiment_plot = experiment.reset_index()
figure, axis = plt.subplots(figsize=(7.2, 4.2))
bars = axis.bar(experiment_plot.variant, experiment_plot.conversion_pct, color=[GREY, GREEN], width=0.58)
axis.bar_label(bars, labels=[f"{value:.2f}%" for value in experiment_plot.conversion_pct], padding=5)
axis.set_ylim(0, max(experiment_plot.conversion_pct) + 12)
axis.set_ylabel("Order Completed / Eligible Sessions (%)")
axis.set_title("Control vs Treatment Conversion", loc="left", weight="bold")
axis.spines[["top", "right"]].set_visible(False)
axis.grid(axis="y", alpha=0.22)
figure.tight_layout()
st.pyplot(figure, clear_figure=True, width="stretch")

test_columns = st.columns(4)
test_columns[0].metric("Sample / Group", f"{int(experiment.eligible_sessions.min()):,}")
test_columns[1].metric("95% CI", f"{inference.ci_95_lower_pp:+.2f} to {inference.ci_95_upper_pp:+.2f} pp")
test_columns[2].metric("p-value", f"{inference.p_value:.4f}")
test_columns[3].metric("Significant at α = 0.05", "Yes" if inference.statistically_significant else "No")
guardrails = experiment.reset_index()[["variant", "payment_failure_pct", "average_order_value"]].copy()
guardrails["payment_failure_pct"] = guardrails.payment_failure_pct.map(format_pct)
guardrails["average_order_value"] = guardrails.average_order_value.map(format_currency)
st.dataframe(
    guardrails,
    hide_index=True,
    width="stretch",
    column_config={"variant": "Variant", "payment_failure_pct": "Payment failure", "average_order_value": "Average order value"},
)
significance_text = "statistically significant" if inference.statistically_significant else "not statistically significant"
st.success(
    f"The simulated treatment increased conversion by {inference.absolute_uplift_pp:.2f} percentage points. "
    f"The difference was {significance_text} at α = {inference.alpha:.2f} (p = {inference.p_value:.4f}). "
    "Payment failure did not worsen and average order value remained broadly stable."
)
st.caption("The experiment is deterministic and simulated; the dashboard reads its validated precomputed outputs.")


st.header("9. Product recommendation")
st.markdown(
    """
    <div class="recommendation">
    <strong>Observation</strong> → The largest checkout loss occurs before checkout begins, returning users perform better, and the simulated treatment lifts conversion.<br><br>
    <strong>Impact</strong> → Repeating address and payment decisions may create avoidable friction for high-intent repeat customers.<br><br>
    <strong>Recommended action</strong> → Test <strong>1-Click Reorder &amp; Micro-Cart</strong> for customers with a successful previous order, saved delivery address, and preferred payment method. Retain normal checkout as fallback.<br><br>
    <strong>Metrics to monitor</strong> → Conversion, checkout completion, payment failure, AOV, cancellations, and accidental orders.
    </div>
    """,
    unsafe_allow_html=True,
)


st.header("10. Assumptions, limitations, and technical evidence")
st.markdown(
    """
    - All user behavior and currency values are synthetic; there is no Blinkit internal data.
    - The experiment is simulated, not a real production deployment.
    - Segment relationships are observational and do not establish causality.
    - Revenue values represent intended cart value and an illustrative recovery scenario.
    - Payment behavior is simplified to one payment-attempt record per session.
    """
)
with st.expander("How this dashboard connects to the analytics pipeline"):
    st.code(
        "Synthetic generation → validation → SQLite → SQL + Python reconciliation "
        "→ validated CSV/JSON outputs → Streamlit",
        language="text",
    )
    st.markdown(
        "The dashboard reads `outputs/tables/session_funnel.csv`, `data/raw/orders.csv`, and the validated "
        "experiment and KPI exports. It performs only lightweight filtering and recalculation. SQLite, SQL, "
        "Python validation, and the deterministic A/B test remain visible in the repository."
    )
    st.dataframe(data["kpis"][["metric", "definition"]], hide_index=True, width="stretch")
