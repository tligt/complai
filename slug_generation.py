import re
import unicodedata


def slugify(text: str, max_length: int = 80) -> str:
    """
    Converts a title into a URL-safe slug.

    Examples:
        "The EU AI Act's Deadline Just Moved — Here's What Changed"
            -> "the-eu-ai-acts-deadline-just-moved-heres-what-changed"
        "Victimes de violations de données : restez vigilants"
            -> "victimes-de-violations-de-donnees-restez-vigilants"

    Strips accents (important for French/Dutch titles — "données" -> "donnees",
    not left as-is or dropped), lowercases, replaces anything that isn't
    alphanumeric with a hyphen, collapses repeated hyphens, and trims to
    max_length without cutting a word in half.
    """
    if not text:
        return ""

    # Normalise accented characters to their closest ASCII equivalent
    # (é -> e, ç -> c, etc.) rather than stripping them to nothing.
    normalised = unicodedata.normalize("NFKD", text)
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")

    lowered = ascii_text.lower()

    # Replace anything that isn't a-z, 0-9 with a hyphen
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)

    # Collapse multiple hyphens, trim leading/trailing hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")

    # Truncate without cutting a word in half
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]

    return slug


def generate_unique_slug(text: str, check_exists_fn, max_length: int = 80) -> str:
    """
    Generates a slug and ensures uniqueness by appending -2, -3, etc.
    if the base slug is already taken.

    check_exists_fn: a function taking a slug string and returning True
    if that slug already exists in the database (e.g. a Supabase lookup
    against marketing_updates.slug). Wire this to your existing db
    connection — e.g.:

        def slug_exists(slug):
            result = supabase.table("marketing_updates") \\
                .select("id").eq("slug", slug).execute()
            return len(result.data) > 0

    Usage:
        slug = generate_unique_slug(title, slug_exists)
    """
    base_slug = slugify(text)
    if not check_exists_fn(base_slug):
        return base_slug

    counter = 2
    while True:
        candidate = f"{base_slug}-{counter}"
        if not check_exists_fn(candidate):
            return candidate
        counter += 1


# ── Streamlit admin BO form pattern ───────────────────────────────
#
# Auto-generates the slug from the title as a live default, but lets
# the person freely edit it before saving — same UX pattern as most
# CMS admin panels (WordPress, Notion, etc.): suggested, not forced.
#
# Drop this into the marketing article approval/edit form:
#
# import streamlit as st
#
# title = st.text_input("Title", value=item.get("title", ""))
#
# # Only auto-populate the suggested slug once per item being edited —
# # after that, respect whatever the person typed, even if they keep
# # editing the title. Keyed by item id so switching between items in
# # the queue resets it correctly.
# slug_state_key = f"slug_suggested_{item['id']}"
# if slug_state_key not in st.session_state:
#     st.session_state[slug_state_key] = slugify(title)
#
# slug = st.text_input(
#     "URL slug",
#     value=st.session_state[slug_state_key],
#     help="Auto-generated from the title — edit freely before saving. "
#          "Used in the article's URL: recosa.eu/pulse/{slug}",
#     key=f"slug_input_{item['id']}",
# )
#
# # Regenerate button, for when the title changes after the initial suggestion
# if st.button("↻ Regenerate from title", key=f"regen_slug_{item['id']}"):
#     st.session_state[slug_state_key] = slugify(title)
#     st.rerun()
#
# # Before saving:
# if st.button("Save", key=f"save_{item['id']}"):
#     final_slug = slug.strip()
#     if not final_slug:
#         st.error("Slug cannot be empty.")
#     elif slug_exists(final_slug) and final_slug != item.get("slug"):
#         st.error(f"Slug '{final_slug}' is already in use — please choose another.")
#     else:
#         # proceed with save, final_slug goes into the slug column
#         pass
