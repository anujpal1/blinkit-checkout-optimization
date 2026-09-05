# Power BI Dashboard Guide

Use the CSVs in `outputs/tables/`; no direct SQLite connector is required. Display all rates as percentages, currency as synthetic INR, and include a visible **Synthetic case study** label.

## Page 1 — Funnel Overview

Sources: `funnel_stage_counts.csv`, `kpi_summary.csv`, `monthly_funnel_trend.csv`, `revenue_impact.csv`.

- Funnel bar: stage and sessions, sorted by `stage_order`
- KPI cards: overall conversion, cart abandonment, checkout completion, payment failure, completed orders, synthetic revenue
- Monthly line: month, sessions, completed orders, conversion
- Revenue table: estimate, synthetic amount, formula

Core measures should use the definitions already supplied in `kpi_summary.csv`; do not average pre-aggregated percentages across segments.

## Page 2 — Segment Analysis

Sources: `user_type_performance.csv`, `device_performance.csv`, `city_performance.csv`, `acquisition_performance.csv`, `delivery_fee_performance.csv`, `payment_method_performance.csv`, `device_payment_performance.csv`.

- Clustered bars: overall conversion by user type, device, city, and acquisition channel
- Fee-band bars: `100 - cart_to_checkout_pct` as cart abandonment
- Payment matrix: method/device, attempts, failures, failure rate
- Tooltip: always show the denominator count beside a rate

Suggested slicers are user type, device, city, and acquisition channel. Keep payment method only on payment-attempt views because it is unknown earlier in the funnel.

## Page 3 — Simulated Experiment

Sources: `ab_test_group_metrics.csv`, `ab_test_inference.csv`.

- Control vs Treatment conversion bars
- KPI cards: absolute uplift, relative uplift, confidence interval, p-value
- Guardrail table: AOV and payment failure by variant
- Recommendation text: test the simplified flow for eligible repeat customers, with normal checkout fallback

Interpret significance using `p_value < alpha`. Report the confidence interval in percentage points and label the experiment as simulated.
