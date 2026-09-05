-- name: funnel_stage_counts
WITH session_flags AS (
    SELECT
        session_id,
        MAX(event_name = 'App Open') AS app_open,
        MAX(event_name = 'Search') AS search,
        MAX(event_name = 'Product View') AS product_view,
        MAX(event_name = 'Add to Cart') AS add_to_cart,
        MAX(event_name = 'Cart View') AS cart_view,
        MAX(event_name = 'Checkout Started') AS checkout_started,
        MAX(event_name = 'Payment Attempt') AS payment_attempt,
        MAX(event_name = 'Order Completed') AS order_completed
    FROM events
    GROUP BY session_id
), stage_counts AS (
    SELECT 1 AS stage_order, 'App Open' AS stage, SUM(app_open) AS sessions FROM session_flags
    UNION ALL SELECT 2, 'Search', SUM(search) FROM session_flags
    UNION ALL SELECT 3, 'Product View', SUM(product_view) FROM session_flags
    UNION ALL SELECT 4, 'Add to Cart', SUM(add_to_cart) FROM session_flags
    UNION ALL SELECT 5, 'Cart View', SUM(cart_view) FROM session_flags
    UNION ALL SELECT 6, 'Checkout Started', SUM(checkout_started) FROM session_flags
    UNION ALL SELECT 7, 'Payment Attempt', SUM(payment_attempt) FROM session_flags
    UNION ALL SELECT 8, 'Order Completed', SUM(order_completed) FROM session_flags
)
SELECT
    stage_order,
    stage,
    sessions,
    ROUND(100.0 * sessions / FIRST_VALUE(sessions) OVER (ORDER BY stage_order), 2) AS percent_of_app_opens,
    ROUND(100.0 * LEAD(sessions) OVER (ORDER BY stage_order) / sessions, 2) AS next_stage_conversion_pct,
    sessions - LEAD(sessions) OVER (ORDER BY stage_order) AS dropoff_sessions,
    ROUND(100.0 * (sessions - LEAD(sessions) OVER (ORDER BY stage_order)) / sessions, 2) AS dropoff_pct
FROM stage_counts
ORDER BY stage_order;

-- name: core_product_metrics
WITH session_flags AS (
    SELECT
        session_id,
        MAX(event_name = 'Cart View') AS cart_view,
        MAX(event_name = 'Checkout Started') AS checkout_started,
        MAX(event_name = 'Order Completed') AS order_completed
    FROM events
    GROUP BY session_id
), order_summary AS (
    SELECT
        COUNT(*) AS payment_attempts,
        SUM(payment_status = 'Failed') AS failed_payments,
        SUM(payment_status = 'Success') AS completed_orders,
        SUM(CASE WHEN payment_status = 'Success' THEN order_value ELSE 0 END) AS synthetic_revenue,
        AVG(CASE WHEN payment_status = 'Success' THEN order_value END) AS average_order_value
    FROM orders
)
SELECT
    COUNT(*) AS sessions,
    SUM(sf.order_completed) AS completed_orders,
    ROUND(100.0 * SUM(sf.order_completed) / COUNT(*), 2) AS overall_conversion_pct,
    ROUND(100.0 * SUM(sf.order_completed) / SUM(sf.checkout_started), 2) AS checkout_completion_pct,
    ROUND(100.0 * (1.0 - SUM(sf.checkout_started) * 1.0 / SUM(sf.cart_view)), 2) AS cart_abandonment_pct,
    ROUND(100.0 * os.failed_payments / os.payment_attempts, 2) AS payment_failure_pct,
    ROUND(os.average_order_value, 2) AS average_order_value,
    ROUND(os.synthetic_revenue, 2) AS synthetic_revenue
FROM session_flags sf
CROSS JOIN order_summary os;

-- name: monthly_funnel_trend
WITH session_flags AS (
    SELECT
        e.session_id,
        MAX(e.event_name = 'Checkout Started') AS checkout_started,
        MAX(e.event_name = 'Order Completed') AS order_completed
    FROM events e
    GROUP BY e.session_id
)
SELECT
    strftime('%Y-%m', s.session_start) AS month,
    COUNT(*) AS sessions,
    SUM(sf.checkout_started) AS checkout_starts,
    SUM(sf.order_completed) AS completed_orders,
    ROUND(100.0 * SUM(sf.order_completed) / COUNT(*), 2) AS conversion_pct
FROM sessions s
JOIN session_flags sf ON sf.session_id = s.session_id
GROUP BY strftime('%Y-%m', s.session_start)
ORDER BY month;
