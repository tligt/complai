"""
nbb_accounts.py — S76, 23 Nov 2026. A Belgian company's size from its filed
annual accounts, through the National Bank's free "Authentic Data" web
service (Central Balance Sheet Office, developer.cbso.nbb.be).

Two calls, with the subscription key in the NBB-CBSO-Subscription-Key header:
  1. GET /legalEntity/{CBE number}/references  → the filings, newest last
  2. GET /deposit/{reference}/accountingData    (Accept: application/x.jsonxbrl)
     → the filing's figures as JSON, one entry per rubric code.

Rubric codes read (CBSO taxonomy, same in every model that has them):
  9087  average number of employees, in full-time equivalents (all models)
  1003  average number of employees, total FTE (social balance sheet, full model)
  70    turnover (full model; optional in the abbreviated and micro models)

The JSON's exact nesting is read loosely (any object holding a rubric code
and a value), because it is confirmed only by the first real call — see
test_nbb_accounts.py for the shapes accepted. Without NBB_CBSO_KEY every
function returns None and the app shows nothing.

Limits: Belgium only; accounts lag 6–18 months behind; sole traders and most
non-profits file none; non-standardised accounts exist only as PDF.
"""

import os
import re
import uuid
from datetime import datetime, timezone

BASE_URL = "https://ws.cbso.nbb.be/authentic"
FTE_CODES = ("9087", "1003")
TURNOVER_CODE = "70"
# NIS2 size test (Commission Recommendation 2003/361, as NIS2 Art. 2 uses it).
NIS2_MEDIUM_STAFF = 50
NIS2_MEDIUM_TURNOVER = 10_000_000


def configured() -> bool:
    return bool((os.environ.get("NBB_CBSO_KEY") or "").strip())


def cbe_number(raw: str | None) -> str | None:
    """'BE 0783.225.609' → '0783225609'. A 9-digit old number gets its 0."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "0" + digits
    return digits if len(digits) == 10 else None


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:          # 1.234,5 → 1234.5
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def rubrics(data) -> dict[str, float]:
    """Every rubric code → value for the current year, from the filing's JSON.
    Accepts any object with a code key (Code / code / Rubric / rubric) and a
    value key (Value / value); with a period key, only the current year
    ('N', or none) counts."""
    out: dict[str, float] = {}

    def walk(x):
        if isinstance(x, dict):
            code = next((x[k] for k in ("Code", "code", "Rubric", "rubric") if k in x), None)
            val = next((x[k] for k in ("Value", "value") if k in x), None)
            period = next((x[k] for k in ("Period", "period") if k in x), None)
            if code is not None and val is not None and str(period or "N").upper() in ("N", "CURRENT"):
                n = _num(val)
                if n is not None:
                    out.setdefault(str(code).strip(), n)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    return out


def latest_reference(refs: list[dict]) -> dict | None:
    """The newest filing: latest financial year end, then latest deposit
    (a correction filed later replaces the initial one)."""
    usable = [r for r in refs or [] if r.get("ReferenceNumber")]
    if not usable:
        return None
    return max(usable, key=lambda r: (((r.get("ExerciseDates") or {}).get("EndDate") or ""),
                                      r.get("DepositDate") or ""))


def figures_from(ref: dict, data) -> dict:
    """What RECOSA keeps from one filing (clients.filed_figures)."""
    rb = rubrics(data)
    fte = next((rb[c] for c in FTE_CODES if c in rb), None)
    return {
        "source": "nbb",
        "reference": ref.get("ReferenceNumber"),
        "year_end": (ref.get("ExerciseDates") or {}).get("EndDate"),
        "filed_on": ref.get("DepositDate"),
        "model": ref.get("ModelType"),
        "fte": round(fte, 1) if fte is not None else None,
        "turnover": round(rb[TURNOVER_CODE]) if TURNOVER_CODE in rb else None,
        "currency": ref.get("Currency") or "EUR",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def size_band(fte: float | None) -> str | None:
    """The Company profile's Employees choice (client_setup.SIZE_OPTIONS)."""
    if fte is None:
        return None
    if fte <= 10:
        return "1-10"
    if fte <= 50:
        return "11-50"
    if fte <= 150:
        return "51-150"
    return "150+"


def nis2_size(fig: dict | None) -> str | None:
    """'small' / 'medium or larger' from the filed figures, None when unknown.
    NIS2 counts a company medium from 50 staff OR €10 M turnover (the balance
    sheet test is not read here, so 'small' is only said when both are under)."""
    if not fig:
        return None
    fte, turnover = fig.get("fte"), fig.get("turnover")
    if (fte is not None and fte >= NIS2_MEDIUM_STAFF) or \
            (turnover is not None and turnover >= NIS2_MEDIUM_TURNOVER):
        return "medium or larger"
    if fte is not None and turnover is not None:
        return "small"
    return None


# ── The calls ──────────────────────────────────────────────────────────────

def _get(path: str, accept: str):
    import requests
    r = requests.get(f"{BASE_URL}{path}", timeout=20, headers={
        "NBB-CBSO-Subscription-Key": os.environ["NBB_CBSO_KEY"].strip(),
        "X-Request-Id": str(uuid.uuid4()), "Accept": accept})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch(raw_number: str | None) -> dict | None:
    """The latest filed figures for a Belgian company number, or None (no key,
    no number, nothing filed, or the service failed — logged, never raised)."""
    num = cbe_number(raw_number)
    if not (num and configured()):
        return None
    try:
        ref = latest_reference(_get(f"/legalEntity/{num}/references", "application/json") or [])
        if not ref:
            return None
        data = _get(f"/deposit/{ref['ReferenceNumber']}/accountingData", "application/x.jsonxbrl")
        return figures_from(ref, data or {})
    except Exception as e:
        print(f"NBB lookup failed for {num}: {e}")
        return None


def refresh_client(client: dict, by: str | None = None) -> dict | None:
    """Fetch and store on the company (clients.filed_figures). Belgian
    companies with a number only. Returns the figures stored, or None."""
    if (client.get("country") or "").upper() != "BE":
        return None
    fig = fetch(client.get("enterprise_number"))
    if not fig:
        return None
    try:
        from database import get_supabase_admin
        get_supabase_admin().table("clients").update({"filed_figures": fig}) \
            .eq("id", client["id"]).execute()
    except Exception as e:
        print(f"Could not store the NBB figures: {e}")
        return None
    return fig
