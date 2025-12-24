import pandas as pd
import re
from datetime import date

PLAYER_RE = re.compile(r"^PYR\d+$", re.I)

def normalize_week_amount(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, str):
        x = x.replace(",", "")
    try:
        return float(x)
    except Exception:
        return 0.0


def infer_week_id(df: pd.DataFrame) -> str:
    """
    Infer the Monday date from a column like 'Mon (12/15)'
    """
    for col in df.columns:
        if col.startswith("Mon ("):
            mmdd = col.split("(")[1].split(")")[0]  # 12/15
            month, day = map(int, mmdd.split("/"))
            year = date.today().year
            return str(date(year, month, day))
    raise ValueError("Could not infer week_id from columns")


def translate_admin_export(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)

    # Keep only real player rows
    df = df[df["Customer"].astype(str).str.match(PLAYER_RE)]

    week_id = infer_week_id(df)

    out = pd.DataFrame({
        "player_id": df["Customer"].str.lower(),
        "week_amount": df["Week"].apply(normalize_week_amount),
        "pending": df.get("Pending", 0),
        "week_id": week_id
    })

    return out.reset_index(drop=True)
