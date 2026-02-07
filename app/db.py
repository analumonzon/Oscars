from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.environ.get("OSCARS_DB_PATH", "data/oscars.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                points INTEGER NOT NULL,
                sort_order INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS nominees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_key TEXT NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY (category_key) REFERENCES categories(key)
            );

            CREATE TABLE IF NOT EXISTS guests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ballots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guest_id) REFERENCES guests(id)
            );

            CREATE TABLE IF NOT EXISTS selections (
                ballot_id INTEGER NOT NULL,
                category_key TEXT NOT NULL,
                nominee TEXT NOT NULL,
                PRIMARY KEY (ballot_id, category_key),
                FOREIGN KEY (ballot_id) REFERENCES ballots(id)
            );

            CREATE TABLE IF NOT EXISTS winners (
                category_key TEXT PRIMARY KEY,
                nominee TEXT NOT NULL,
                points INTEGER NOT NULL
            );
            """
        )
    conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def replace_ballot(conn: sqlite3.Connection, ballot: list[dict[str, Any]]) -> None:
    with conn:
        conn.execute("DELETE FROM nominees")
        conn.execute("DELETE FROM categories")
        conn.execute("DELETE FROM winners")
        conn.execute("DELETE FROM selections")
        conn.execute("DELETE FROM ballots")
        conn.execute("DELETE FROM guests")
        conn.execute("DELETE FROM settings WHERE key = 'locked_at'")

        for idx, category in enumerate(ballot):
            conn.execute(
                "INSERT INTO categories (key, name, points, sort_order) VALUES (?, ?, ?, ?)",
                (category["key"], category["name"], category["points"], idx),
            )
            conn.executemany(
                "INSERT INTO nominees (category_key, name) VALUES (?, ?)",
                [(category["key"], nominee) for nominee in category["nominees"]],
            )


def load_ballot_from_db(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    categories = conn.execute(
        "SELECT key, name, points FROM categories ORDER BY sort_order"
    ).fetchall()
    if not categories:
        return []

    nominees = conn.execute(
        "SELECT category_key, name FROM nominees ORDER BY id"
    ).fetchall()

    by_key: dict[str, dict[str, Any]] = {
        row["key"]: {"key": row["key"], "name": row["name"], "points": row["points"], "nominees": []}
        for row in categories
    }

    for row in nominees:
        category = by_key.get(row["category_key"])
        if category:
            category["nominees"].append(row["name"])

    return list(by_key.values())
