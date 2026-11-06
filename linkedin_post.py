"""
linkedin_post.py — S57 follow-up (D-149): turning a LinkedIn draft into the
post Buffer sends. No Streamlit, no network except the image upload.

- plain_text: LinkedIn shows no Markdown, so **bold** kept its asterisks
  (6 Nov). Emphasis marks, list dashes and [text](url) links are converted;
  hashtags and every other "#" are left alone (asked for, 6 Nov).
- with_source: the source line, two ways, chosen per post — "Source: <link>"
  in the post, or "Source: <name>" in the post and the link in the first
  comment (a link in the post is widely believed to cut reach).
- mentions: every "RECOSA" in the text becomes a real mention of the RECOSA
  LinkedIn page — Buffer's LinkedIn `annotations`, format confirmed by a test
  draft on 6 Nov (id = the page number, entity = urn:li:organization:<id>).
- headline_card: a RECOSA image for posts whose link is in the comment
  (no link preview then), hosted in the public social-images bucket because
  Buffer fetches images by URL and has no upload.
"""

from __future__ import annotations

import hashlib
import io
import os
import re

RECOSA_PAGE = {
    "id": "129854326",
    "entity": "urn:li:organization:129854326",
    "link": "https://www.linkedin.com/company/recosa-ai",
    "localizedName": "RECOSA",
    "vanityName": "recosa-ai",
}
IMAGE_BUCKET = "social-images"
SOURCE_MODES = {
    "comment": "Source name in the post, link in the first comment",
    "link": "Source: link in the post",
    "none": "No source line",
}


# ── Text ──────────────────────────────────────────────────────────────────

def plain_text(text: str) -> str:
    """The draft as LinkedIn will show it, Markdown marks removed. "#" is
    never touched: hashtags pass on LinkedIn as they are."""
    out = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        s = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", line)                          # list items
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 \2", s)        # links
        s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)                             # bold
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)    # italics
        s = re.sub(r"`([^`]+)`", r"\1", s)                                    # code
        s = re.sub(r"^\s*([-*_])\1{2,}\s*$", "", s)                           # rules
        s = re.sub(r"@RECOSA(?!\w)", "RECOSA", s)       # the mention replaces the "@"
        out.append(s.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def with_source(text: str, mode: str, source_name: str | None,
                url: str | None) -> tuple[str, str | None]:
    """(post text, first comment) for the chosen source mode."""
    name = (source_name or "").strip()
    url = (url or "").strip()
    if mode == "link" and url:
        return f"{text}\n\nSource: {url}", None
    if mode == "comment" and (name or url):
        line = f"\n\nSource: {name}" if name else ""
        return f"{text}{line}", (f"Source: {url}" if url else None)
    return text, None


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def mentions(text: str, counting: str = "utf16") -> list[dict]:
    """Annotations for every standalone "RECOSA" in the text. Positions in
    UTF-16 code units (how JavaScript, and so Buffer, counts: an emoji is
    two) unless counting="codepoints"."""
    out = []
    for m in re.finditer(r"(?<![\w@])RECOSA(?!\w)", text):
        if counting == "utf16":
            start, length = _utf16_len(text[:m.start()]), _utf16_len(m.group())
        else:
            start, length = m.start(), len(m.group())
        out.append({**RECOSA_PAGE, "start": start, "length": length})
    return out


# ── Image ─────────────────────────────────────────────────────────────────

_FONT_PATHS = {
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
           "C:/Windows/Fonts/arialbd.ttf"],
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf"],
}


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for p in _FONT_PATHS[bold]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def headline_card(title: str, kicker: str | None = None) -> bytes:
    """A 1200×627 PNG (LinkedIn's link-image size): RECOSA navy, the R mark,
    the headline, and recosa.eu."""
    from PIL import Image, ImageDraw
    W, H, M = 1200, 627, 72
    img = Image.new("RGB", (W, H), (0, 0x33, 0x66))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((M, M, M + 64, M + 64), radius=14, fill="white")
    d.text((M + 32, M + 33), "R", font=_font(40, True), fill=(0, 0x33, 0x66), anchor="mm")
    d.text((M + 88, M + 32), "RECOSA", font=_font(34, True), fill="white", anchor="lm")
    y = M + 130
    if kicker:
        d.text((M, y), kicker.upper()[:60], font=_font(24, True), fill=(0x9F, 0xE7, 0xEE))
        y += 50
    hf = _font(54, True)
    for line in _wrap(d, title or "", hf, W - 2 * M, 4):
        d.text((M, y), line, font=hf, fill="white")
        y += 68
    d.text((M, H - M - 10), "recosa.eu", font=_font(26), fill=(0xC9, 0xD6, 0xE3), anchor="ls")
    d.rectangle((0, H - 10, W, H), fill=(0x14, 0xC7, 0xD5))
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def upload_card(png: bytes) -> str | None:
    """Public URL of the card in the social-images bucket (Buffer fetches it
    when the post is published, so it must stay)."""
    from database import upload_file
    name = f"cards/{hashlib.sha256(png).hexdigest()[:16]}.png"
    if not upload_file(IMAGE_BUCKET, name, png, "image/png"):
        return None
    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    return f"{base}/storage/v1/object/public/{IMAGE_BUCKET}/{name}" if base else None
