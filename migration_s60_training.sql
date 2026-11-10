-- S60 (D-159): skills matrix and training register.
--
--   training_requirement — reference data (S24 decision): what training the
--                          law asks of whom, global rows in reference_values.
--   employees            — the client's people, with the four facts that
--                          decide what they need (personal data, AI use,
--                          management body, AI oversight).
--   training_sessions    — one training given on one date, covering one or
--                          more requirements.
--   training_attendance  — who attended which session.
--   clients              — training_nudged_at: the content-free reminder
--                          (monitor_training.py) is sent at most monthly.
--
-- RECOSA does not deliver training. These tables are evidence of a plan and
-- of attendance, not of competence.
--
-- Idempotent: safe to run again.

-- ── Employees ─────────────────────────────────────────────────────────────
create table if not exists public.employees (
    id                     uuid primary key default gen_random_uuid(),
    client_id              uuid not null references public.clients (id) on delete cascade,
    user_id                uuid references auth.users (id) on delete set null,
    name                   text not null check (char_length(name) between 1 and 200),
    email                  text check (email is null or char_length(email) <= 254),
    job_title              text check (job_title is null or char_length(job_title) <= 200),
    department             text check (department is null or char_length(department) <= 200),
    handles_personal_data  boolean not null default true,
    uses_ai                boolean not null default false,
    management_body        boolean not null default false,
    ai_overseer            boolean not null default false,
    started_on             date,
    left_on                date,
    notes                  text check (notes is null or char_length(notes) <= 2000),
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    check (left_on is null or started_on is null or left_on >= started_on)
);
create index if not exists employees_client_idx on public.employees (client_id);
alter table public.employees enable row level security;

drop policy if exists employees_select on public.employees;
create policy employees_select on public.employees for select
    using (has_client_access(client_id, null) or is_admin_user());
drop policy if exists employees_insert on public.employees;
create policy employees_insert on public.employees for insert
    with check (can_edit_client(client_id, null) and user_id = (select auth.uid()));
drop policy if exists employees_update on public.employees;
create policy employees_update on public.employees for update
    using (can_edit_client(client_id, null))
    with check (can_edit_client(client_id, null));
-- Delete is allowed (a person entered by mistake, or erasure once retention
-- ends): it removes their attendance too. Someone who left gets left_on, which
-- keeps the record.
drop policy if exists employees_delete on public.employees;
create policy employees_delete on public.employees for delete
    using (can_edit_client(client_id, null));

-- ── Sessions ──────────────────────────────────────────────────────────────
create table if not exists public.training_sessions (
    id                 uuid primary key default gen_random_uuid(),
    client_id          uuid not null references public.clients (id) on delete cascade,
    user_id            uuid references auth.users (id) on delete set null,
    title              text not null check (char_length(title) between 1 and 300),
    requirement_codes  text[] not null default '{}',
    held_on            date not null,
    duration_minutes   integer check (duration_minutes is null or duration_minutes > 0),
    format             text not null default 'in_person'
                       check (format in ('in_person', 'online', 'e_learning', 'reading')),
    provider           text check (provider is null or char_length(provider) <= 200),
    trainer            text check (trainer is null or char_length(trainer) <= 200),
    content            text check (content is null or char_length(content) <= 4000),
    valid_until        date,     -- overrides the requirement's refresh interval
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
create index if not exists training_sessions_client_idx on public.training_sessions (client_id, held_on desc);
alter table public.training_sessions enable row level security;

drop policy if exists training_sessions_select on public.training_sessions;
create policy training_sessions_select on public.training_sessions for select
    using (has_client_access(client_id, null) or is_admin_user());
drop policy if exists training_sessions_insert on public.training_sessions;
create policy training_sessions_insert on public.training_sessions for insert
    with check (can_edit_client(client_id, null) and user_id = (select auth.uid()));
drop policy if exists training_sessions_update on public.training_sessions;
create policy training_sessions_update on public.training_sessions for update
    using (can_edit_client(client_id, null))
    with check (can_edit_client(client_id, null));
drop policy if exists training_sessions_delete on public.training_sessions;
create policy training_sessions_delete on public.training_sessions for delete
    using (can_edit_client(client_id, null));

-- ── Attendance ────────────────────────────────────────────────────────────
create table if not exists public.training_attendance (
    id           uuid primary key default gen_random_uuid(),
    client_id    uuid not null references public.clients (id) on delete cascade,
    session_id   uuid not null references public.training_sessions (id) on delete cascade,
    employee_id  uuid not null references public.employees (id) on delete cascade,
    user_id      uuid references auth.users (id) on delete set null,
    created_at   timestamptz not null default now(),
    unique (session_id, employee_id)
);
create index if not exists training_attendance_client_idx on public.training_attendance (client_id);
create index if not exists training_attendance_employee_idx on public.training_attendance (employee_id);
alter table public.training_attendance enable row level security;

drop policy if exists training_attendance_select on public.training_attendance;
create policy training_attendance_select on public.training_attendance for select
    using (has_client_access(client_id, null) or is_admin_user());
drop policy if exists training_attendance_insert on public.training_attendance;
create policy training_attendance_insert on public.training_attendance for insert
    with check (can_edit_client(client_id, null) and user_id = (select auth.uid()));
drop policy if exists training_attendance_delete on public.training_attendance;
create policy training_attendance_delete on public.training_attendance for delete
    using (can_edit_client(client_id, null));

-- ── The monthly reminder ──────────────────────────────────────────────────
alter table public.clients add column if not exists training_nudged_at timestamptz;

-- ── Requirements (reference data) ─────────────────────────────────────────
alter table public.reference_values drop constraint if exists reference_values_type_valid;
alter table public.reference_values add constraint reference_values_type_valid
    check (value_type in ('system_category', 'data_category', 'special_category',
        'criminal_data', 'art9_condition', 'data_subject_category', 'legal_basis',
        'transfer_mechanism', 'dpa_status', 'controller_role', 'system_role',
        'criticality', 'ai_role', 'security_measure', 'jurisdiction',
        'retention_basis', 'retention_unit', 'data_source', 'dpia_risk',
        'nis2_risk', 'training_requirement'));

-- metadata: regulation, audience (all | personal_data | management |
-- ai_users | ai_overseers), refresh_months (RECOSA's default: the law says
-- "regular" or "appropriate", never a number), obligation_id (the register
-- obligation it evidences, or null), anchor (the articles).
insert into public.reference_values
    (value_type, code, label_en, label_fr, note_en, note_fr, metadata, sort_order, active)
values
    ('training_requirement', 'gdpr_awareness',
     'Data protection awareness', 'Sensibilisation à la protection des données',
     'Everyone who handles personal data. GDPR Art. 5(2) (accountability), Art. 32(4) (staff act only on instructions), Art. 39(1)(b) (the DPO''s awareness-raising and training).',
     'Toute personne qui traite des données personnelles. RGPD art. 5(2) (responsabilité), art. 32(4) (le personnel n''agit que sur instruction), art. 39(1)(b) (sensibilisation et formation par le DPO).',
     '{"regulation": "GDPR", "audience": "personal_data", "refresh_months": 12, "obligation_id": "gdpr_13", "anchor": "GDPR Art. 5(2), 32(4), 39(1)(b)"}',
     10, true),
    ('training_requirement', 'nis2_awareness',
     'Cybersecurity awareness', 'Sensibilisation à la cybersécurité',
     'All staff. NIS2 Art. 21(2)(g): basic cyber hygiene practices and cybersecurity training.',
     'Tout le personnel. NIS2 art. 21(2)(g) : pratiques de base en matière de cyberhygiène et formation à la cybersécurité.',
     '{"regulation": "NIS2", "audience": "all", "refresh_months": 12, "obligation_id": "nis2_09", "anchor": "NIS2 Art. 21(2)(g)"}',
     20, true),
    ('training_requirement', 'nis2_management',
     'Cybersecurity training for the management body', 'Formation cybersécurité de l''organe de direction',
     'Members of the management body. NIS2 Art. 20(2): they must follow training to identify risks and assess cybersecurity risk-management practices.',
     'Membres de l''organe de direction. NIS2 art. 20(2) : ils sont tenus de suivre une formation pour identifier les risques et évaluer les pratiques de gestion des risques.',
     '{"regulation": "NIS2", "audience": "management", "refresh_months": 12, "obligation_id": null, "anchor": "NIS2 Art. 20(2)"}',
     30, true),
    ('training_requirement', 'ai_literacy',
     'AI literacy', 'Maîtrise de l''IA',
     'Staff who use or operate AI systems. AI Act Art. 4: measures to support a sufficient level of AI literacy; since the Digital Omnibus an obligation of effort.',
     'Personnel qui utilise ou exploite des systèmes d''IA. AI Act art. 4 : mesures pour un niveau suffisant de maîtrise de l''IA ; depuis l''Omnibus numérique, une obligation de moyens.',
     '{"regulation": "EU_AI_ACT", "audience": "ai_users", "refresh_months": 12, "obligation_id": "ai_01", "anchor": "AI Act Art. 4"}',
     40, true),
    ('training_requirement', 'ai_oversight',
     'Human oversight of high-risk AI', 'Contrôle humain des systèmes d''IA à haut risque',
     'People assigned to oversee a high-risk AI system. AI Act Art. 26(2): the necessary competence, training and authority. Applies from 2 Dec 2027.',
     'Personnes chargées du contrôle humain d''un système d''IA à haut risque. AI Act art. 26(2) : compétence, formation et autorité nécessaires. Applicable à partir du 2 déc. 2027.',
     '{"regulation": "EU_AI_ACT", "audience": "ai_overseers", "refresh_months": 12, "obligation_id": null, "anchor": "AI Act Art. 26(2)", "applies_from": "2027-12-02"}',
     50, true)
on conflict do nothing;
