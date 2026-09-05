PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    signup_date TEXT NOT NULL,
    city TEXT NOT NULL,
    device TEXT NOT NULL CHECK (device IN ('Android', 'iOS')),
    acquisition_channel TEXT NOT NULL,
    user_type TEXT NOT NULL CHECK (user_type IN ('New', 'Returning'))
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_start TEXT NOT NULL,
    device TEXT NOT NULL,
    city TEXT NOT NULL,
    cart_value REAL NOT NULL CHECK (cart_value >= 0),
    delivery_fee REAL NOT NULL CHECK (delivery_fee >= 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    order_value REAL NOT NULL CHECK (order_value >= 0),
    payment_method TEXT NOT NULL,
    payment_status TEXT NOT NULL CHECK (payment_status IN ('Success', 'Failed')),
    delivery_fee REAL NOT NULL CHECK (delivery_fee >= 0),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_events_session ON events(session_id, event_timestamp);
CREATE INDEX idx_events_name ON events(event_name);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_orders_status ON orders(payment_status);
