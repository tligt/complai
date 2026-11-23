"""
test_pricing.py — S74

Run: python test_pricing.py

The cases that would fail quietly: a yearly price that isn't 11 months, a
price shown with stray decimals, a commitment end that breaks on 29
February, and a plan priced with the customer given a number.
"""

import sys
from datetime import datetime, timezone

import pricing as P

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


check("Starter monthly", P.price("starter") == 49)
check("Starter yearly = 11 months", P.price("starter", "yearly") == 539)
check("Professional yearly = 11 months", P.price("professional", "yearly") == 1639)
check("saving is one month", P.yearly_saving("starter") == 49 and P.yearly_saving("professional") == 149)
check("per month on yearly", P.per_month_on_yearly("starter") == 44.92)
check("Enterprise has no list price", P.price("enterprise", "yearly") is None and P.price_label("advisory") is None)
check("labels", P.price_label("starter") == "€49/month" and P.price_label("professional", "yearly") == "€1,639/year")
check("eur whole and decimal", P.eur(539) == "€539" and P.eur(124.17) == "€124.17")
check("yearly listed first", P.CYCLES[0] == "yearly")

d = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
check("term end a year later", P.term_end(d, "yearly") == datetime(2027, 11, 23, 10, 0, tzinfo=timezone.utc))
check("29 Feb → 28 Feb", P.term_end(datetime(2028, 2, 29, tzinfo=timezone.utc), "yearly").day == 28)
check("monthly has no commitment", P.term_end(d, "monthly") is None and P.term_end(None, "yearly") is None)

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All pricing tests passed.")
