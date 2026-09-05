import sqlite3
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DATABASE_PATH = PROCESSED_DIR / "blinkit_checkout.db"


def build_database() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        for table in ["users", "sessions", "events", "orders"]:
            frame = pd.read_csv(RAW_DIR / f"{table}.csv")
            frame.to_sql(table, connection, if_exists="append", index=False)
        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        assert not foreign_key_issues, f"Foreign-key violations: {foreign_key_issues}"
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ["users", "sessions", "events", "orders"]}
    print(f"Built {DATABASE_PATH.name}: " + ", ".join(f"{table}={count:,}" for table, count in counts.items()))


if __name__ == "__main__":
    build_database()
