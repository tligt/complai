"""
test_nbb_accounts.py — S76

Run: python test_nbb_accounts.py

The cases that would fail quietly: a company number with dots or a BE
prefix not recognised, last year's column (period N-1) read as this year's,
a correction filed later losing to the initial filing, a Belgian decimal
comma misread, and the NIS2 size called "small" when the turnover is unknown.
The real JSON's nesting is confirmed at the first real call; these shapes
are the ones accepted meanwhile.
"""

import sys

import nbb_accounts as N

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


check("dots and prefix", N.cbe_number("BE 0783.225.609") == "0783225609")
check("old 9-digit number", N.cbe_number("783225609") == "0783225609")
check("not a number", N.cbe_number("12345") is None and N.cbe_number(None) is None)

flat = {"Rubrics": [{"Code": "9087", "Period": "N", "Value": "12,4"},
                    {"Code": "9087", "Period": "NM1", "Value": "10"},
                    {"Code": "70", "Period": "N", "Value": "1234567.89"}]}
rb = N.rubrics(flat)
check("current year only", rb.get("9087") == 12.4)
check("turnover", rb.get("70") == 1234567.89)
nested = {"Data": {"Sections": [{"Items": [{"code": "1003", "value": 61.5}]}]}}
check("nested, lower-case keys, no period", N.rubrics(nested).get("1003") == 61.5)
check("thousands with dots and decimal comma", N._num("1.234,5") == 1234.5)
check("empty value ignored", N.rubrics({"Rubrics": [{"Code": "70", "Value": ""}]}) == {})

refs = [
    {"ReferenceNumber": "2024-1", "DepositDate": "2024-07-10", "ExerciseDates": {"EndDate": "2023-12-31"}},
    {"ReferenceNumber": "2025-1", "DepositDate": "2025-07-01", "ExerciseDates": {"EndDate": "2024-12-31"}},
    {"ReferenceNumber": "2025-2", "DepositDate": "2025-09-15", "ExerciseDates": {"EndDate": "2024-12-31"},
     "DepositType": "Correction"},
]
check("latest year, then latest deposit (the correction)", N.latest_reference(refs)["ReferenceNumber"] == "2025-2")
check("no filings", N.latest_reference([]) is None)

fig = N.figures_from(refs[2] | {"ModelType": "m02-f", "Currency": "EUR"}, flat)
check("figures kept", fig["fte"] == 12.4 and fig["turnover"] == 1234568 and fig["year_end"] == "2024-12-31"
      and fig["reference"] == "2025-2" and fig["source"] == "nbb")
check("1003 when 9087 missing", N.figures_from(refs[0], nested)["fte"] == 61.5)

check("size bands", [N.size_band(x) for x in (3, 10, 10.5, 50, 51, 151)]
      == ["1-10", "1-10", "11-50", "11-50", "51-150", "150+"])
check("no FTE, no band", N.size_band(None) is None)
check("NIS2 medium on staff", N.nis2_size({"fte": 50, "turnover": None}) == "medium or larger")
check("NIS2 medium on turnover", N.nis2_size({"fte": 5, "turnover": 12_000_000}) == "medium or larger")
check("NIS2 small needs both under", N.nis2_size({"fte": 12, "turnover": 900_000}) == "small")
check("NIS2 unknown without turnover", N.nis2_size({"fte": 12, "turnover": None}) is None)

import os
os.environ.pop("NBB_CBSO_KEY", None)
check("no key, no call", N.fetch("0783225609") is None and not N.configured())

if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("All NBB accounts tests passed.")
