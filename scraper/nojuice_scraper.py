# scraper/nojuice_scraper.py
import os
import re
import json
import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


PYR_RE = re.compile(r"^PYR(\d+)$", re.IGNORECASE)
MON_HEADER_RE = re.compile(r"Mon\s*\((\d{1,2})/(\d{1,2})\)", re.IGNORECASE)


@dataclass
class ScrapedRow:
    week_id: dt.date
    player_id: str
    week_amount: float
    raw_payload: Dict[str, Any]


def _parse_money(x: str) -> float:
    """
    Handles '', '-0', '1,234', '$-216' etc.
    """
    s = (x or "").strip()
    if s == "":
        return 0.0
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


def _infer_week_id_from_headers(header_texts: List[str], now: Optional[dt.date] = None) -> dt.date:
    """
    Find "Mon (MM/DD)" in the table headers and infer the year.
    """
    now = now or dt.date.today()

    mm = dd = None
    for h in header_texts:
        m = MON_HEADER_RE.search(h)
        if m:
            mm, dd = int(m.group(1)), int(m.group(2))
            break

    if mm is None:
        # fallback: previous week's Monday (week close use case)
        today = now
        last_monday = today - dt.timedelta(days=today.weekday())
        return last_monday - dt.timedelta(days=7)

    candidate = dt.date(now.year, mm, dd)
    if candidate - now > dt.timedelta(days=30):
        candidate = dt.date(now.year - 1, mm, dd)
    return candidate


def _dump_debug(page, label: str) -> None:
    """
    Writes artifacts/{label}.png and artifacts/{label}.html for inspection in CI.
    """
    Path("artifacts").mkdir(exist_ok=True)
    try:
        page.screenshot(path=f"artifacts/{label}.png", full_page=True)
    except Exception:
        pass
    try:
        with open(f"artifacts/{label}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass


def _try_click_weekly_figures(page) -> None:
    """
    Navigate to Weekly Figures robustly.
    Handles cases where the menu item exists but is inside a collapsed sidebar/menu.
    """
    def _open_any_menu() -> None:
        # Common hamburger/toggler patterns
        candidates = [
            '[aria-label*="menu" i]',
            'button:has-text("Menu")',
            'button:has-text("MENU")',
            '.navbar-toggler',
            '.menu-toggle',
            '.sidebar-toggle',
            '.hamburger',
            'button:has(i.fa-bars)',
            'a:has(i.fa-bars)',
            'button:has(span:has-text("☰"))',
            'text=☰',
        ]
        for sel in candidates:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click()
                    page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    # We'll retry for a bit because UI hydration + responsive layout can change visibility.
    for _ in range(25):  # ~25s total
        wf = page.get_by_text("Weekly Figures", exact=False).first

        # If it's visible, click it normally.
        if wf.is_visible():
            wf.click()
            return

        # If it's in the DOM but not visible, the menu is likely collapsed. Try opening.
        _open_any_menu()

        # Another common pattern: sidebar exists but needs hover/focus—scroll it into view
        try:
            wf.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        page.wait_for_timeout(1000)

    # As a fallback, click the nearest clickable ancestor (like the <a> or <li> wrapping the span)
    try:
        span = page.locator('span.menu-title', has_text=re.compile(r"Weekly Figures", re.I)).first
        if span.count() > 0:
            # Try parent <a>
            parent_a = span.locator("xpath=ancestor::a[1]")
            if parent_a.count() > 0 and parent_a.first.is_visible():
                parent_a.first.click()
                return
            # Try parent <li>
            parent_li = span.locator("xpath=ancestor::li[1]")
            if parent_li.count() > 0 and parent_li.first.is_visible():
                parent_li.first.click()
                return
    except Exception:
        pass

    _dump_debug(page, "weekly_figures_click_failed")
    raise RuntimeError("Could not click Weekly Figures (present but not visible/clickable). See artifacts/.")


def scrape_week_last_week() -> Tuple[dt.date, List[ScrapedRow]]:
    """
    Login -> click Weekly Figures -> click Last Week -> scrape player rows.
    Returns (week_id, rows).
    """
    load_dotenv()

    base_url = os.getenv("NOJUICE_URL", "https://www.nojuice.ag")
    username = os.getenv("NOJUICE_USERNAME")
    password = os.getenv("NOJUICE_PASSWORD")

    if not username or not password:
        raise RuntimeError("Missing NOJUICE_USERNAME / NOJUICE_PASSWORD in environment")

    # Debug knobs
    headless = os.getenv("PW_HEADLESS", "1") != "0"
    slow_mo = int(os.getenv("PW_SLOW_MO", "0"))
    pause = os.getenv("PW_PAUSE", "0") == "1"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)

        def _is_on_login() -> bool:
            try:
                u = page.locator('input[name="customerID"]')
                pw = page.locator('input[name="Password"]')
                btn = page.locator('button[data-action="login"]')
                return u.count() > 0 and u.first.is_visible() and pw.count() > 0 and pw.first.is_visible() and btn.count() > 0
            except Exception:
                return False

        def _do_login() -> None:
            page.wait_for_selector('input[name="customerID"]', timeout=60000)
            page.fill('input[name="customerID"]', username)
            page.fill('input[name="Password"]', password)

            login_btn = page.locator('button[data-action="login"]').first
            login_btn.click()

            # JS-heavy app: don’t rely on navigation. Wait for the login form to disappear.
            for _ in range(60):  # up to ~60s
                if not _is_on_login():
                    return
                # if SweetAlert error pops, fail fast
                if page.locator(".swal2-container, .swal-modal").count() > 0:
                    _dump_debug(page, "login_swal_error")
                    raise RuntimeError("Login error popup detected (see artifacts).")
                page.wait_for_timeout(1000)

            _dump_debug(page, "login_still_visible")
            raise RuntimeError("Still on login screen after clicking LOGIN (see artifacts).")

        def _click_weekly_figures_tile() -> None:
            """
            Click the *tile* itself (not the hidden menu/title span).
            In your captured HTML the tile is:
              div.ic-square[data-action="get-weekly-figure"]
            """
            # Wait until the tile grid exists
            page.wait_for_selector(".menu-icons-panel, .squares-items, div.ic-square", timeout=60000)

            tile = page.locator('div.ic-square[data-action="get-weekly-figure"]').first
            try:
                tile.wait_for(state="visible", timeout=30000)
            except Exception:
                _dump_debug(page, "weekly_figures_tile_not_visible")
                raise RuntimeError("Weekly Figures tile not visible (see artifacts).")

            # Normal click first
            try:
                tile.scroll_into_view_if_needed()
                tile.click(timeout=30000)
                return
            except Exception:
                # Fallback: JS click (handles overlays / weird event handlers)
                try:
                    page.evaluate("el => el.click()", tile)
                    return
                except Exception:
                    _dump_debug(page, "weekly_figures_click_failed")
                    raise RuntimeError("Could not click Weekly Figures tile (see artifacts).")

        # --- Start ---
        page.goto(base_url, wait_until="domcontentloaded")

        # Always login each run (sessions are flaky on this site)
        if _is_on_login():
            _do_login()

            # Sometimes first click doesn’t take; retry once if still on login
            if _is_on_login():
                page.wait_for_timeout(1500)
                _do_login()

        # Optional: pause here when debugging in headed mode
        if pause and not headless:
            page.pause()

        # At this point we should be “inside” — wait for the tiles area to render
        try:
            page.wait_for_selector(".menu-icons-panel, .squares-items, div.ic-square", timeout=60000)
        except PWTimeoutError:
            _dump_debug(page, "post_login_no_tiles")
            raise RuntimeError("Logged in but did not see landing tiles (see artifacts).")

        # Click Weekly Figures tile via data-action
        _click_weekly_figures_tile()

        # Click "Last Week"
        try:
            page.get_by_text("Last Week", exact=True).click()
        except Exception:
            try:
                page.get_by_text("Last Week", exact=False).first.click()
            except Exception:
                _dump_debug(page, "last_week_tab_not_found")
                raise RuntimeError("Could not click 'Last Week' tab (see artifacts).")

        # Wait for table headers
        try:
            page.wait_for_selector("table thead tr th", timeout=60000)
        except PWTimeoutError:
            _dump_debug(page, "no_table_headers_after_last_week")
            raise RuntimeError("No table headers found after selecting Last Week (see artifacts).")

        page.wait_for_timeout(500)

        # Find the table that contains Customer + Week
        tables = page.locator("table")
        target_table = None
        target_headers = None

        for i in range(tables.count()):
            t = tables.nth(i)
            ths = t.locator("thead tr th")
            if ths.count() < 5:
                continue

            headers = [ths.nth(j).inner_text().strip() for j in range(ths.count())]
            norm = [h.strip().lower() for h in headers]
            if "customer" in norm and "week" in norm:
                target_table = t
                target_headers = headers
                break

        if target_table is None or target_headers is None:
            _dump_debug(page, "target_table_not_found")
            raise RuntimeError("Could not find a table with headers including Customer + Week (see artifacts).")

        week_id = _infer_week_id_from_headers(target_headers)

        norm_headers = [h.strip().lower() for h in target_headers]
        try:
            customer_idx = norm_headers.index("customer")
            week_idx = norm_headers.index("week")
        except ValueError:
            _dump_debug(page, "customer_week_col_missing")
            raise RuntimeError(f"Could not locate Customer/Week columns in headers: {target_headers} (see artifacts).")

        rows_out: List[ScrapedRow] = []
        body_rows = target_table.locator("tbody tr")

        for r in range(body_rows.count()):
            tr = body_rows.nth(r)
            tds = tr.locator("td")
            if tds.count() <= max(customer_idx, week_idx):
                continue

            customer = tds.nth(customer_idx).inner_text().strip()
            m = PYR_RE.match(customer)
            if not m:
                continue

            player_id = f"pyr{m.group(1)}".lower()
            week_val_raw = tds.nth(week_idx).inner_text().strip()
            week_amount = _parse_money(week_val_raw)

            rows_out.append(
                ScrapedRow(
                    week_id=week_id,
                    player_id=player_id,
                    week_amount=round(week_amount, 2),
                    raw_payload={
                        "customer": customer,
                        "week_cell": week_val_raw,
                        "cells": [tds.nth(i).inner_text().strip() for i in range(tds.count())],
                        "headers": target_headers,
                    },
                )
            )

        browser.close()
        return week_id, rows_out


def upsert_weekly_raw(week_id: dt.date, rows: List[ScrapedRow]) -> int:
    """
    Upsert into weeks + weekly_raw using DATABASE_URL (same as app).
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("Missing DATABASE_URL")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute(
        "insert into weeks (week_id) values (%s) on conflict (week_id) do nothing",
        (week_id.isoformat(),),
    )

    upsert_sql = """
        insert into weekly_raw (week_id, player_id, week_amount)
        values (%s, %s, %s)
        on conflict (week_id, player_id)
        do update set week_amount = excluded.week_amount
    """

    count = 0
    for row in rows:
        cur.execute(upsert_sql, (row.week_id.isoformat(), row.player_id, row.week_amount))
        count += 1

    conn.commit()
    conn.close()
    return count


def run_last_week_scrape_and_upsert() -> None:
    week_id, rows = scrape_week_last_week()
    n = upsert_weekly_raw(week_id, rows)
    print(json.dumps({"ok": True, "week_id": week_id.isoformat(), "rows_upserted": n}, indent=2))


if __name__ == "__main__":
    run_last_week_scrape_and_upsert()
