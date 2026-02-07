from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

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
