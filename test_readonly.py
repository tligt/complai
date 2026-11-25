"""test_readonly.py — D-215: the read-only guard. Fake clients, no database.

    python test_readonly.py
"""

import readonly as RO

failures = []


def check(name, ok):
    if not ok:
        failures.append(name)
        print(f"FAIL  {name}")


calls = []


class FakeQuery:
    def __init__(self, table):
        self.table = table

    def __getattr__(self, name):
        def m(*a, **k):
            calls.append((self.table, name))
            return self
        return m

    def execute(self):
        calls.append((self.table, "execute"))
        return type("R", (), {"data": [{"id": 1}], "count": 1})()


class FakeBucket:
    def __getattr__(self, name):
        return lambda *a, **k: calls.append(("storage", name)) or b"bytes"


class FakeStorage:
    def from_(self, b):
        return FakeBucket()


class FakeClient:
    storage = FakeStorage()
    auth = "auth-object"

    def table(self, name):
        return FakeQuery(name)

    def rpc(self, *a, **k):
        return "rpc"


# Not read-only (no Streamlit session): the client itself.
c = FakeClient()
check("inactive: unwrapped", RO.wrap(c) is c)
check("inactive: check passes", RO.check("x") is None)

# Force read-only.
RO.active = lambda: True
w = RO.wrap(c)
check("active: wrapped", w is not c)

calls.clear()
r = w.table("systems").select("*").eq("client_id", "x").execute()
check("reads go through", r.data == [{"id": 1}] and ("systems", "select") in calls)

for op in ("insert", "update", "upsert", "delete"):
    calls.clear()
    try:
        getattr(w.table("systems"), op)({"a": 1}).eq("id", 1).execute()
        check(f"{op} refused", False)
    except RO.ReadOnlyError:
        check(f"{op} refused, not sent", not any(t == "systems" for t, _ in calls))

calls.clear()
r = w.table("profiles").update({"ui_language": "fr"}).eq("id", 1).execute()
check("profiles still writable", ("profiles", "update") in calls and r.data == [{"id": 1}])
calls.clear()
w.table("support_tickets").insert({"x": 1}).execute()
check("support still writable", ("support_tickets", "insert") in calls)
calls.clear()
try:
    w.from_("documents").insert({"x": 1}).execute()
    check("from_ guarded too", False)
except RO.ReadOnlyError:
    check("from_ guarded too", not any(t == "documents" for t, _ in calls))

check("download allowed", w.storage.from_("docs").download("p") == b"bytes")
check("signed url allowed", w.storage.from_("docs").create_signed_url("p", 60) == b"bytes")
try:
    w.storage.from_("docs").upload("p", b"x")
    check("upload refused", False)
except RO.ReadOnlyError:
    check("upload refused", True)
try:
    RO.check("generating documents")
    check("AI refused", False)
except RO.ReadOnlyError as e:
    check("AI refused", "generating documents" in e.detail and "read-only" in str(e))
check("other attributes pass", w.auth == "auth-object" and w.rpc("f") == "rpc")

print("All read-only tests passed." if not failures else f"{len(failures)} failure(s).")
raise SystemExit(1 if failures else 0)
