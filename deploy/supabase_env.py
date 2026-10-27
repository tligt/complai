"""
deploy/supabase_env.py — writes the self-hosted Supabase stack's .env (S50).

    python3 supabase_env.py /opt/recosa/supabase/docker   # once, on the server

Starts from that directory's .env.example — the file shipped with the pinned
Supabase version, so the list of settings always matches the stack — and:

  * generates every secret: any key whose name contains PASSWORD, SECRET,
    TOKEN or ENC_KEY, plus SECRET_KEY_BASE and the tenant ids;
  * signs ANON_KEY and SERVICE_ROLE_KEY with the new JWT_SECRET (HS256, ten
    years), the way Supabase's own key generator does;
  * sets the public URLs and the SMTP settings from deploy/.env.

Refuses to overwrite an existing .env: regenerating JWT_SECRET would log
everyone out and invalidate both API keys the apps hold. Prints the two keys
to copy into deploy/.env (SUPABASE_KEY, SUPABASE_SERVICE_KEY) and lists any
setting it left at its example value, so nothing is silently a placeholder.

Standard library only: it runs on the bare host before anything is installed.
"""

import base64
import hashlib
import hmac
import json
import secrets
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def jwt_hs256(payload: dict, secret: str) -> str:
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(sig)}"


def read_env(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main(stack_dir: str) -> None:
    stack = Path(stack_dir)
    example, target = stack / ".env.example", stack / ".env"
    if target.exists():
        sys.exit(f"{target} exists already — not overwriting (see the docstring).")
    ours = read_env(HERE / ".env")

    jwt_secret = secrets.token_hex(32)
    now = int(time.time())
    ten_years = now + 10 * 365 * 24 * 3600
    anon = jwt_hs256({"role": "anon", "iss": "supabase", "iat": now, "exp": ten_years}, jwt_secret)
    service = jwt_hs256({"role": "service_role", "iss": "supabase", "iat": now, "exp": ten_years}, jwt_secret)

    api = f"https://{ours['API_HOST']}"
    app = f"https://{ours['APP_HOST']}"
    fixed = {
        "JWT_SECRET": jwt_secret,
        "ANON_KEY": anon,
        "SERVICE_ROLE_KEY": service,
        # Hex only: the password ends up inside connection URLs.
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "DASHBOARD_USERNAME": "recosa",
        "SECRET_KEY_BASE": secrets.token_hex(32),
        # Exactly 32 characters, as the pooler requires.
        "VAULT_ENC_KEY": secrets.token_hex(16),
        "POOLER_TENANT_ID": "recosa",
        "SITE_URL": app,
        "ADDITIONAL_REDIRECT_URLS": app,
        "API_EXTERNAL_URL": api,
        "SUPABASE_PUBLIC_URL": api,
        "ENABLE_EMAIL_SIGNUP": "true",
        "ENABLE_ANONYMOUS_USERS": "false",
        "ENABLE_PHONE_SIGNUP": "false",
        "DISABLE_SIGNUP": "false",
    }
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_ADMIN_EMAIL",
              "SMTP_SENDER_NAME", "ENABLE_EMAIL_AUTOCONFIRM"):
        if ours.get(k):
            fixed[k] = ours[k]

    lines, untouched = [], []
    for line in example.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            lines.append(line)
            continue
        key = s.split("=", 1)[0].strip()
        if key in fixed:
            lines.append(f"{key}={fixed[key]}")
        elif any(w in key for w in ("ENC_KEY", "CRYPTO_KEY")):
            # Encryption keys: exactly 32 characters.
            lines.append(f"{key}={secrets.token_hex(16)}")
        elif any(w in key for w in ("PASSWORD", "SECRET", "TOKEN")):
            lines.append(f"{key}={secrets.token_hex(24)}")
        else:
            lines.append(line)
            untouched.append(key)

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(0o600)

    print(f"Wrote {target}\n")
    print("Copy into deploy/.env:")
    print(f"  SUPABASE_KEY={anon}")
    print(f"  SUPABASE_SERVICE_KEY={service}\n")
    print("Left at the example value — check each is what you want:")
    for k in untouched:
        print(f"  {k}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
