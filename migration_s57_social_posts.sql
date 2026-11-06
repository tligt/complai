-- S57 (D-147): LinkedIn drafts sent to Buffer from the back office.
--
-- One row per draft sent to one Buffer channel (or saved as a Buffer Idea):
-- what went, how (queue, a date and time, or an Idea to finish in Buffer),
-- and Buffer's answer. The draft itself stays on its regulatory_updates /
-- marketing_updates row (linkedin_draft); this is the history of sending it.
--
-- Back office only: written and read with the service role. RLS on, no
-- policy, no grants to anon or authenticated.

create table if not exists public.social_posts (
    id            uuid primary key default gen_random_uuid(),
    source_table  text not null check (source_table in ('regulatory_updates', 'marketing_updates')),
    source_id     uuid not null,
    mode          text not null check (mode in ('queue', 'scheduled', 'idea')),
    channel_id    text,                       -- null for an Idea (it belongs to the organisation)
    channel_name  text,
    service       text,                       -- linkedin, twitter, ...
    text          text not null,
    due_at        timestamptz,                -- when Buffer will post it, as Buffer answered
    buffer_id     text,                       -- the post or Idea id at Buffer
    status        text not null check (status in ('sent', 'error')),
    error         text,
    sent_by       uuid references auth.users (id) on delete set null,
    created_at    timestamptz not null default now()
);

create index if not exists social_posts_source_idx
    on public.social_posts (source_table, source_id, created_at desc);

alter table public.social_posts enable row level security;
revoke all on public.social_posts from anon, authenticated;

comment on table public.social_posts is
  'S57: drafts sent to Buffer (queue, scheduled, or Idea). Back office, service role only.';
