from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, insert, select, text

from app.ballot_loader import BallotError, load_ballot
from app.db import (
    ballots,
    clear_setting,
    guests,
    get_conn,
    get_setting,
    init_db,
    load_ballot_from_db,
    replace_ballot,
    selections,
    set_setting,
    utc_now,
    winners,
)

BALLOT_PATH = os.environ.get("OSCARS_BALLOT_PATH", "docs/OscarBallotList.csv")
ADMIN_KEY = os.environ.get("OSCARS_ADMIN_KEY")
RESET_BALLOT_ON_START = os.environ.get("OSCARS_RESET_BALLOT_ON_START", "false").lower() in {
    "1",
    "true",
    "yes",
}

app = FastAPI(title="Oscars Ballot")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

init_db()

try:
    file_ballot = load_ballot(BALLOT_PATH)
except BallotError as exc:
    raise RuntimeError(str(exc)) from exc

print(
    f"[startup] ballot_path={BALLOT_PATH} reset_on_start={RESET_BALLOT_ON_START} "
    f"loaded_categories={len(file_ballot)}"
)

conn = get_conn()
try:
    existing_ballot = load_ballot_from_db(conn)
    replaced_ballot = bool(RESET_BALLOT_ON_START or not existing_ballot)
    if replaced_ballot:
        replace_ballot(conn, file_ballot)
    BALLOT = load_ballot_from_db(conn)
    print(
        f"[startup] existing_categories_before={len(existing_ballot)} "
        f"replaced_ballot={replaced_ballot} db_categories_after={len(BALLOT)}"
    )
finally:
    conn.close()


def _require_admin(request: Request) -> None:
    if not ADMIN_KEY:
        return
    key = request.query_params.get("key") or request.headers.get("X-Admin-Key")
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin key required")


def _ballots_locked() -> bool:
    conn = get_conn()
    try:
        return get_setting(conn, "locked_at") is not None
    finally:
        conn.close()


def _load_winners() -> dict[str, dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            select(winners.c.category_key, winners.c.nominee, winners.c.points)
        ).mappings().all()
        return {row["category_key"]: dict(row) for row in rows}
    finally:
        conn.close()


def _leaderboard() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            text(
                """
            SELECT g.name AS guest_name,
                   COALESCE(SUM(CASE WHEN s.nominee = w.nominee THEN w.points ELSE 0 END), 0) AS score
            FROM guests g
            JOIN ballots b ON b.guest_id = g.id
            JOIN selections s ON s.ballot_id = b.id
            LEFT JOIN winners w ON w.category_key = s.category_key
            GROUP BY g.name
            ORDER BY score DESC, g.name ASC
            """
            )
        ).mappings().all()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _normalized_name(name: str) -> str:
    return " ".join(name.split()).strip().lower()


def _find_guest_row(conn, name: str):
    normalized = _normalized_name(name)
    if not normalized:
        return None
    return conn.execute(
        select(guests.c.id, guests.c.name)
        .where(func.lower(func.trim(guests.c.name)) == normalized)
        .limit(1)
    ).first()


def _load_guest_ballot(name: str) -> dict[str, str] | None:
    conn = get_conn()
    try:
        guest = _find_guest_row(conn, name)
        if not guest:
            return None

        latest_ballot = conn.execute(
            select(ballots.c.id)
            .where(ballots.c.guest_id == guest.id)
            .order_by(ballots.c.id.desc())
            .limit(1)
        ).first()
        if not latest_ballot:
            return None

        rows = conn.execute(
            select(selections.c.category_key, selections.c.nominee)
            .where(selections.c.ballot_id == latest_ballot.id)
        ).all()
        return {row.category_key: row.nominee for row in rows}
    finally:
        conn.close()


@app.get("/api/guest-check")
async def guest_check(name: str = "") -> dict[str, str | bool | None]:
    check_name = " ".join(name.split()).strip()
    if not check_name:
        return {"exists": False, "name": "", "edit_url": None}

    conn = get_conn()
    try:
        row = _find_guest_row(conn, check_name)
        if not row:
            return {"exists": False, "name": check_name, "edit_url": None}
        return {
            "exists": True,
            "name": row.name,
            "edit_url": f"/?edit_name={quote(row.name)}",
        }
    finally:
        conn.close()


@app.get("/", response_class=HTMLResponse)
async def ballot_form(
    request: Request,
    error: str | None = None,
    duplicate_name: str | None = None,
    edit_name: str | None = None,
    view_name: str | None = None,
) -> HTMLResponse:
    locked = _ballots_locked()
    edit_mode = bool(edit_name)
    existing_selections: dict[str, str] = {}
    readonly_name = ""
    readonly_lookup_done = False
    readonly_lookup_error: str | None = None

    if edit_mode and edit_name:
        existing_selections = _load_guest_ballot(edit_name) or {}
    elif locked and view_name:
        readonly_name = " ".join(view_name.split()).strip()
        if readonly_name:
            readonly_lookup_done = True
            loaded = _load_guest_ballot(readonly_name)
            if loaded is None:
                readonly_lookup_error = "No ballot found for that name."
            else:
                existing_selections = loaded
        else:
            readonly_lookup_done = True
            readonly_lookup_error = "Please enter a name to view saved answers."

    return templates.TemplateResponse(
        "ballot.html",
        {
            "request": request,
            "ballot": BALLOT,
            "locked": locked,
            "error": error,
            "duplicate_name": duplicate_name,
            "edit_mode": edit_mode,
            "edit_name": edit_name,
            "default_guest_name": edit_name or "",
            "existing_selections": existing_selections,
            "edit_url": f"/?edit_name={quote(duplicate_name)}" if duplicate_name else None,
            "readonly_name": readonly_name,
            "readonly_lookup_done": readonly_lookup_done,
            "readonly_lookup_error": readonly_lookup_error,
        },
    )


@app.post("/submit")
async def submit_ballot(
    request: Request,
    guest_name: str = Form(...),
    overwrite: str | None = Form(default=None),
) -> RedirectResponse:
    if _ballots_locked():
        return RedirectResponse(url="/?error=Ballot%20is%20locked", status_code=303)

    name = " ".join(guest_name.split()).strip()
    overwrite_existing = (overwrite or "").lower() in {"1", "true", "yes", "on"}
    if not name:
        return RedirectResponse(url="/?error=Name%20is%20required", status_code=303)

    form = await request.form()
    picks: dict[str, str] = {}
    for category in BALLOT:
        field_name = f"category_{category['key']}"
        nominee = form.get(field_name)
        if not nominee:
            return RedirectResponse(
                url=f"/?error=Missing%20selection%20for%20{category['name']}",
                status_code=303,
            )
        picks[category["key"]] = nominee

    conn = get_conn()
    try:
        with conn.begin():
            row = _find_guest_row(conn, name)
            if row:
                if not overwrite_existing:
                    return RedirectResponse(
                        url=f"/?duplicate_name={quote(row.name)}&error=Name%20already%20exists",
                        status_code=303,
                    )

                guest_id = row.id
                ballot_ids = conn.execute(
                    select(ballots.c.id).where(ballots.c.guest_id == guest_id)
                ).scalars().all()
                if ballot_ids:
                    conn.execute(delete(selections).where(selections.c.ballot_id.in_(ballot_ids)))
                conn.execute(delete(ballots).where(ballots.c.guest_id == guest_id))
            else:
                guest_id = conn.execute(
                    insert(guests).values(name=name, created_at=utc_now())
                ).inserted_primary_key[0]

            ballot_id = conn.execute(
                insert(ballots).values(guest_id=guest_id, created_at=utc_now())
            ).inserted_primary_key[0]
            conn.execute(
                insert(selections),
                [
                    {"ballot_id": ballot_id, "category_key": key, "nominee": nominee}
                    for key, nominee in picks.items()
                ],
            )
    finally:
        conn.close()

    return RedirectResponse(url="/leaderboard", status_code=303)


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "leaderboard.html",
        {"request": request, "leaders": _leaderboard()},
    )


@app.get("/healthz", response_model=None)
async def healthz():
    conn = get_conn()
    try:
        conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unreachable"},
        )
    finally:
        conn.close()


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request) -> HTMLResponse:
    _require_admin(request)
    winners = _load_winners()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "ballot": BALLOT,
            "winners": winners,
            "locked": _ballots_locked(),
            "leaders": _leaderboard(),
        },
    )


@app.post("/admin/lock")
async def lock_ballots(request: Request) -> RedirectResponse:
    _require_admin(request)
    conn = get_conn()
    try:
        with conn.begin():
            if get_setting(conn, "locked_at") is None:
                set_setting(conn, "locked_at", utc_now())
    finally:
        conn.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/unlock")
async def unlock_ballots(request: Request) -> RedirectResponse:
    _require_admin(request)
    conn = get_conn()
    try:
        with conn.begin():
            clear_setting(conn, "locked_at")
    finally:
        conn.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/winners")
async def set_winners(request: Request) -> RedirectResponse:
    _require_admin(request)
    form = await request.form()
    conn = get_conn()
    try:
        with conn.begin():
            for category in BALLOT:
                field_name = f"winner_{category['key']}"
                nominee = form.get(field_name)
                if not nominee:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO winners (category_key, nominee, points) VALUES (:category_key, :nominee, :points) "
                        "ON CONFLICT(category_key) DO UPDATE SET nominee = excluded.nominee, points = excluded.points"
                    ),
                    {
                        "category_key": category["key"],
                        "nominee": nominee,
                        "points": category["points"],
                    },
                )
    finally:
        conn.close()

    return RedirectResponse(url="/admin", status_code=303)
