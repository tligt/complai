"""
doc_theme.py — S52 (D-144): the look of a generated document.

A document's look comes from its company's brand profile (brand_profiles,
versioned, set on the Company profile page) or, without one, from RECOSA's
neutral house style. Theme only (D-09): logo, main colour, font and a footer
line — never layout. Templates stay presentation-free (D-10): build_docx and
build_xlsx read a DocTheme, the template text never does.

Branding is a Professional, Advisory and Enterprise feature (asked for,
5 Nov). A Starter company's documents use the house style even if a profile
was saved under a higher plan earlier.

Colours are kept readable whatever the company picks: text in the brand
colour is darkened until it reads on white (4.5:1), and a table header
filled with it gets white or near-black text, whichever reads better.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

FONTS = ("Arial", "Calibri", "Georgia", "Times New Roman", "Verdana")
HOUSE_COLOR = "#003366"                 # RECOSA navy, as on recosa.eu
BRANDING_TIERS = ("professional", "advisory", "enterprise")
LOGO_BUCKET = "compliance-files"
LOGO_MAX_BYTES = 1_000_000


# ── Colour helpers ────────────────────────────────────────────────────────

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


WHITE = (255, 255, 255)
INK = (0x1A, 0x1A, 0x1A)


def readable_on_white(rgb, target: float = 4.5) -> tuple[int, int, int]:
    """The colour itself if text in it reads on white, else the same hue
    darkened step by step until it does."""
    r, g, b = rgb
    for _ in range(40):
        if contrast((r, g, b), WHITE) >= target:
            break
        r, g, b = int(r * 0.9), int(g * 0.9), int(b * 0.9)
    return r, g, b


def text_on(fill) -> tuple[int, int, int]:
    """White or near-black, whichever reads better on `fill`."""
    return WHITE if contrast(WHITE, fill) >= contrast(INK, fill) else INK


# ── The theme ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DocTheme:
    color: str = HOUSE_COLOR                 # as chosen, "#RRGGBB"
    font: str = "Arial"
    footer_text: str | None = None
    logo: bytes | None = field(default=None, repr=False)
    branded: bool = False                    # a company's own branding
    version_id: str | None = None            # brand_profiles.id, stamped on documents

    @property
    def fill(self) -> tuple[int, int, int]:
        """The colour as chosen: rules, table header fill, spreadsheet header."""
        return hex_to_rgb(self.color)

    @property
    def text(self) -> tuple[int, int, int]:
        """The colour for titles and headings: readable on white."""
        return readable_on_white(self.fill)

    @property
    def header_text(self) -> tuple[int, int, int]:
        return text_on(self.fill)


HOUSE = DocTheme()


# ── Loading ───────────────────────────────────────────────────────────────

def owner_tier(client_id: str) -> str | None:
    """The plan of the account that owns the company. Read with the service
    role: a team member may not read the owner's profile."""
    from database import get_supabase_admin
    try:
        c = (get_supabase_admin().table("clients").select("user_id")
             .eq("id", client_id).limit(1).execute().data)
        if not c:
            return None
        p = (get_supabase_admin().table("profiles").select("subscription_tier")
             .eq("id", c[0]["user_id"]).limit(1).execute().data)
        return (p[0].get("subscription_tier") if p else None) or "professional"
    except Exception as e:
        print(f"Could not read the plan for branding: {e}")
        return None


def branding_allowed(client_id: str | None) -> bool:
    return bool(client_id) and owner_tier(client_id) in BRANDING_TIERS


def latest_profile(client_id: str) -> dict | None:
    """The newest brand profile row of a company, as the user may see it."""
    from database import get_supabase
    try:
        rows = (get_supabase().table("brand_profiles").select("*")
                .eq("client_id", client_id).order("version", desc=True)
                .limit(1).execute().data)
        return rows[0] if rows else None
    except Exception as e:
        print(f"Could not read the brand profile: {e}")
        return None


def load_logo(path: str | None) -> bytes | None:
    if not path:
        return None
    from database import get_supabase_admin
    try:
        return get_supabase_admin().storage.from_(LOGO_BUCKET).download(path)
    except Exception as e:
        print(f"Could not load the logo {path}: {e}")
        return None


def theme_from_row(row: dict | None, logo: bytes | None = None) -> DocTheme:
    if not row or not row.get("enabled"):
        return HOUSE
    return DocTheme(
        color=row.get("primary_color") or HOUSE_COLOR,
        font=row.get("font") if row.get("font") in FONTS else "Arial",
        footer_text=(row.get("footer_text") or "").strip() or None,
        logo=logo,
        branded=True,
        version_id=row.get("id"),
    )


def theme_for_client(client_id: str | None) -> DocTheme:
    """The theme a document for this company is built with now."""
    if not client_id or not branding_allowed(client_id):
        return HOUSE
    row = latest_profile(client_id)
    if not row or not row.get("enabled"):
        return HOUSE
    return theme_from_row(row, load_logo(row.get("logo_path")))


# ── Saving ────────────────────────────────────────────────────────────────

def prepare_logo(raw: bytes) -> bytes:
    """A logo as stored: PNG, at most 1200 px wide, transparency kept.
    Raises ValueError with a plain message for anything that is not a usable
    image."""
    from PIL import Image, UnidentifiedImageError
    if len(raw) > LOGO_MAX_BYTES * 5:
        raise ValueError("That file is too large. Use a logo under 5 MB.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise ValueError("That file isn't an image RECOSA can read. Use a PNG or JPG.")
    if img.width < 40 or img.height < 20:
        raise ValueError("That logo is too small. Use one at least 200 pixels wide.")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    if img.width > 1200:
        img = img.resize((1200, round(img.height * 1200 / img.width)))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def save_profile(client_id: str, user_id: str, *, enabled: bool, color: str,
                 font: str, footer_text: str | None, logo_png: bytes | None,
                 keep_logo_path: str | None) -> tuple[bool, str | None]:
    """A new version of the company's branding. logo_png: a new logo (from
    prepare_logo); otherwise keep_logo_path carries the current one over, or
    None removes it. Returns (ok, error message)."""
    import hashlib
    from database import get_supabase, upload_file
    color = (color or HOUSE_COLOR).upper()
    if font not in FONTS:
        return False, "Choose one of the fonts in the list."
    footer_text = (footer_text or "").strip()[:200] or None
    current = latest_profile(client_id)
    version = (current["version"] + 1) if current else 1
    logo_path = keep_logo_path
    if logo_png:
        digest = hashlib.sha256(logo_png).hexdigest()[:12]
        logo_path = upload_file(LOGO_BUCKET, f"branding/{client_id}/{version}-{digest}.png",
                                logo_png, "image/png")
        if not logo_path:
            return False, "The logo couldn't be uploaded. Try again."
    try:
        get_supabase().table("brand_profiles").insert({
            "client_id": client_id, "version": version, "enabled": enabled,
            "primary_color": color, "font": font, "footer_text": footer_text,
            "logo_path": logo_path, "user_id": user_id,
        }).execute()
    except Exception as e:
        return False, f"Couldn't save the branding: {e}"
    return True, None
