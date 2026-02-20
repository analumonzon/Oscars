from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    create_engine,
    delete,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Connection

DB_PATH = os.environ.get("OSCARS_DB_PATH", "data/oscars.db")
DATABASE_URL = os.environ.get("OSCARS_DATABASE_URL", f"sqlite:///{DB_PATH}")

if DATABASE_URL.startswith("sqlite:///"):
    sqlite_path = DATABASE_URL.removeprefix("sqlite:///")
    sqlite_dir = os.path.dirname(sqlite_path)
    if sqlite_dir:
        os.makedirs(sqlite_dir, exist_ok=True)

engine = create_engine(DATABASE_URL, future=True)
metadata = MetaData()

settings = Table(
    "settings",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", String, nullable=False),
)

categories = Table(
    "categories",
    metadata,
    Column("key", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("points", Integer, nullable=False),
    Column("sort_order", Integer, nullable=False),
)

nominees = Table(
    "nominees",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("category_key", String, ForeignKey("categories.key"), nullable=False),
    Column("name", String, nullable=False),
)

guests = Table(
    "guests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, nullable=False, unique=True),
    Column("created_at", String, nullable=False),
)

ballots = Table(
    "ballots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("guest_id", Integer, ForeignKey("guests.id"), nullable=False),
    Column("created_at", String, nullable=False),
)

selections = Table(
    "selections",
    metadata,
    Column("ballot_id", Integer, ForeignKey("ballots.id"), nullable=False),
    Column("category_key", String, nullable=False),
    Column("nominee", String, nullable=False),
    PrimaryKeyConstraint("ballot_id", "category_key"),
)

winners = Table(
    "winners",
    metadata,
    Column("category_key", String, primary_key=True),
    Column("nominee", String, nullable=False),
    Column("points", Integer, nullable=False),
)


def get_conn() -> Connection:
    return engine.connect()


def init_db() -> None:
    metadata.create_all(engine)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_setting(conn: Connection, key: str) -> str | None:
    row = conn.execute(
        select(settings.c.value).where(settings.c.key == key)
    ).scalar_one_or_none()
    return row


def set_setting(conn: Connection, key: str, value: str) -> None:
    conn.execute(
        text(
            "INSERT INTO settings (key, value) VALUES (:key, :value) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        ),
        {"key": key, "value": value},
    )


def clear_setting(conn: Connection, key: str) -> None:
    conn.execute(delete(settings).where(settings.c.key == key))


def replace_ballot(conn: Connection, ballot: list[dict[str, Any]]) -> None:
    def _replace() -> None:
        conn.execute(delete(nominees))
        conn.execute(delete(categories))
        conn.execute(delete(winners))
        conn.execute(delete(selections))
        conn.execute(delete(ballots))
        conn.execute(delete(guests))
        conn.execute(delete(settings).where(settings.c.key == "locked_at"))

        for idx, category in enumerate(ballot):
            conn.execute(
                insert(categories).values(
                    key=category["key"],
                    name=category["name"],
                    points=category["points"],
                    sort_order=idx,
                )
            )
            conn.execute(
                insert(nominees),
                [
                    {"category_key": category["key"], "name": nominee}
                    for nominee in category["nominees"]
                ],
            )

    if conn.in_transaction():
        _replace()
    else:
        with conn.begin():
            _replace()


def load_ballot_from_db(conn: Connection) -> list[dict[str, Any]]:
    category_rows = conn.execute(
        select(categories.c.key, categories.c.name, categories.c.points).order_by(categories.c.sort_order)
    ).mappings().all()
    if not category_rows:
        return []

    nominee_rows = conn.execute(
        select(nominees.c.category_key, nominees.c.name).order_by(nominees.c.id)
    ).mappings().all()

    by_key: dict[str, dict[str, Any]] = {
        row["key"]: {"key": row["key"], "name": row["name"], "points": row["points"], "nominees": []}
        for row in category_rows
    }

    for row in nominee_rows:
        category = by_key.get(row["category_key"])
        if category:
            category["nominees"].append(row["name"])

    return list(by_key.values())
