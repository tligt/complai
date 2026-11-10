"""
load_template_docs.py — S62. Load authored templates through the API.

The seed scripts emit SQL for the SQL editor. This does the same upserts with
the service-role client, for when no SQL connection is at hand:

    python load_template_docs.py template_seed_ai aup hop notice

Runs check_bodies first and refuses on any error, exactly as run() does.
"""

import importlib
import sys

from dotenv import load_dotenv

load_dotenv()

from database import get_supabase_admin
from template_seed_lib import check_bodies


def load(doc) -> None:
    errors = check_bodies(doc)
    if errors:
        raise SystemExit(f"{doc.doc_type}: " + "; ".join(errors))
    sb = get_supabase_admin()
    t = sb.table("document_templates").upsert(
        {"doc_type": doc.doc_type, "title": doc.title, "tier": doc.tier,
         "active": True, "sort_order": doc.sort_order},
        on_conflict="doc_type").execute().data[0]
    for lang, body in doc.bodies.items():
        sb.table("document_template_versions").upsert(
            {"template_id": t["id"], "language": lang, "version_no": doc.version_no,
             "source_revision": doc.source_revision, "body_md": body,
             "materiality": doc.materiality, "status": "in_force",
             "change_note": doc.note, "effective_from": doc.effective_from},
            on_conflict="template_id,language,version_no").execute()
    print(f"{doc.doc_type}: {', '.join(doc.bodies)} loaded")


if __name__ == "__main__":
    mod = importlib.import_module(sys.argv[1])
    for key in sys.argv[2:]:
        load(mod.DOCS[key][0])
