"""
test_client_company.py — D-170

Run: python test_client_company.py

KYC is the client company's (the account's). What would fail silently: a
company's address counted for the account, VAT made mandatory again, or a
blank-but-spaces field passing.
"""

import sys

from database import ACCOUNT_DETAIL_FIELDS, KYC_FIELDS, missing_kyc

failures = []


def check(name, cond, detail=""):
    if not cond:
        failures.append(f"{name} {detail}")


full = {"legal_name": "Creagent SRL", "country": "BE", "address_street": "Rue de la Houlette 42",
        "address_postcode": "1170", "address_city": "Brussels", "phone": "+32 2 000 00 00"}
check("complete", missing_kyc(full) == [], str(missing_kyc(full)))
check("vat and number optional", "VAT number" not in KYC_FIELDS.values()
      and "enterprise_number" not in KYC_FIELDS)
check("blank counts as missing", missing_kyc({**full, "phone": "   "}) == ["phone number"])
check("none account", len(missing_kyc(None)) == len(KYC_FIELDS))
check("all KYC fields saveable", all(f in ACCOUNT_DETAIL_FIELDS for f in KYC_FIELDS),
      str([f for f in KYC_FIELDS if f not in ACCOUNT_DETAIL_FIELDS]))
check("company_name does not count", missing_kyc({"company_name": "X"})[0] == "legal name")

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("All client company tests passed.")
