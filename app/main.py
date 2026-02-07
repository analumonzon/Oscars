from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.ballot_loader import BallotError, load_ballot
from app.db import get_conn, get_setting, init_db, set_setting, utc_now

BALLOT_PATH = os.environ.get("OSCARS_BALLOT_PATH", "docs/Oscar-Ballot-2026.xlsx")
ADMIN_KEY = os.environ.get("OSCARS_ADMIN_KEY")

app = FastAPI(title="Oscars Ballot")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

init_db()

try:
    BALLOT = load_ballot(BALLOT_PATH)
except BallotError as exc:
    raise RuntimeError(str(exc)) from exc

BALLOT_BY_KEY = {item["key"]: item for item in BALLOT}


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
        rows = conn.execute("SELECT category_key, nominee, points FROM winners").fetchall()
        return {row["category_key"]: dict(row) for row in rows}
    finally:
        conn.close()


def _leaderboard() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
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
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/", response_class=HTMLResponse)
async def ballot_form(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        "ballot.html",
        {
            "request": request,
            "ballot": BALLOT,
            "locked": _ballots_locked(),
            "error": error,
        },
    )


@app.post("/submit")
async def submit_ballot(request: Request, guest_name: str = Form(...)) -> RedirectResponse:
    if _ballots_locked():
        return RedirectResponse(url="/?error=Ballot%20is%20locked", status_code=303)

    name = guest_name.strip()
    if not name:
        return RedirectResponse(url="/?error=Name%20is%20required", status_code=303)

    form = await request.form()
    selections: dict[str, str] = {}
    for category in BALLOT:
        field_name = f"category_{category['key']}"
        nominee = form.get(field_name)
        if not nominee:
            return RedirectResponse(
                url=f"/?error=Missing%20selection%20for%20{category['name']}",
                status_code=303,
            )
        selections[category["key"]] = nominee

    conn = get_conn()
    try:
        with conn:
            row = conn.execute(
                "SELECT id FROM guests WHERE name = ?",
                (name,),
            ).fetchone()
            if row:
                return RedirectResponse(
                    url="/?error=This%20name%20already%20submitted%20a%20ballot",
                    status_code=303,
                )
            guest_id = conn.execute(
                "INSERT INTO guests (name, created_at) VALUES (?, ?)",
                (name, utc_now()),
            ).lastrowid
            ballot_id = conn.execute(
                "INSERT INTO ballots (guest_id, created_at) VALUES (?, ?)",
                (guest_id, utc_now()),
            ).lastrowid
            conn.executemany(
                "INSERT INTO selections (ballot_id, category_key, nominee) VALUES (?, ?, ?)",
                [(ballot_id, key, nominee) for key, nominee in selections.items()],
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
        with conn:
            if get_setting(conn, "locked_at") is None:
                set_setting(conn, "locked_at", utc_now())
    finally:
        conn.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/winners")
async def set_winners(request: Request) -> RedirectResponse:
    _require_admin(request)
    form = await request.form()
    conn = get_conn()
    try:
        with conn:
            for category in BALLOT:
                field_name = f"winner_{category['key']}"
                nominee = form.get(field_name)
                if not nominee:
                    continue
                conn.execute(
                    "INSERT INTO winners (category_key, nominee, points) VALUES (?, ?, ?)"
                    " ON CONFLICT(category_key) DO UPDATE SET nominee = excluded.nominee, points = excluded.points",
                    (category["key"], nominee, category["points"]),
                )
    finally:
        conn.close()

    return RedirectResponse(url="/admin", status_code=303)
