"""
pricing.py — S74, 23 Nov 2026. The plans' prices, in one place.

Classic SaaS: each plan per month or per year, and a year costs 11 months
(one month free). Prices are in euro, excluding VAT, and must match
recosa.eu/pricing. Enterprise and Advisory are priced with the customer.
"""

from datetime import datetime

MONTHLY_EUR = {"starter": 49, "professional": 149}
YEAR_MONTHS = 11                       # a year = 11 × the monthly fee
CYCLES = ("yearly", "monthly")         # yearly first: the one to choose
CYCLE_LABELS = {"monthly": "Monthly", "yearly": "Yearly"}


def price(plan: str, cycle: str = "monthly") -> int | None:
    """The price for one billing period, or None for a plan priced with the customer."""
    m = MONTHLY_EUR.get(plan)
    if m is None:
        return None
    return m * YEAR_MONTHS if cycle == "yearly" else m


def yearly_saving(plan: str) -> int | None:
    """What a year saves against twelve monthly payments: one month."""
    m = MONTHLY_EUR.get(plan)
    return None if m is None else m * 12 - m * YEAR_MONTHS


def per_month_on_yearly(plan: str) -> float | None:
    p = price(plan, "yearly")
    return None if p is None else round(p / 12, 2)


def eur(amount: float | int) -> str:
    """€539, €44.92 — no decimals when whole, two otherwise, comma for thousands."""
    return f"€{amount:,.0f}" if float(amount).is_integer() else f"€{amount:,.2f}"


def price_label(plan: str, cycle: str = "monthly") -> str | None:
    """English: '€49/month', '€539/year'. Callers translate the unit with tr()."""
    p = price(plan, cycle)
    if p is None:
        return None
    return f"{eur(p)}/{'year' if cycle == 'yearly' else 'month'}"


def term_end(start: datetime, cycle: str | None) -> datetime | None:
    """When a yearly commitment started on `start` ends (same day, next year;
    29 Feb → 28 Feb). Monthly runs month to month: no commitment date."""
    if cycle != "yearly" or not start:
        return None
    try:
        return start.replace(year=start.year + 1)
    except ValueError:
        return start.replace(year=start.year + 1, day=28)
