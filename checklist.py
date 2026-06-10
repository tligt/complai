import re
from dataclasses import dataclass
from crawler import CrawlResult

# ── Status constants ──────────────────────────────────────────────────────────
OK      = "ok"       # Compliant
WARN    = "warn"     # Partial / needs attention
FAIL    = "fail"     # Missing / non-compliant

STATUS_LABELS = {
    OK:   "✅ Compliant",
    WARN: "⚠️  Needs attention",
    FAIL: "❌ Missing",
}

STATUS_COLORS = {
    OK:   "#0F6E56",
    WARN: "#BA7517",
    FAIL: "#993C1D",
}


@dataclass
class CheckResult:
    id: str
    regulation: str
    category: str
    label: str
    description: str
    status: str        # ok / warn / fail
    detail: str        # What was found or not found


@dataclass
class AuditResult:
    url: str
    checks: list
    score: int         # 0-100
    risk_level: str    # Green / Amber / Red
    ok_count: int
    warn_count: int
    fail_count: int


def _contains(text: str, *keywords) -> bool:
    """Case-insensitive keyword check."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _has_page(result: CrawlResult, *keys) -> tuple[bool, str]:
    """Check if any of the given page keys exist in found_pages."""
    for key in keys:
        for found_key, content in result.found_pages.items():
            if key.lower() in found_key.lower():
                return True, content
    return False, ""


def run_checklist(result: CrawlResult) -> AuditResult:
    checks = []
    homepage_text = result.homepage_text
    homepage_html = result.homepage_html
    all_text = homepage_text + " ".join(result.found_pages.values())

    # ── GDPR checks ──────────────────────────────────────────────────────────

    # G1 — Privacy policy page exists
    has_privacy, privacy_text = _has_page(result, "privacy", "gdpr", "rgpd", "privacybeleid", "confidentialite")
    checks.append(CheckResult(
        id="G1", regulation="GDPR", category="Privacy Policy",
        label="Privacy policy page exists",
        description="A privacy policy page must be accessible from the website.",
        status=OK if has_privacy else FAIL,
        detail="Privacy policy page found." if has_privacy else "No privacy policy page detected."
    ))

    # G2 — Privacy policy mentions data controller identity
    if has_privacy:
        has_controller = _contains(privacy_text, "controller", "responsable", "verwerkingsverantwoordelijke", "company", "société", "onderneming")
        checks.append(CheckResult(
            id="G2", regulation="GDPR", category="Privacy Policy",
            label="Data controller identity disclosed",
            description="The privacy policy must identify who is responsible for data processing (Article 13 GDPR).",
            status=OK if has_controller else WARN,
            detail="Controller identity found in privacy policy." if has_controller else "Controller identity not clearly identified in privacy policy."
        ))
    else:
        checks.append(CheckResult(
            id="G2", regulation="GDPR", category="Privacy Policy",
            label="Data controller identity disclosed",
            description="The privacy policy must identify who is responsible for data processing (Article 13 GDPR).",
            status=FAIL,
            detail="Cannot assess — no privacy policy found."
        ))

    # G3 — Data subject rights mentioned
    if has_privacy:
        has_rights = _contains(privacy_text, "right to access", "right to erasure", "right to rectif",
                                "droit d'accès", "droit à l'effacement", "recht op inzage",
                                "data subject rights", "droits des personnes", "rechten van betrokkenen")
        checks.append(CheckResult(
            id="G3", regulation="GDPR", category="Privacy Policy",
            label="Data subject rights described",
            description="The privacy policy must describe rights of access, erasure, rectification, and portability (Articles 15-22 GDPR).",
            status=OK if has_rights else WARN,
            detail="Data subject rights found in privacy policy." if has_rights else "Data subject rights not clearly described."
        ))
    else:
        checks.append(CheckResult(
            id="G3", regulation="GDPR", category="Privacy Policy",
            label="Data subject rights described",
            description="The privacy policy must describe rights of access, erasure, rectification, and portability (Articles 15-22 GDPR).",
            status=FAIL,
            detail="Cannot assess — no privacy policy found."
        ))

    # G4 — Legal basis for processing mentioned
    if has_privacy:
        has_legal_basis = _contains(privacy_text, "legal basis", "lawful basis", "legitimate interest",
                                     "base légale", "intérêt légitime", "rechtsgrondslag",
                                     "consent", "consentement", "toestemming", "contract")
        checks.append(CheckResult(
            id="G4", regulation="GDPR", category="Privacy Policy",
            label="Legal basis for processing stated",
            description="The privacy policy must specify the legal basis for each processing activity (Article 13(1)(c) GDPR).",
            status=OK if has_legal_basis else WARN,
            detail="Legal basis found in privacy policy." if has_legal_basis else "Legal basis for processing not clearly stated."
        ))
    else:
        checks.append(CheckResult(
            id="G4", regulation="GDPR", category="Privacy Policy",
            label="Legal basis for processing stated",
            description="The privacy policy must specify the legal basis for each processing activity (Article 13(1)(c) GDPR).",
            status=FAIL,
            detail="Cannot assess — no privacy policy found."
        ))

    # G5 — DPO or contact for data enquiries
    has_dpo = _contains(all_text, "dpo", "data protection officer", "délégué à la protection",
                          "functionaris gegevensbescherming", "privacy@", "dpo@", "gdpr@")
    checks.append(CheckResult(
        id="G5", regulation="GDPR", category="Privacy Policy",
        label="DPO or privacy contact provided",
        description="A contact point for data protection enquiries must be provided (Article 13(1)(b) GDPR).",
        status=OK if has_dpo else WARN,
        detail="DPO or privacy contact found." if has_dpo else "No DPO or dedicated privacy contact found."
    ))

    # G6 — Retention periods mentioned
    if has_privacy:
        has_retention = _contains(privacy_text, "retention", "retain", "how long", "durée de conservation",
                                    "bewaartermijn", "stored for", "conserv")
        checks.append(CheckResult(
            id="G6", regulation="GDPR", category="Privacy Policy",
            label="Data retention periods stated",
            description="The privacy policy must specify how long personal data is retained (Article 13(2)(a) GDPR).",
            status=OK if has_retention else WARN,
            detail="Retention periods found in privacy policy." if has_retention else "Data retention periods not specified."
        ))
    else:
        checks.append(CheckResult(
            id="G6", regulation="GDPR", category="Privacy Policy",
            label="Data retention periods stated",
            description="The privacy policy must specify how long personal data is retained (Article 13(2)(a) GDPR).",
            status=FAIL,
            detail="Cannot assess — no privacy policy found."
        ))

    # G7 — Third-party processors / data transfers mentioned
    if has_privacy:
        has_transfers = _contains(privacy_text, "third party", "third-party", "tiers", "derde partij",
                                    "transfer", "transfert", "processor", "sub-processor",
                                    "international transfer", "adequacy")
        checks.append(CheckResult(
            id="G7", regulation="GDPR", category="Privacy Policy",
            label="Third-party processors / transfers disclosed",
            description="The privacy policy must disclose data transfers to third parties and international transfers (Article 13(1)(e) GDPR).",
            status=OK if has_transfers else WARN,
            detail="Third-party disclosures found." if has_transfers else "No disclosure of third-party processors or data transfers."
        ))
    else:
        checks.append(CheckResult(
            id="G7", regulation="GDPR", category="Privacy Policy",
            label="Third-party processors / transfers disclosed",
            description="The privacy policy must disclose data transfers to third parties and international transfers (Article 13(1)(e) GDPR).",
            status=FAIL,
            detail="Cannot assess — no privacy policy found."
        ))

    # ── ePrivacy / Cookie checks ──────────────────────────────────────────────

    # C1 — Cookie banner / consent mechanism
    has_cookie_banner = _contains(homepage_html,
        "cookie", "cookieconsent", "cookie-consent", "cookiebot",
        "onetrust", "axeptio", "tarteaucitron", "usercentrics",
        "didomi", "quantcast", "cookiepro"
    )
    checks.append(CheckResult(
        id="C1", regulation="ePrivacy", category="Cookie Consent",
        label="Cookie consent mechanism present",
        description="A cookie consent banner or mechanism is required before placing non-essential cookies (ePrivacy Directive, Article 5(3)).",
        status=OK if has_cookie_banner else FAIL,
        detail="Cookie consent mechanism detected on homepage." if has_cookie_banner else "No cookie consent mechanism detected."
    ))

    # C2 — Cookie policy page
    has_cookie_page, cookie_text = _has_page(result, "cookie")
    checks.append(CheckResult(
        id="C2", regulation="ePrivacy", category="Cookie Consent",
        label="Cookie policy page exists",
        description="A dedicated cookie policy must explain what cookies are used and why.",
        status=OK if has_cookie_page else WARN,
        detail="Cookie policy page found." if has_cookie_page else "No dedicated cookie policy page found."
    ))

    # C3 — Cookie categories described
    if has_cookie_page:
        has_categories = _contains(cookie_text,
            "functional", "analytics", "marketing", "advertising", "performance",
            "fonctionnel", "analytique", "publicitaire", "functioneel", "analytisch"
        )
        checks.append(CheckResult(
            id="C3", regulation="ePrivacy", category="Cookie Consent",
            label="Cookie categories described",
            description="The cookie policy must distinguish between functional, analytics, and marketing cookies.",
            status=OK if has_categories else WARN,
            detail="Cookie categories found in cookie policy." if has_categories else "Cookie categories not clearly described."
        ))
    else:
        checks.append(CheckResult(
            id="C3", regulation="ePrivacy", category="Cookie Consent",
            label="Cookie categories described",
            description="The cookie policy must distinguish between functional, analytics, and marketing cookies.",
            status=WARN,
            detail="Cannot fully assess — no dedicated cookie policy page found."
        ))

    # ── Accessibility checks ──────────────────────────────────────────────────

    # A1 — Language attribute on HTML
    has_lang = bool(re.search(r'<html[^>]+lang\s*=', homepage_html, re.IGNORECASE))
    checks.append(CheckResult(
        id="A1", regulation="EAA", category="Accessibility",
        label="HTML language attribute set",
        description="The page language must be declared in the HTML tag for screen readers (WCAG 2.1, EAA Article 4).",
        status=OK if has_lang else FAIL,
        detail="HTML lang attribute found." if has_lang else "No HTML lang attribute detected."
    ))

    # A2 — Images have alt text
    img_tags = re.findall(r'<img[^>]*>', homepage_html, re.IGNORECASE)
    imgs_with_alt = [img for img in img_tags if re.search(r'alt\s*=', img, re.IGNORECASE)]
    if img_tags:
        alt_ratio = len(imgs_with_alt) / len(img_tags)
        a2_status = OK if alt_ratio >= 0.9 else (WARN if alt_ratio >= 0.5 else FAIL)
        a2_detail = f"{len(imgs_with_alt)} of {len(img_tags)} images have alt text ({int(alt_ratio*100)}%)."
    else:
        a2_status = OK
        a2_detail = "No images detected on homepage."
    checks.append(CheckResult(
        id="A2", regulation="EAA", category="Accessibility",
        label="Images have alt text",
        description="All meaningful images must have descriptive alt text for screen readers (WCAG 2.1 Success Criterion 1.1.1).",
        status=a2_status,
        detail=a2_detail
    ))

    # A3 — Accessibility statement page
    has_accessibility, _ = _has_page(result, "accessibility", "accessibilite", "toegankelijkheid")
    checks.append(CheckResult(
        id="A3", regulation="EAA", category="Accessibility",
        label="Accessibility statement page exists",
        description="An accessibility statement is required under the European Accessibility Act (EAA, Article 13).",
        status=OK if has_accessibility else WARN,
        detail="Accessibility statement page found." if has_accessibility else "No accessibility statement page detected."
    ))

    # A4 — HTTPS enforced
    is_https = result.url.startswith("https://")
    checks.append(CheckResult(
        id="A4", regulation="EAA / NIS2", category="Accessibility",
        label="HTTPS enforced",
        description="The website must use HTTPS to protect user data in transit (NIS2 Article 21, WCAG 2.1).",
        status=OK if is_https else FAIL,
        detail="Website uses HTTPS." if is_https else "Website does not use HTTPS — data transmitted in clear text."
    ))

    # ── Consumer Rights checks ────────────────────────────────────────────────

    # R1 — Terms and conditions
    has_terms, terms_text = _has_page(result, "terms", "conditions", "cgu", "algemene_voorwaarden", "tos")
    checks.append(CheckResult(
        id="R1", regulation="Consumer Rights", category="Terms & Conditions",
        label="Terms and conditions page exists",
        description="General terms and conditions must be provided and accessible (EU Consumer Rights Directive, Article 6).",
        status=OK if has_terms else WARN,
        detail="Terms and conditions page found." if has_terms else "No terms and conditions page detected."
    ))

    # R2 — Right of withdrawal mentioned
    if has_terms:
        has_withdrawal = _contains(terms_text,
            "right of withdrawal", "right to cancel", "cooling-off",
            "droit de rétractation", "délai de rétractation",
            "herroepingsrecht", "annulering"
        )
        checks.append(CheckResult(
            id="R2", regulation="Consumer Rights", category="Terms & Conditions",
            label="Right of withdrawal / cancellation stated",
            description="The right of withdrawal (14-day cooling-off period) must be disclosed for distance selling (EU Consumer Rights Directive, Article 9).",
            status=OK if has_withdrawal else WARN,
            detail="Right of withdrawal found in T&Cs." if has_withdrawal else "Right of withdrawal not clearly stated in T&Cs."
        ))
    else:
        checks.append(CheckResult(
            id="R2", regulation="Consumer Rights", category="Terms & Conditions",
            label="Right of withdrawal / cancellation stated",
            description="The right of withdrawal (14-day cooling-off period) must be disclosed for distance selling (EU Consumer Rights Directive, Article 9).",
            status=WARN,
            detail="Cannot assess — no T&Cs page found."
        ))

    # R3 — Company legal identity disclosed
    has_legal, legal_text = _has_page(result, "legal", "mentions", "imprint", "impressum", "wettelijke")
    company_in_footer = _contains(homepage_text,
                                    "registered company", "company number", "registration number",
                                    "vat number", "tva:", "btw:", "kvk:", "rcs:", "be 0",
                                    "siret", "kbo", "ondernemingsnummer")
    has_identity = has_legal or company_in_footer
    checks.append(CheckResult(
        id="R3", regulation="Consumer Rights", category="Legal Identity",
        label="Company legal identity disclosed",
        description="The company's legal name, registration number, and VAT number must be disclosed (EU Consumer Rights Directive, Article 6(1)).",
        status=OK if has_identity else WARN,
        detail="Company legal identity found." if has_identity else "Company legal identity (registration/VAT number) not clearly disclosed."
    ))

    # R4 — Contact information present
    has_contact, _ = _has_page(result, "contact")
    contact_in_page = _contains(homepage_text, "@", "contact", "support", "email", "phone", "tel")
    has_contact_info = has_contact or contact_in_page
    checks.append(CheckResult(
        id="R4", regulation="Consumer Rights", category="Legal Identity",
        label="Contact information accessible",
        description="A contact address (email, phone, or postal) must be easily accessible (EU Consumer Rights Directive, Article 6(1)(c)).",
        status=OK if has_contact_info else FAIL,
        detail="Contact information found." if has_contact_info else "No contact information easily accessible."
    ))

    # ── NIS2 checks ──────────────────────────────────────────────────────────

    # N1 — Security contact / responsible disclosure
    has_security, _ = _has_page(result, "security", "securite", "beveiliging", "well-known")
    has_security_email = _contains(all_text, "security@", "abuse@", "responsible disclosure",
                                    "vulnerability", "divulgation responsable", "melden")
    n1_status = OK if (has_security or has_security_email) else WARN
    checks.append(CheckResult(
        id="N1", regulation="NIS2", category="Cybersecurity",
        label="Security contact or responsible disclosure policy",
        description="NIS2 entities should provide a security contact for vulnerability reporting (NIS2 Article 21).",
        status=n1_status,
        detail="Security contact or disclosure policy found." if n1_status == OK else "No security contact or responsible disclosure policy found."
    ))

    # N2 — Security policy / ISMS mention
    has_security_policy = _contains(all_text, "iso 27001", "isms", "information security",
                                     "sécurité de l'information", "informationssicherheit",
                                     "soc 2", "cybersecurity policy", "politique de sécurité")
    checks.append(CheckResult(
        id="N2", regulation="NIS2", category="Cybersecurity",
        label="Security policy or certification mentioned",
        description="NIS2 entities should demonstrate cybersecurity measures such as ISO 27001 or equivalent (NIS2 Article 21(2)).",
        status=OK if has_security_policy else WARN,
        detail="Security policy or certification found." if has_security_policy else "No security policy or certification (e.g. ISO 27001) mentioned."
    ))

    # ── EU AI Act checks ──────────────────────────────────────────────────────

    # AI1 — AI usage disclosed if chatbot / automated system detected
    has_chatbot = _contains(homepage_html, "chatbot", "chat widget", "intercom", "drift",
                              "zendesk", "crisp", "tawk", "livechat", "freshchat",
                              "automated decision", "ai-powered", "powered by ai")
    if has_chatbot:
        has_ai_disclosure = _contains(all_text, "ai", "artificial intelligence", "automated",
                                        "intelligence artificielle", "kunstmatige intelligentie",
                                        "this chat", "chatbot", "virtual assistant")
        checks.append(CheckResult(
            id="AI1", regulation="EU AI Act", category="AI Transparency",
            label="AI system usage disclosed to users",
            description="Users must be informed when they interact with an AI system (EU AI Act Article 50).",
            status=OK if has_ai_disclosure else FAIL,
            detail="AI usage disclosure found." if has_ai_disclosure else "AI system detected but no disclosure to users found."
        ))
    else:
        checks.append(CheckResult(
            id="AI1", regulation="EU AI Act", category="AI Transparency",
            label="AI system usage disclosed to users",
            description="Users must be informed when they interact with an AI system (EU AI Act Article 50).",
            status=OK,
            detail="No AI system (chatbot, automated decision tool) detected on public pages."
        ))

    # ── Score calculation ────────────────────────────────────────────────────

    ok_count   = sum(1 for c in checks if c.status == OK)
    warn_count = sum(1 for c in checks if c.status == WARN)
    fail_count = sum(1 for c in checks if c.status == FAIL)
    total = len(checks)

    # Score: OK=100%, WARN=50%, FAIL=0%
    score = int(((ok_count * 1.0 + warn_count * 0.5) / total) * 100)

    if score >= 75:
        risk_level = "Green"
    elif score >= 45:
        risk_level = "Amber"
    else:
        risk_level = "Red"

    return AuditResult(
        url=result.url,
        checks=checks,
        score=score,
        risk_level=risk_level,
        ok_count=ok_count,
        warn_count=warn_count,
        fail_count=fail_count,
    )
