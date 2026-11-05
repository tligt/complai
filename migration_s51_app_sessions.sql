-- S51 (D-143): a login that survives a refresh or a reopened page.
--
-- The browser keeps only an opaque, random cookie. This table keeps what it
-- stands for: the Supabase tokens of that login, encrypted with the app's
-- SESSION_SECRET (Fernet), so a database dump alone cannot be replayed.
-- `id` is the SHA-256 of the cookie value, never the value itself.
--
-- Only the service role reads or writes it: RLS on with no policy, and no
-- grants to anon or authenticated. Deleting the account deletes its rows.

create table if not exists public.app_sessions (
    id            text primary key,                 -- sha256(cookie value), hex
    app           text not null check (app in ('client', 'admin')),
    user_id       uuid not null references auth.users (id) on delete cascade,
    tokens        text not null,                    -- Fernet({access, refresh})
    created_at    timestamptz not null default now(),
    last_seen_at  timestamptz not null default now(),
    expires_at    timestamptz not null,             -- absolute end of the login
    user_agent    text
);

create index if not exists app_sessions_user_idx on public.app_sessions (user_id);
create index if not exists app_sessions_expires_idx on public.app_sessions (expires_at);

alter table public.app_sessions enable row level security;
revoke all on public.app_sessions from anon, authenticated;

comment on table public.app_sessions is
  'S51: server side of the login cookie. Service role only. Tokens are Fernet-encrypted with SESSION_SECRET.';
