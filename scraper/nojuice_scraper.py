# scraper/nojuice_scraper.py
import os
import re
import json
import time
import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv


PYR_RE = re.compile(r"^PYR(\d+)$", re.IGNORECASE)
MON_HEADER_RE = re.compile(r"Mon\s*\((\d{1,2})/(\d{1,2})\)", re.IGNORECASE)


@dataclass
class ScrapedRow:
    week_id: dt.date
    player_id: str
    week_amount: float
    raw_payload: Dict[str, Any]


def _ensure_artifacts_dir() -> Path:
    p = Path("artifacts")
    p.mkdir(exist_ok=True)
    return p


def _dump_artifact(label: str, payload: Any) -> None:
    """
    Writes artifacts/{label}.json (or .txt if not JSON serializable)
    """
    _ensure_artifacts_dir()
    out_json = Path("artifacts") / f"{label}.json"
    out_txt = Path("artifacts") / f"{label}.txt"
    try:
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    except Exception:
        with out_txt.open("w", encoding="utf-8") as f:
            f.write(str(payload))


def _parse_money(x: Any) -> float:
    s = ("" if x is None else str(x)).strip()
    if s == "":
        return 0.0
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


def _infer_week_id_from_headers(header_texts: List[str], now: Optional[dt.date] = None) -> dt.date:
    now = now or dt.date.today()

    mm = dd = None
    for h in header_texts:
        m = MON_HEADER_RE.search(h)
        if m:
            mm, dd = int(m.group(1)), int(m.group(2))
            break

    if mm is None:
        today = now
        last_monday = today - dt.timedelta(days=today.weekday())
        return last_monday - dt.timedelta(days=7)

    candidate = dt.date(now.year, mm, dd)
    if candidate - now > dt.timedelta(days=30):
        candidate = dt.date(now.year - 1, mm, dd)
    return candidate


def _first_key(d: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    dl = {k.lower(): k for k in d.keys()}
    for c in candidates:
        if c.lower() in dl:
            return dl[c.lower()]
    return None


def _extract_token_from_json(obj: Any) -> Optional[str]:
    """
    Tries hard to find a JWT/bearer in a JSON response.
    """
    if obj is None:
        return None

    if isinstance(obj, str):
        # sometimes backend returns the token directly as a string
        if obj.count(".") >= 2 and len(obj) > 40:
            return obj
        return None

    if isinstance(obj, dict):
        # common token keys
        key = _first_key(obj, [
            "token",
            "access_token",
            "accessToken",
            "jwt",
            "bearer",
            "id_token",
            "idToken",
            "authorization",
        ])
        if key and isinstance(obj.get(key), str):
            return obj[key]

        # nested shapes
        for nest_key in ["data", "result", "payload", "auth", "session"]:
            if nest_key in obj:
                t = _extract_token_from_json(obj[nest_key])
                if t:
                    return t

    if isinstance(obj, list):
        for item in obj:
            t = _extract_token_from_json(item)
            if t:
                return t

    return None


def _extract_code_from_json(obj: Any) -> Optional[str]:
    """
    If authenticateCustomer returns an OAuth-like "code", grab it.
    """
    if not isinstance(obj, dict):
        return None
    key = _first_key(obj, ["code", "auth_code", "authCode", "authorization_code"])
    if key and isinstance(obj.get(key), str):
        return obj[key]
    # sometimes nested
    for nest_key in ["data", "result", "payload"]:
        if nest_key in obj and isinstance(obj[nest_key], dict):
            key2 = _first_key(obj[nest_key], ["code", "auth_code", "authCode"])
            if key2 and isinstance(obj[nest_key].get(key2), str):
                return obj[nest_key][key2]
    return None


class NoJuiceAPI:
    """
    Minimal API client to:
      - authenticateCustomer (username/password) => token (or code)
      - getWeeklyFigureByAgent
    """
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.sess = requests.Session()

        # Basic headers that match browser-style XHR (not all are required, but helps)
        self.sess.headers.update({
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
            "origin": self.base_url,
            "referer": self.base_url + "/",
            "user-agent": os.getenv(
                "NOJUICE_UA",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        })

    def authenticate_customer(self, customer_id: str, password: str, multiaccount: str = "1") -> str:
        """
        Calls /cloud/api/System/authenticateCustomer and returns a token.
        If response is code-based, we fail loudly with artifacts so you can capture the follow-up exchange endpoint.
        """
        url = f"{self.base_url}/cloud/api/System/authenticateCustomer"

        # IMPORTANT: your captured request included these exact fields
        data = {
            "customerID": customer_id,
            "state": "true",
            "password": password,
            "multiaccount": multiaccount,
            "response_type": "code",
            "client_id": customer_id,
            "domain": "nojuice.ag",
            "redirect_uri": "nojuice.ag",
            "operation": "authenticateCustomer",
            "RRO": "1",
        }

        # per your capture: Bearer undefined (keep it exactly)
        headers = {"authorization": "Bearer undefined"}

        r = self.sess.post(url, data=data, headers=headers, timeout=30)
        _dump_artifact("auth_customer_status", {"status_code": r.status_code, "url": url})
        _dump_artifact("auth_customer_headers", dict(r.headers))

        # Sometimes returns JSON, sometimes text/html with JSON inside, etc.
        ct = (r.headers.get("content-type") or "").lower()
        text = r.text

        # Try JSON first
        obj = None
        if "application/json" in ct:
            try:
                obj = r.json()
                _dump_artifact("auth_customer_response_json", obj)
            except Exception as e:
                _dump_artifact("auth_customer_json_parse_error", {"error": str(e), "body_head": text[:2000]})
        else:
            # still might be JSON despite wrong content-type
            try:
                obj = r.json()
                _dump_artifact("auth_customer_response_json_guess", obj)
            except Exception:
                _dump_artifact("auth_customer_response_text", text[:4000])

        if r.status_code != 200:
            raise RuntimeError(f"authenticateCustomer failed: HTTP {r.status_code} (see artifacts/auth_customer_*)")

        token = _extract_token_from_json(obj) if obj is not None else None
        if token:
            return token

        code = _extract_code_from_json(obj) if obj is not None else None
        if code:
            # We need the code exchange endpoint (usually in Network right after authenticateCustomer).
            _dump_artifact("auth_customer_returned_code", {"code": code, "note": "Need code-exchange XHR after login"})
            raise RuntimeError(
                "authenticateCustomer returned a CODE, not a TOKEN. "
                "In DevTools, capture the NEXT XHR after authenticateCustomer (code exchange) and paste as cURL."
            )

        # If neither token nor code: dump body and fail
        _dump_artifact("auth_customer_unrecognized_response", {"content_type": ct, "body_head": text[:4000]})
        raise RuntimeError("authenticateCustomer succeeded but token could not be extracted (see artifacts).")

    def get_weekly_figure_by_agent(
        self,
        token: str,
        agent_id: str,
        agent_owner: str,
        agent_site: str,
        week: int = 1,
        betting_type: str = "A",
        layout: str = "byDay",
        big_amount: int = 500,
        rro: int = 1,
    ) -> Dict[str, Any]:
        """
        Calls /cloud/api/Manager/getWeeklyFigureByAgent.
        NOTE: Token must be in BOTH Authorization header and token=... in body for many endpoints.
        """
        url = f"{self.base_url}/cloud/api/Manager/getWeeklyFigureByAgent"
        headers = {"authorization": f"Bearer {token}"}

        data = {
            "agentID": agent_id,
            "week": str(week),
            "type": betting_type,
            "layout": layout,
            "bigAmount": str(big_amount),
            "operation": "getWeeklyFigureByAgent",
            "RRO": str(rro),
            "agentOwner": agent_owner,
            "agentSite": str(agent_site),
            # critical for this backend: include token in payload as well
            "token": token,
        }

        r = self.sess.post(url, data=data, headers=headers, timeout=30)
        _dump_artifact("weekly_figures_status", {"status_code": r.status_code, "url": url})
        if r.status_code != 200:
            _dump_artifact("weekly_figures_body_head", r.text[:2000])
            raise RuntimeError(f"getWeeklyFigureByAgent failed: HTTP {r.status_code} (see artifacts/weekly_figures_*)")

        try:
            payload = r.json()
        except Exception as e:
            _dump_artifact("weekly_figures_json_parse_error", {"error": str(e), "body_head": r.text[:4000]})
            raise RuntimeError("getWeeklyFigureByAgent returned non-JSON (see artifacts).")

        _dump_artifact("weekly_figures_response_json", payload)
        return payload


def _find_rows_in_payload(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Attempts to find the table rows and headers in the JSON.
    Because we don't have the exact shape yet, this searches common patterns.
    Returns (rows, headers_guess).
    """
    # candidates where rows might live
    candidate_paths = [
        ("rows",),
        ("data",),
        ("data", "rows"),
        ("result",),
        ("result", "rows"),
        ("weeklyFigure",),
        ("weeklyFigure", "rows"),
        ("weeklyFigures",),
        ("weeklyFigures", "rows"),
        ("table", "rows"),
        ("table", "data"),
        ("list",),
    ]

    rows: List[Dict[str, Any]] = []
    for path in candidate_paths:
        cur: Any = payload
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if not ok:
            continue

        if isinstance(cur, list) and cur and isinstance(cur[0], dict):
            rows = cur
            break

    # headers might be present too
    headers: List[str] = []
    header_candidates = [
        ("headers",),
        ("columns",),
        ("data", "headers"),
        ("data", "columns"),
        ("table", "headers"),
        ("table", "columns"),
    ]
    for path in header_candidates:
        cur = payload
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if not ok:
            continue
        if isinstance(cur, list) and cur and all(isinstance(x, (str, dict)) for x in cur):
            # if dicts, try name/title keys
            if isinstance(cur[0], dict):
                for col in cur:
                    for key in ("name", "title", "label", "header"):
                        if key in col and isinstance(col[key], str):
                            headers.append(col[key])
                            break
            else:
                headers = [str(x) for x in cur]
            break

    return rows, headers


def _row_get(row: Dict[str, Any], *names: str) -> Optional[Any]:
    """
    Case-insensitive lookup for one of several key names.
    """
    lower = {k.lower(): k for k in row.keys()}
    for n in names:
        k = lower.get(n.lower())
        if k is not None:
            return row.get(k)
    return None


def scrape_week_last_week() -> Tuple[dt.date, List[ScrapedRow]]:
    """
    API mode:
      - authenticateCustomer => token
      - getWeeklyFigureByAgent(week=1) => rows
      - parse (Customer, Week)
    """
    load_dotenv()

    base_url = os.getenv("NOJUICE_URL", "https://nojuice.ag").rstrip("/")
    username = os.getenv("NOJUICE_USERNAME")  # customerID
    password = os.getenv("NOJUICE_PASSWORD")

    # Agent identity: often same as username, but keep configurable
    agent_id = os.getenv("NOJUICE_AGENT_ID", username or "")
    agent_owner = os.getenv("NOJUICE_AGENT_OWNER", username or "")
    agent_site = os.getenv("NOJUICE_AGENT_SITE", "1")

    if not username or not password:
        raise RuntimeError("Missing NOJUICE_USERNAME / NOJUICE_PASSWORD in environment")
    if not agent_id or not agent_owner:
        raise RuntimeError("Missing NOJUICE_AGENT_ID / NOJUICE_AGENT_OWNER (or NOJUICE_USERNAME)")

    api = NoJuiceAPI(base_url=base_url)

    # login -> token
    token = api.authenticate_customer(customer_id=username, password=password, multiaccount="1")
    _dump_artifact("auth_token_extracted", {"token_prefix": token[:16] + "...", "len": len(token)})

    # weekly figures
    payload = api.get_weekly_figure_by_agent(
        token=token,
        agent_id=agent_id,
        agent_owner=agent_owner,
        agent_site=agent_site,
        week=1,  # last week
        betting_type="A",
        layout="byDay",
        big_amount=500,
        rro=1,
    )

    rows, headers = _find_rows_in_payload(payload)
    if not rows:
        _dump_artifact("weekly_figures_no_rows_found", {"keys": list(payload.keys())})
        raise RuntimeError("Could not find rows in weekly figures JSON (see artifacts/weekly_figures_response_json).")

    # Determine week_id
    # If headers contain "Mon (MM/DD)", infer from that; otherwise default to previous week's Monday.
    week_id = _infer_week_id_from_headers(headers if headers else [])

    out: List[ScrapedRow] = []
    for row in rows:
        customer = _row_get(row, "Customer", "customer", "customerID", "player", "Player", "Cust", "CustID")
        if customer is None:
            continue
        customer = str(customer).strip()

        m = PYR_RE.match(customer)
        if not m:
            # skip anything not PYR### (totals, groups, etc)
            continue

        # The "Week" field is the weekly total. Try multiple key names.
        week_val = _row_get(row, "Week", "week", "Weekly", "weekly", "Total", "total")
        if week_val is None:
            # as last resort: try numeric field that looks like week total
            # (keep row_payload anyway for debugging)
            week_val = 0

        out.append(
            ScrapedRow(
                week_id=week_id,
                player_id=f"pyr{m.group(1)}".lower(),
                week_amount=round(_parse_money(week_val), 2),
                raw_payload=row,
            )
        )

    if not out:
        _dump_artifact("weekly_figures_parsed_zero_rows", {"row_count": len(rows), "sample_row": rows[0] if rows else None})
        raise RuntimeError("Parsed zero PYR rows from weekly figures payload (see artifacts).")

    return week_id, out


def upsert_weekly_raw(week_id: dt.date, rows: List[ScrapedRow]) -> int:
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
