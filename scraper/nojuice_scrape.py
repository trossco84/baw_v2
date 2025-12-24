# scraper/nojuice_scraper.py
import os
import re
import json
import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

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
    # some cells show "-0" or "-0.00"
    try:
        return float(s)
    except ValueError:
        # last resort: pull first number-like token
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
        # Monday=0
        today = now
        last_monday = today - dt.timedelta(days=today.weekday())
        return last_monday - dt.timedelta(days=7)

    # infer year (handles year boundaries)
    candidate = dt.date(now.year, mm, dd)
    # if candidate is > ~30 days in the future relative to now, it's probably last year
    if candidate - now > dt.timedelta(days=30):
        candidate = dt.date(now.year - 1, mm, dd)
    return candidate


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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base_url, wait_until="domcontentloaded")

        # --- Login screen ---
        # We don't know input names; use first two inputs on the page (common for this UI).
        page.wait_for_timeout(300)  # tiny buffer for heavy background
        inputs = page.locator("input")
        if inputs.count() < 2:
            raise RuntimeError("Could not find login inputs")

        inputs.nth(0).fill(username)
        inputs.nth(1).fill(password)

        # Click LOGIN button
        page.get_by_role("button", name=re.compile(r"login", re.IGNORECASE)).click()

        # --- Landing tiles ---
        # Wait for tiles and click Weekly Figures
        try:
            page.get_by_text("Weekly Figures", exact=False).wait_for(timeout=15000)
        except PWTimeoutError:
            raise RuntimeError("Login may have failed: Weekly Figures tile not found")

        page.get_by_text("Weekly Figures", exact=False).click()

        # --- Weekly Figures page ---
        # Click "Last Week" tab
        page.get_by_text("Last Week", exact=True).click()

        # Wait for table to render
        # There are usually 2 tables (summary + detail). We'll scrape the detail table that has "Customer" header.
        try:
            page.get_by_text("Customer", exact=True).wait_for(timeout=15000)
        except PWTimeoutError:
            raise RuntimeError("Weekly figures table not found after selecting Last Week")

        # Find the table that contains the header "Customer"
        tables = page.locator("table")
        target_table = None
        for i in range(tables.count()):
            t = tables.nth(i)
            txt = t.inner_text()
            if "Customer" in txt and "Week" in txt:
                target_table = t
                break
        if target_table is None:
            raise RuntimeError("Could not identify target table containing Customer/Week")

        # Header texts (for week_id inference)
        header_cells = target_table.locator("thead tr").first.locator("th")
        header_texts = []
        for i in range(header_cells.count()):
            header_texts.append(header_cells.nth(i).inner_text().strip())

        week_id = _infer_week_id_from_headers(header_texts)

        # Map column indexes
        # Expected: Customer ... Week ... (we need Week index)
        norm_headers = [h.strip().lower() for h in header_texts]
        try:
            customer_idx = norm_headers.index("customer")
            week_idx = norm_headers.index("week")
        except ValueError:
            raise RuntimeError(f"Could not locate Customer/Week columns in headers: {header_texts}")

        # Scrape body rows
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
                continue  # skip agent totals, section headers, etc.

            player_id = f"pyr{m.group(1)}".lower()
            week_val_raw = tds.nth(week_idx).inner_text().strip()
            week_amount = _parse_money(week_val_raw)

            # capture raw row for debugging
            row_payload = {
                "customer": customer,
                "week_cell": week_val_raw,
                "cells": [tds.nth(i).inner_text().strip() for i in range(tds.count())],
                "headers": header_texts,
            }

            rows_out.append(
                ScrapedRow(
                    week_id=week_id,
                    player_id=player_id,
                    week_amount=round(week_amount, 2),
                    raw_payload=row_payload,
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

    # Ensure week exists
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
