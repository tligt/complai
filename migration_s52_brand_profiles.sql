-- S52 (D-144): document branding — a company's logo, main colour, font and
-- footer line on the documents RECOSA generates for it (D-09: theme only,
-- never layout; D-10: templates carry no presentation).
--
-- Versioned and append-only: a change is a new row with the next version,
-- and every generated document records the version it was built with
-- (documents.brand_profile_version, there since S25), so "why does this
-- look different from what we filed?" has an answer. The newest version is
-- the one in use. A version with all fields at their defaults and no logo
-- means "branding off".
--
-- Logos are in the private compliance-files bucket under
-- branding/<client_id>/, written with the service role like every upload.

create table if not exists public.brand_profiles (
    id             uuid primary key default gen_random_uuid(),
    client_id      uuid not null references public.clients (id) on delete cascade,
    version        integer not null check (version > 0),
    enabled        boolean not null default true,
    primary_color  text not null default '#003366'
                   check (primary_color ~ '^#[0-9A-Fa-f]{6}$'),
    font           text not null default 'Arial'
                   check (font in ('Arial', 'Calibri', 'Georgia', 'Times New Roman', 'Verdana')),
    footer_text    text check (char_length(footer_text) <= 200),
    logo_path      text,
    user_id        uuid not null default auth.uid() references auth.users (id),
    created_at     timestamptz not null default now(),
    unique (client_id, version)
);

create index if not exists brand_profiles_client_idx
    on public.brand_profiles (client_id, version desc);

alter table public.brand_profiles enable row level security;

-- Everyone with access to the company sees its branding (documents are
-- built with it); those who may edit the company may add a version. No
-- update or delete: versions are history.
drop policy if exists brand_profiles_select on public.brand_profiles;
create policy brand_profiles_select on public.brand_profiles
    for select using (has_client_access(client_id, user_id));

drop policy if exists brand_profiles_insert on public.brand_profiles;
create policy brand_profiles_insert on public.brand_profiles
    for insert with check (can_edit_client(client_id, user_id) and user_id = auth.uid());

comment on table public.brand_profiles is
  'S52: document branding per company, versioned, append-only. documents.brand_profile_version = id.';
