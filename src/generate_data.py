from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
N_USERS = 7000
STAGES = [
    "App Open", "Search", "Product View", "Add to Cart", "Cart View",
    "Checkout Started", "Payment Attempt", "Order Completed",
]
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"


def bounded(value: float, low: float = 0.05, high: float = 0.99) -> float:
    return float(np.clip(value, low, high))


def generate_users(rng: np.random.Generator) -> pd.DataFrame:
    user_ids = [f"U{i:05d}" for i in range(1, N_USERS + 1)]
    user_type = rng.choice(["New", "Returning"], N_USERS, p=[0.56, 0.44])
    cities = rng.choice(
        ["Bengaluru", "Delhi", "Mumbai", "Hyderabad", "Kolkata"],
        N_USERS, p=[0.26, 0.22, 0.20, 0.18, 0.14],
    )
    devices = rng.choice(["Android", "iOS"], N_USERS, p=[0.72, 0.28])
    channels = rng.choice(
        ["Organic", "Paid Search", "Paid Social", "Referral"],
        N_USERS, p=[0.43, 0.23, 0.19, 0.15],
    )
    analysis_start = pd.Timestamp("2025-01-01")
    signup_days = np.where(
        user_type == "Returning",
        rng.integers(90, 730, N_USERS),
        rng.integers(0, 120, N_USERS),
    )
    signup_dates = analysis_start - pd.to_timedelta(signup_days, unit="D")
    return pd.DataFrame({
        "user_id": user_ids,
        "signup_date": signup_dates.strftime("%Y-%m-%d"),
        "city": cities,
        "device": devices,
        "acquisition_channel": channels,
        "user_type": user_type,
    })


def choose_delivery_fee(rng: np.random.Generator, cart_value: float) -> float:
    if cart_value >= 900 and rng.random() < 0.68:
        return 0.0
    return float(rng.choice([0, 19, 29, 39, 49, 59, 69], p=[0.10, 0.12, 0.18, 0.22, 0.19, 0.12, 0.07]))


def stage_probabilities(user: pd.Series, delivery_fee: float) -> list[float]:
    returning = user.user_type == "Returning"
    organic = user.acquisition_channel == "Organic"
    paid_social = user.acquisition_channel == "Paid Social"
    android = user.device == "Android"
    kolkata = user.city == "Kolkata"

    search = bounded(0.945 + 0.012 * returning + 0.008 * organic - 0.015 * paid_social)
    product = bounded(0.91 + 0.014 * returning + 0.008 * organic - 0.018 * paid_social)
    add = bounded(0.72 + 0.045 * returning + 0.018 * organic - 0.035 * paid_social)
    cart = bounded(0.95 + 0.012 * returning)
    fee_penalty = {0.0: 0.025, 19.0: 0.01, 29.0: 0.0, 39.0: -0.025, 49.0: -0.055, 59.0: -0.095, 69.0: -0.13}[delivery_fee]
    checkout = bounded(
        0.72 + 0.07 * returning + 0.018 * organic - 0.035 * paid_social
        - 0.045 * kolkata - 0.012 * android + fee_penalty
    )
    payment = bounded(0.925 + 0.018 * returning - 0.012 * android - 0.012 * kolkata)
    return [search, product, add, cart, checkout, payment]


def generate_behavior(users: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sessions, events, orders = [], [], []
    event_counter = 1
    order_counter = 1
    session_counter = 1
    payment_methods = ["UPI", "Card", "Wallet", "Cash on Delivery"]
    payment_weights = [0.53, 0.24, 0.13, 0.10]

    for user in users.itertuples(index=False):
        session_count = 1 + rng.poisson(1.05 if user.user_type == "Returning" else 0.35)
        for _ in range(session_count):
            session_id = f"S{session_counter:06d}"
            session_counter += 1
            start = pd.Timestamp("2025-01-01") + pd.to_timedelta(int(rng.integers(0, 181)), unit="D")
            start += pd.to_timedelta(int(rng.integers(7 * 60, 23 * 60)), unit="m")
            aov_mean = 760 if user.user_type == "Returning" else 660
            cart_value = round(float(np.clip(rng.lognormal(np.log(aov_mean), 0.38), 150, 2400)), 2)
            delivery_fee = choose_delivery_fee(rng, cart_value)
            sessions.append({
                "session_id": session_id, "user_id": user.user_id,
                "session_start": start.isoformat(), "device": user.device, "city": user.city,
                "cart_value": cart_value, "delivery_fee": delivery_fee,
            })

            reached_stages = ["App Open"]
            for stage, probability in zip(STAGES[1:7], stage_probabilities(pd.Series(user._asdict()), delivery_fee)):
                if rng.random() <= probability:
                    reached_stages.append(stage)
                else:
                    break

            payment_method = None
            payment_status = None
            if reached_stages[-1] == "Payment Attempt":
                payment_method = str(rng.choice(payment_methods, p=payment_weights))
                fail_probability = 0.085
                fail_probability += 0.035 if user.device == "Android" else 0
                fail_probability += 0.025 if payment_method == "Card" else 0
                fail_probability += 0.040 if payment_method == "Cash on Delivery" else 0
                fail_probability -= 0.012 if payment_method == "Wallet" else 0
                fail_probability += 0.012 if user.city == "Kolkata" else 0
                fail_probability -= 0.012 if user.user_type == "Returning" else 0
                payment_status = "Failed" if rng.random() < bounded(fail_probability, 0.03, 0.22) else "Success"
                if payment_status == "Success":
                    reached_stages.append("Order Completed")

                payment_time = start + pd.to_timedelta(30 + 18 * (len(reached_stages) - 1), unit="s")
                orders.append({
                    "order_id": f"O{order_counter:06d}", "session_id": session_id,
                    "user_id": user.user_id, "order_date": payment_time.isoformat(),
                    "order_value": cart_value, "payment_method": payment_method,
                    "payment_status": payment_status, "delivery_fee": delivery_fee,
                })
                order_counter += 1

            for stage_index, stage in enumerate(reached_stages):
                event_time = start + pd.to_timedelta(30 + stage_index * 18 + int(rng.integers(0, 8)), unit="s")
                events.append({
                    "event_id": f"E{event_counter:07d}", "session_id": session_id,
                    "user_id": user.user_id, "event_name": stage,
                    "event_timestamp": event_time.isoformat(),
                })
                event_counter += 1

    return pd.DataFrame(sessions), pd.DataFrame(events), pd.DataFrame(orders)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    users = generate_users(rng)
    sessions, events, orders = generate_behavior(users, rng)
    users.to_csv(RAW_DIR / "users.csv", index=False)
    sessions.to_csv(RAW_DIR / "sessions.csv", index=False)
    events.to_csv(RAW_DIR / "events.csv", index=False)
    orders.to_csv(RAW_DIR / "orders.csv", index=False)
    print(f"Generated {len(users):,} users, {len(sessions):,} sessions, {len(events):,} events, and {len(orders):,} payment attempts.")


if __name__ == "__main__":
    main()
