from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
STAGES = [
    "App Open", "Search", "Product View", "Add to Cart", "Cart View",
    "Checkout Started", "Payment Attempt", "Order Completed",
]


def load_data() -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(RAW_DIR / f"{name}.csv") for name in ["users", "sessions", "events", "orders"]}


def validate() -> None:
    data = load_data()
    users, sessions, events, orders = (data[name] for name in ["users", "sessions", "events", "orders"])

    for frame, id_column in [(users, "user_id"), (sessions, "session_id"), (events, "event_id"), (orders, "order_id")]:
        assert frame[id_column].notna().all(), f"Missing {id_column}"
        assert frame[id_column].is_unique, f"Duplicate {id_column}"
    for frame, columns in [(sessions, ["user_id"]), (events, ["session_id", "user_id"]), (orders, ["session_id", "user_id"])]:
        assert frame[columns].notna().all().all(), f"Missing critical identifier in {columns}"

    assert set(events.event_name).issubset(STAGES), "Invalid event name"
    assert set(orders.payment_status).issubset({"Success", "Failed"}), "Invalid payment status"
    assert (orders.order_value >= 0).all() and (sessions.cart_value >= 0).all(), "Negative value"
    assert (orders.delivery_fee >= 0).all() and (sessions.delivery_fee >= 0).all(), "Negative delivery fee"
    assert sessions.user_id.isin(users.user_id).all(), "Orphan session user"
    assert events.session_id.isin(sessions.session_id).all(), "Orphan event session"
    assert orders.session_id.isin(sessions.session_id).all(), "Orphan order session"

    user_lookup = users.set_index("user_id")
    session_lookup = sessions.set_index("session_id")
    assert (sessions.device == sessions.user_id.map(user_lookup.device)).all(), "Session/user device mismatch"
    assert (sessions.city == sessions.user_id.map(user_lookup.city)).all(), "Session/user city mismatch"
    assert (events.user_id == events.session_id.map(session_lookup.user_id)).all(), "Event/session user mismatch"
    assert (orders.user_id == orders.session_id.map(session_lookup.user_id)).all(), "Order/session user mismatch"

    for frame, column in [(users, "signup_date"), (sessions, "session_start"), (events, "event_timestamp"), (orders, "order_date")]:
        parsed = pd.to_datetime(frame[column], errors="coerce")
        assert parsed.notna().all(), f"Invalid timestamp in {column}"

    session_start = pd.to_datetime(sessions.set_index("session_id").session_start)
    signup_date = pd.to_datetime(users.set_index("user_id").signup_date)
    assert (pd.to_datetime(sessions.session_start) >= sessions.user_id.map(signup_date).reset_index(drop=True)).all(), "Session before signup"
    assert (pd.to_datetime(events.event_timestamp) >= events.session_id.map(session_start).reset_index(drop=True)).all(), "Event before session"
    assert (pd.to_datetime(orders.order_date) >= orders.session_id.map(session_start).reset_index(drop=True)).all(), "Payment record before session"

    stage_map = {stage: index for index, stage in enumerate(STAGES)}
    ordered = events.assign(stage_index=events.event_name.map(stage_map)).sort_values(["session_id", "event_timestamp"])
    for session_id, group in ordered.groupby("session_id", sort=False):
        indices = group.stage_index.tolist()
        assert indices == list(range(len(indices))), f"Impossible funnel sequence in {session_id}: {indices}"
        assert group.event_timestamp.is_monotonic_increasing, f"Non-monotonic events in {session_id}"

    completed_sessions = set(events.loc[events.event_name == "Order Completed", "session_id"])
    successful_sessions = set(orders.loc[orders.payment_status == "Success", "session_id"])
    attempted_sessions = set(events.loc[events.event_name == "Payment Attempt", "session_id"])
    assert completed_sessions == successful_sessions, "Completed events and successful payments differ"
    assert attempted_sessions == set(orders.session_id), "Payment attempts and order records differ"
    assert orders.session_id.is_unique, "Multiple payment records for one session"
    assert (orders.set_index("session_id").delivery_fee == sessions.set_index("session_id").loc[orders.session_id].delivery_fee.values).all(), "Order/session fee mismatch"

    print("Validation passed: IDs, identifiers, timestamps, categories, amounts, foreign keys, and funnel order are valid.")


if __name__ == "__main__":
    validate()
