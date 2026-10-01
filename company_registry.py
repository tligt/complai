"""
company_registry.py — S48: prefill a client from its official company number.

One adapter per source, all returning the same `RegistryRecord`, so a source
can be swapped without touching the caller. Belgium uses CBEAPI (cbeapi.be,
by Retinens) as a proof of value; the stated end state is the official
BCE/KBO web service, which will be one more adapter selected by
REGISTRY_BE_PROVIDER — nothing else changes (S48 scope lock).

  FR  recherche-entreprises.api.gouv.fr — official, free, no key.
  BE  CBEAPI — free tier, key in CBEAPI_KEY. Only the company number (public
      data) is sent.

Pure module, no Streamlit. Lookups never raise: a failure comes back as
`RegistryRecord.error`, so onboarding can carry on by hand.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

TIMEOUT = 10


@dataclass
class RegistryRecord:
    country: str
    number: str                      # normalised: BE 10 digits, FR 9 digits (SIREN)
    legal_name: str = ""
    legal_form: str = ""
    registered_address: str = ""
    nace_code: str = ""              # as the registry gives it (BE 62010, FR 70.10Z)
    nace_label: str = ""
    sector: str = ""                 # RECOSA sector option, from the NACE division
    website: str = ""
    active: bool | None = None
    source: str = ""
    error: str = ""


# ── NACE → RECOSA sector ─────────────────────────────────────────────────
# Must stay in step with app.py's _ONBOARD_SECTOR_OPTIONS. Mapped on the NACE
# division (first two digits), which BE (NACE-BEL) and FR (NAF) share. A
# suggestion for the onboarding form, never a legal classification: NIS2
# scope is deliberately not derived here (S48 scope lock).

_SECTOR_BY_DIVISION = {
    **{d: "SaaS / Technology" for d in (58, 62, 63)},
    **{d: "Professional services" for d in (69, 70, 71, 72, 73, 74, 78, 82)},
    **{d: "Healthcare / Medtech" for d in (21, 75, 86, 87, 88)},
    **{d: "Finance / Fintech" for d in (64, 65, 66)},
    **{d: "Logistics / Transport" for d in (49, 50, 51, 52, 53)},
    **{d: "Retail / E-commerce" for d in (45, 46, 47)},
    85: "Education",
    **{d: "Manufacturing" for d in range(10, 34) if d != 21},
}


def sector_for_nace(code: str) -> str:
    digits = re.sub(r"\D", "", code or "")
    if len(digits) < 2:
        return ""
    return _SECTOR_BY_DIVISION.get(int(digits[:2]), "Other")


# ── Number normalisation ─────────────────────────────────────────────────

def normalise_number(country: str, raw: str) -> tuple[str, str]:
    """(number, error). Accepts the usual written forms: 'BE 0783.225.609',
    '783225609', '552 032 534', or a 14-digit SIRET (its first 9 digits are
    the SIREN)."""
    digits = re.sub(r"\D", "", raw or "")
    if country == "BE":
        if len(digits) == 9:
            digits = "0" + digits
        if len(digits) != 10:
            return "", "A Belgian enterprise number has 10 digits (e.g. 0783.225.609)."
        # Modulo-97 check: the last two digits are 97 - (first 8 mod 97).
        if 97 - int(digits[:8]) % 97 != int(digits[8:]):
            return "", "That Belgian enterprise number is not valid (check digits don't match)."
        return digits, ""
    if country == "FR":
        if len(digits) == 14:
            digits = digits[:9]
        if len(digits) != 9:
            return "", "A French SIREN has 9 digits (or give the 14-digit SIRET)."
        return digits, ""
    return "", f"Company lookup isn't available for {country} yet."


# ── Adapters ─────────────────────────────────────────────────────────────

# INSEE "catégorie juridique" codes for the forms SMEs actually have.
_FR_LEGAL_FORMS = {
    "1000": "Entrepreneur individuel",
    "5410": "SARL", "5498": "EURL", "5499": "SARL",
    "5505": "SA", "5599": "SA", "5699": "SA",
    "5710": "SAS", "5720": "SASU",
    "5785": "SELAS", "5385": "SELARL",
    "6540": "SCI", "9220": "Association",
}

def _lookup_fr(number: str) -> RegistryRecord:
    rec = RegistryRecord(country="FR", number=number, source="recherche-entreprises.api.gouv.fr")
    try:
        r = requests.get("https://recherche-entreprises.api.gouv.fr/search",
                         params={"q": number, "per_page": 1}, timeout=TIMEOUT)
        r.raise_for_status()
        hits = [h for h in r.json().get("results", []) if h.get("siren") == number]
    except Exception as e:
        rec.error = f"The French registry could not be reached ({type(e).__name__})."
        return rec
    if not hits:
        rec.error = f"No French company found with SIREN {number}."
        return rec
    h = hits[0]
    siege = h.get("siege") or {}
    rec.legal_name = h.get("nom_raison_sociale") or h.get("nom_complet") or ""
    # INSEE gives a numeric code; an unmapped one is left blank rather than
    # printed as a number in a client's documents.
    rec.legal_form = _FR_LEGAL_FORMS.get(h.get("nature_juridique") or "", "")
    street = " ".join(x for x in (siege.get("numero_voie"), siege.get("type_voie"),
                                  siege.get("libelle_voie")) if x)
    town = " ".join(x for x in (siege.get("code_postal"), siege.get("libelle_commune")) if x)
    rec.registered_address = ("\n".join(x for x in (street, town) if x)
                              if street else siege.get("adresse") or "")
    rec.nace_code = h.get("activite_principale") or siege.get("activite_principale") or ""
    rec.sector = sector_for_nace(rec.nace_code)
    rec.active = h.get("etat_administratif") == "A"
    return rec


def _lookup_be_cbeapi(number: str) -> RegistryRecord:
    rec = RegistryRecord(country="BE", number=number, source="cbeapi.be")
    key = os.environ.get("CBEAPI_KEY", "").strip()
    if not key:
        rec.error = "Belgian lookup isn't configured (CBEAPI_KEY missing)."
        return rec
    try:
        r = requests.get(f"https://cbeapi.be/api/v1/company/{number}",
                         headers={"Authorization": f"Bearer {key}",
                                  "Accept": "application/json"},
                         timeout=TIMEOUT)
    except Exception as e:
        rec.error = f"The Belgian registry could not be reached ({type(e).__name__})."
        return rec
    if r.status_code == 404:
        rec.error = f"No Belgian company found with number {number}."
        return rec
    if r.status_code in (401, 403):
        rec.error = "The Belgian registry refused the API key (CBEAPI_KEY)."
        return rec
    if r.status_code == 429:
        rec.error = "Belgian lookup limit reached for today. Try again later."
        return rec
    if not r.ok:
        rec.error = f"The Belgian registry returned an error ({r.status_code})."
        return rec

    body = r.json()
    d = body.get("data", body) if isinstance(body, dict) else {}
    rec.legal_name = d.get("denomination") or ""
    # Short form ("SRL"), as clients already store it and documents print it
    rec.legal_form = d.get("juridical_form_short") or d.get("juridical_form") or ""
    a = d.get("address") or {}
    if isinstance(a, dict):
        street = " ".join(x for x in (a.get("street"), a.get("street_number")) if x)
        if a.get("box"):
            street += f" bte {a['box']}"
        town = " ".join(x for x in (a.get("post_code"), a.get("city")) if x)
        # Two lines, the format of clients.registered_address
        rec.registered_address = "\n".join(x for x in (street, town) if x)
    naces = d.get("nace_activities") or []
    if naces:
        main = naces[0]
        rec.nace_code = str(main.get("code") or "")
        rec.nace_label = main.get("description") or ""
        rec.sector = sector_for_nace(rec.nace_code)
    contact = d.get("contact_infos") or {}
    rec.website = (contact.get("web") or "") if isinstance(contact, dict) else ""
    status = (d.get("status") or "")
    rec.active = None if not status else str(status).lower() in ("active", "actif", "ac")
    return rec


_BE_PROVIDERS = {"cbeapi": _lookup_be_cbeapi}


def lookup(country: str, raw_number: str) -> RegistryRecord:
    """Look a company up by its official number. Never raises."""
    country = (country or "").upper()
    number, err = normalise_number(country, raw_number)
    if err:
        return RegistryRecord(country=country, number=raw_number, error=err)
    if country == "FR":
        return _lookup_fr(number)
    provider = os.environ.get("REGISTRY_BE_PROVIDER", "cbeapi")
    adapter = _BE_PROVIDERS.get(provider)
    if not adapter:
        return RegistryRecord(country="BE", number=number,
                              error=f"Unknown Belgian registry provider: {provider}")
    return adapter(number)
