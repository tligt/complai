"""
fresh_modules.py — reload our own modules that changed on disk since they
were imported.

Streamlit re-runs a page's script on every interaction but keeps imported
modules in memory. After a deploy, Streamlit Cloud can therefore run new
pages against an old database.py: a new name then fails with ImportError
(D-116, 26 Oct; again on 9 Nov with S59, where a reboot of the client app
did not clear it). Called first thing by app.py and admin_app.py: a listed
module whose file is newer than the copy in memory is reloaded, so the
pages' `from database import …` that follow get the current code.

"Newer than the copy in memory": the first time a module is seen here, its
compiled cache (__pycache__/*.pyc, written when it was imported) older
than its .py file means the .py was replaced after the import. After that,
the file's modification time is remembered and compared on every run.
"""

import importlib
import os
import sys

# Shared modules that pages import names from; a module is reloaded before
# the ones that import from it.
MODULES = ("database", "cached_reads", "auth", "tier_gates", "doc_theme", "active_client",
           "table_view", "dedup", "monitoring_queue")


def _mtime(path: str | None) -> float | None:
    try:
        return os.path.getmtime(path) if path else None
    except OSError:
        return None


def refresh() -> list[str]:
    reloaded = []
    for name in MODULES:
        mod = sys.modules.get(name)
        src = _mtime(getattr(mod, "__file__", None))
        if not mod or src is None:
            continue
        seen = getattr(mod, "_FRESH_MTIME", None)
        if seen is None:
            pyc = _mtime(getattr(mod, "__cached__", None))
            stale = pyc is not None and pyc < src
        else:
            stale = src != seen
        if stale:
            try:
                mod = importlib.reload(mod)
                reloaded.append(name)
            except Exception as e:     # a failed reload must not take the app down
                print(f"Could not reload {name}: {e}")
        mod._FRESH_MTIME = src
    if reloaded:
        print(f"Reloaded changed modules: {', '.join(reloaded)}")
    return reloaded
