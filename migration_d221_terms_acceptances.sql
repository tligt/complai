-- D-221, 27 Nov: proof that a user accepted the Terms of Service and the
-- Privacy Policy. Until now the app's sign-up checkbox was required but never
-- saved, and the free check's sign-up (which starts a trial too) had none.
--
-- One row per acceptance: who, which versions, when, and where (app sign-up,
-- free-check sign-up, or the prompt at login for an account with none).
-- Append-only, and no foreign key to the user: the row outlives the account
-- (kept after deletion, as the privacy policy says), with the email so it
-- still identifies who accepted.
--
-- Service role only. Idempotent.

create table if not exists public.terms_acceptances (
    id              bigint generated always as identity primary key,
    user_id         uuid not null,
    email           text not null,
    terms_version   text not null,
    privacy_version text not null,
    source          text not null,
    accepted_at     timestamptz not null default now()
);
create index if not exists terms_acceptances_user_idx on public.terms_acceptances (user_id, accepted_at desc);
alter table public.terms_acceptances enable row level security;

notify pgrst, 'reload schema';
