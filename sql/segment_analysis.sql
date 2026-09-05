-- name: user_type_performance
WITH session_flags AS (
    SELECT session_id,
           MAX(event_name = 'Cart View') AS cart_view,
           MAX(event_name = 'Checkout Started') AS checkout_started,
           MAX(event_name = 'Order Completed') AS order_completed
    FROM events GROUP BY session_id
)
SELECT u.user_type AS segment, COUNT(*) AS sessions,
       SUM(sf.cart_view) AS cart_views, SUM(sf.checkout_started) AS checkout_starts,
       SUM(sf.order_completed) AS completed_orders,
       ROUND(100.0 * SUM(sf.order_completed) / COUNT(*), 2) AS overall_conversion_pct,
       ROUND(100.0 * SUM(sf.checkout_started) / NULLIF(SUM(sf.cart_view), 0), 2) AS cart_to_checkout_pct,
       ROUND(100.0 * SUM(sf.order_completed) / NULLIF(SUM(sf.checkout_started), 0), 2) AS checkout_completion_pct,
       ROUND(AVG(CASE WHEN o.payment_status = 'Success' THEN o.order_value END), 2) AS average_order_value
FROM sessions s JOIN users u ON u.user_id = s.user_id
JOIN session_flags sf ON sf.session_id = s.session_id
LEFT JOIN orders o ON o.session_id = s.session_id
GROUP BY u.user_type
HAVING COUNT(*) >= 100
ORDER BY overall_conversion_pct DESC;

-- name: device_performance
WITH session_flags AS (
    SELECT session_id, MAX(event_name = 'Cart View') AS cart_view,
           MAX(event_name = 'Checkout Started') AS checkout_started,
           MAX(event_name = 'Order Completed') AS order_completed
    FROM events GROUP BY session_id
)
SELECT s.device AS segment, COUNT(*) AS sessions,
       SUM(sf.cart_view) AS cart_views, SUM(sf.checkout_started) AS checkout_starts,
       SUM(sf.order_completed) AS completed_orders,
       ROUND(100.0 * SUM(sf.order_completed) / COUNT(*), 2) AS overall_conversion_pct,
       ROUND(100.0 * SUM(sf.checkout_started) / NULLIF(SUM(sf.cart_view), 0), 2) AS cart_to_checkout_pct,
       ROUND(100.0 * SUM(sf.order_completed) / NULLIF(SUM(sf.checkout_started), 0), 2) AS checkout_completion_pct
FROM sessions s JOIN session_flags sf ON sf.session_id = s.session_id
GROUP BY s.device ORDER BY overall_conversion_pct DESC;

-- name: city_performance
WITH session_flags AS (
    SELECT session_id, MAX(event_name = 'Cart View') AS cart_view,
           MAX(event_name = 'Checkout Started') AS checkout_started,
           MAX(event_name = 'Order Completed') AS order_completed
    FROM events GROUP BY session_id
), city_metrics AS (
    SELECT s.city AS segment, COUNT(*) AS sessions,
           SUM(sf.cart_view) AS cart_views, SUM(sf.checkout_started) AS checkout_starts,
           SUM(sf.order_completed) AS completed_orders,
           100.0 * SUM(sf.order_completed) / COUNT(*) AS overall_conversion_pct,
           100.0 * SUM(sf.checkout_started) / NULLIF(SUM(sf.cart_view), 0) AS cart_to_checkout_pct,
           100.0 * SUM(sf.order_completed) / NULLIF(SUM(sf.checkout_started), 0) AS checkout_completion_pct
    FROM sessions s JOIN session_flags sf ON sf.session_id = s.session_id
    GROUP BY s.city
)
SELECT segment, sessions, cart_views, checkout_starts, completed_orders,
       ROUND(overall_conversion_pct, 2) AS overall_conversion_pct,
       ROUND(cart_to_checkout_pct, 2) AS cart_to_checkout_pct,
       ROUND(checkout_completion_pct, 2) AS checkout_completion_pct,
       RANK() OVER (ORDER BY checkout_completion_pct DESC) AS checkout_rank
FROM city_metrics ORDER BY checkout_rank;

-- name: acquisition_performance
WITH session_flags AS (
    SELECT session_id, MAX(event_name = 'Cart View') AS cart_view,
           MAX(event_name = 'Checkout Started') AS checkout_started,
           MAX(event_name = 'Order Completed') AS order_completed
    FROM events GROUP BY session_id
)
SELECT u.acquisition_channel AS segment, COUNT(*) AS sessions,
       SUM(sf.cart_view) AS cart_views, SUM(sf.checkout_started) AS checkout_starts,
       SUM(sf.order_completed) AS completed_orders,
       ROUND(100.0 * SUM(sf.order_completed) / COUNT(*), 2) AS overall_conversion_pct,
       ROUND(100.0 * SUM(sf.checkout_started) / NULLIF(SUM(sf.cart_view), 0), 2) AS cart_to_checkout_pct,
       ROUND(100.0 * SUM(sf.order_completed) / NULLIF(SUM(sf.checkout_started), 0), 2) AS checkout_completion_pct
FROM sessions s JOIN users u ON u.user_id = s.user_id
JOIN session_flags sf ON sf.session_id = s.session_id
GROUP BY u.acquisition_channel ORDER BY overall_conversion_pct DESC;

-- name: delivery_fee_performance
WITH session_flags AS (
    SELECT session_id, MAX(event_name = 'Cart View') AS cart_view,
           MAX(event_name = 'Checkout Started') AS checkout_started,
           MAX(event_name = 'Order Completed') AS order_completed
    FROM events GROUP BY session_id
), fee_segments AS (
    SELECT s.session_id,
           CASE WHEN s.delivery_fee = 0 THEN 'Free'
                WHEN s.delivery_fee <= 30 THEN 'Low (1-30)'
                WHEN s.delivery_fee <= 50 THEN 'Medium (31-50)'
                ELSE 'High (51+)' END AS segment,
           sf.cart_view, sf.checkout_started, sf.order_completed
    FROM sessions s JOIN session_flags sf ON sf.session_id = s.session_id
    WHERE sf.cart_view = 1
)
SELECT segment, COUNT(*) AS cart_view_sessions, SUM(checkout_started) AS checkout_starts,
       SUM(order_completed) AS completed_orders,
       ROUND(100.0 * SUM(checkout_started) / COUNT(*), 2) AS cart_to_checkout_pct,
       ROUND(100.0 * SUM(order_completed) / COUNT(*), 2) AS cart_to_order_pct
FROM fee_segments GROUP BY segment
ORDER BY CASE segment WHEN 'Free' THEN 1 WHEN 'Low (1-30)' THEN 2 WHEN 'Medium (31-50)' THEN 3 ELSE 4 END;

-- name: payment_method_performance
SELECT payment_method AS segment, COUNT(*) AS payment_attempts,
       SUM(payment_status = 'Success') AS successful_payments,
       SUM(payment_status = 'Failed') AS failed_payments,
       ROUND(100.0 * SUM(payment_status = 'Failed') / COUNT(*), 2) AS payment_failure_pct,
       ROUND(AVG(CASE WHEN payment_status = 'Success' THEN order_value END), 2) AS average_successful_order_value
FROM orders GROUP BY payment_method ORDER BY payment_failure_pct;

-- name: device_payment_performance
SELECT s.device AS segment, COUNT(*) AS payment_attempts,
       SUM(o.payment_status = 'Failed') AS failed_payments,
       ROUND(100.0 * SUM(o.payment_status = 'Failed') / COUNT(*), 2) AS payment_failure_pct
FROM orders o JOIN sessions s ON s.session_id = o.session_id
GROUP BY s.device ORDER BY payment_failure_pct;

-- name: repeat_order_behavior
WITH successful_orders AS (
    SELECT o.*,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_date, order_id) AS order_number
    FROM orders o WHERE payment_status = 'Success'
), user_orders AS (
    SELECT user_id, COUNT(*) AS completed_orders, SUM(order_value) AS revenue
    FROM successful_orders GROUP BY user_id
)
SELECT
    COUNT(*) AS purchasing_users,
    SUM(completed_orders >= 2) AS repeat_purchasers,
    ROUND(100.0 * SUM(completed_orders >= 2) / COUNT(*), 2) AS repeat_purchaser_pct,
    ROUND(AVG(completed_orders), 2) AS orders_per_purchaser,
    ROUND(SUM(revenue), 2) AS synthetic_revenue
FROM user_orders;
