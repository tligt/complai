-- S61 (D-160): AI Act inventory in three layers — model, system, use case.
--
--   systems           — unchanged. An AI system is an inventory system whose
--                       ai_role is not 'none'; its ai_role is the default role
--                       for its use cases. One list of systems, not two.
--   ai_models         — the model or service a system is built on (GPT-4o,
--                       an in-house classifier). One model, many systems.
--   ai_system_models  — which models each system uses.
--   ai_use_cases      — a business use of a system. Role and risk attach
--                       HERE: one system used for two purposes can be minimal
--                       risk for one and high risk for the other.
--   reference_values  — ai_annex_iii_area (the eight Annex III areas) and
--                       ai_prohibited_practice (Art. 5, with the Digital
--                       Omnibus additions).
--
-- The risk class is not stored: ai_rules.py works it out from the answers
-- below, so it cannot drift from them.
--
-- Idempotent: safe to run again.

-- ── Models ────────────────────────────────────────────────────────────────
create table if not exists public.ai_models (
    id                 uuid primary key default gen_random_uuid(),
    client_id          uuid not null references public.clients (id) on delete cascade,
    user_id            uuid references auth.users (id) on delete set null,
    name               text not null check (char_length(name) between 1 and 200),
    supplier           text check (supplier is null or char_length(supplier) <= 200),
    version            text check (version is null or char_length(version) <= 100),
    general_purpose    boolean,          -- a GPAI model (Art. 3(63)); NULL = not known
    origin             text not null default 'third_party'
                       check (origin in ('third_party', 'open_weights', 'in_house')),
    documentation_url  text check (documentation_url is null or char_length(documentation_url) <= 500),
    notes              text check (notes is null or char_length(notes) <= 2000),
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
create index if not exists ai_models_client_idx on public.ai_models (client_id);
alter table public.ai_models enable row level security;
drop policy if exists ai_models_select on public.ai_models;
create policy ai_models_select on public.ai_models for select
    using (has_client_access(client_id, null) or is_admin_user());
drop policy if exists ai_models_insert on public.ai_models;
create policy ai_models_insert on public.ai_models for insert
    with check (can_edit_client(client_id, null) and user_id = (select auth.uid()));
drop policy if exists ai_models_update on public.ai_models;
create policy ai_models_update on public.ai_models for update
    using (can_edit_client(client_id, null)) with check (can_edit_client(client_id, null));
drop policy if exists ai_models_delete on public.ai_models;
create policy ai_models_delete on public.ai_models for delete
    using (can_edit_client(client_id, null));

-- ── System ↔ model ────────────────────────────────────────────────────────
create table if not exists public.ai_system_models (
    id          uuid primary key default gen_random_uuid(),
    client_id   uuid not null references public.clients (id) on delete cascade,
    system_id   uuid not null references public.systems (id) on delete cascade,
    model_id    uuid not null references public.ai_models (id) on delete cascade,
    user_id     uuid references auth.users (id) on delete set null,
    created_at  timestamptz not null default now(),
    unique (system_id, model_id)
);
create index if not exists ai_system_models_client_idx on public.ai_system_models (client_id);
alter table public.ai_system_models enable row level security;
drop policy if exists ai_system_models_select on public.ai_system_models;
create policy ai_system_models_select on public.ai_system_models for select
    using (has_client_access(client_id, null) or is_admin_user());
drop policy if exists ai_system_models_insert on public.ai_system_models;
create policy ai_system_models_insert on public.ai_system_models for insert
    with check (can_edit_client(client_id, null) and user_id = (select auth.uid()));
drop policy if exists ai_system_models_delete on public.ai_system_models;
create policy ai_system_models_delete on public.ai_system_models for delete
    using (can_edit_client(client_id, null));

-- ── Use cases ─────────────────────────────────────────────────────────────
create table if not exists public.ai_use_cases (
    id                     uuid primary key default gen_random_uuid(),
    client_id              uuid not null references public.clients (id) on delete cascade,
    system_id              uuid not null references public.systems (id) on delete cascade,
    user_id                uuid references auth.users (id) on delete set null,
    name                   text not null check (char_length(name) between 1 and 200),
    description            text check (description is null or char_length(description) <= 2000),
    business_owner         text check (business_owner is null or char_length(business_owner) <= 200),
    status                 text not null default 'in_use'
                           check (status in ('planned', 'in_use', 'retired')),
    -- Role (Art. 3(3)-(7)); NULL = the system's ai_role.
    role                   text check (role is null or role in ('deployer', 'provider', 'importer', 'distributor')),
    -- Art. 25(1): a deployer becomes a provider.
    own_name_or_brand      boolean,      -- (a) put on the market under their name or trademark
    substantially_modified boolean,      -- (b) substantial modification
    purpose_changed        boolean,      -- (c) intended purpose changed so it becomes high-risk
    -- Art. 5 screening. NULL = not screened; '{}' = screened, none apply.
    prohibited_practices   text[],
    -- Annex III (Art. 6(2)). NULL = not answered; 'none' = no area applies.
    annex_iii_area         text,
    -- Art. 6(3) derogation, and the profiling exclusion that defeats it.
    art6_3_condition       text check (art6_3_condition is null or art6_3_condition in
                               ('narrow_procedural', 'improves_human_result',
                                'detects_patterns', 'preparatory')),
    art6_3_reason          text check (art6_3_reason is null or char_length(art6_3_reason) <= 2000),
    profiles_people        boolean,
    -- Art. 50 transparency.
    interacts_with_people  boolean,
    generates_content      boolean,      -- synthetic audio, image, video or text
    deep_fake              boolean,      -- published content resembling real people or events
    public_interest_text   boolean,      -- published text informing the public
    emotion_or_biometric   boolean,      -- emotion recognition or biometric categorisation
    -- Art. 26 (high-risk deployers).
    used_on_workers        boolean,
    oversight_employee_id  uuid references public.employees (id) on delete set null,
    notes                  text check (notes is null or char_length(notes) <= 2000),
    assessed_at            timestamptz,
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now()
);
create index if not exists ai_use_cases_client_idx on public.ai_use_cases (client_id);
create index if not exists ai_use_cases_system_idx on public.ai_use_cases (system_id);
alter table public.ai_use_cases enable row level security;
drop policy if exists ai_use_cases_select on public.ai_use_cases;
create policy ai_use_cases_select on public.ai_use_cases for select
    using (has_client_access(client_id, null) or is_admin_user());
drop policy if exists ai_use_cases_insert on public.ai_use_cases;
create policy ai_use_cases_insert on public.ai_use_cases for insert
    with check (can_edit_client(client_id, null) and user_id = (select auth.uid()));
drop policy if exists ai_use_cases_update on public.ai_use_cases;
create policy ai_use_cases_update on public.ai_use_cases for update
    using (can_edit_client(client_id, null)) with check (can_edit_client(client_id, null));
drop policy if exists ai_use_cases_delete on public.ai_use_cases;
create policy ai_use_cases_delete on public.ai_use_cases for delete
    using (can_edit_client(client_id, null));

-- ── Reference data ────────────────────────────────────────────────────────
alter table public.reference_values drop constraint if exists reference_values_type_valid;
alter table public.reference_values add constraint reference_values_type_valid
    check (value_type in ('system_category', 'data_category', 'special_category',
        'criminal_data', 'art9_condition', 'data_subject_category', 'legal_basis',
        'transfer_mechanism', 'dpa_status', 'controller_role', 'system_role',
        'criticality', 'ai_role', 'security_measure', 'jurisdiction',
        'retention_basis', 'retention_unit', 'data_source', 'dpia_risk',
        'nis2_risk', 'training_requirement', 'ai_annex_iii_area',
        'ai_prohibited_practice'));

insert into public.reference_values (value_type, code, label_en, label_fr, note_en, metadata, sort_order, active) values
 ('ai_annex_iii_area', 'biometrics', 'Biometrics', 'Biométrie',
  'Remote biometric identification, biometric categorisation by sensitive attributes, emotion recognition (where not prohibited).', '{"point": "1"}', 10, true),
 ('ai_annex_iii_area', 'critical_infrastructure', 'Critical infrastructure', 'Infrastructures critiques',
  'Safety components in the management and operation of critical digital infrastructure, road traffic, or the supply of water, gas, heating or electricity.', '{"point": "2"}', 20, true),
 ('ai_annex_iii_area', 'education', 'Education and vocational training', 'Éducation et formation professionnelle',
  'Deciding access or admission, evaluating learning outcomes, assessing the appropriate level of education, monitoring students during tests.', '{"point": "3"}', 30, true),
 ('ai_annex_iii_area', 'employment', 'Employment and workers management', 'Emploi et gestion des travailleurs',
  'Recruitment and selection (targeted job ads, filtering applications, evaluating candidates); decisions on promotion, termination, task allocation; monitoring and evaluating performance and behaviour.', '{"point": "4"}', 40, true),
 ('ai_annex_iii_area', 'essential_services', 'Access to essential services', 'Accès aux services essentiels',
  'Eligibility for public benefits; creditworthiness and credit scores (except fraud detection); risk and pricing in life and health insurance; dispatching emergency calls.', '{"point": "5"}', 50, true),
 ('ai_annex_iii_area', 'law_enforcement', 'Law enforcement', 'Application de la loi',
  'Uses by or on behalf of law enforcement authorities.', '{"point": "6"}', 60, true),
 ('ai_annex_iii_area', 'migration', 'Migration, asylum and border control', 'Migration, asile et contrôle aux frontières',
  'Uses by or on behalf of competent public authorities.', '{"point": "7"}', 70, true),
 ('ai_annex_iii_area', 'justice_democracy', 'Justice and democratic processes', 'Justice et processus démocratiques',
  'Assisting judicial authorities in researching and interpreting facts and law; influencing the outcome of an election or voting behaviour.', '{"point": "8"}', 80, true),
 ('ai_prohibited_practice', 'manipulation', 'Subliminal, manipulative or deceptive techniques', 'Techniques subliminales, manipulatrices ou trompeuses',
  'Materially distorting behaviour in a way that causes or is likely to cause significant harm.', '{"article": "Art. 5(1)(a)"}', 10, true),
 ('ai_prohibited_practice', 'vulnerabilities', 'Exploiting vulnerabilities', 'Exploitation des vulnérabilités',
  'Of age, disability or a specific social or economic situation, causing significant harm.', '{"article": "Art. 5(1)(b)"}', 20, true),
 ('ai_prohibited_practice', 'social_scoring', 'Social scoring', 'Notation sociale',
  'Evaluating or classifying people over time by social behaviour or personal traits, leading to unjustified or disproportionate detrimental treatment.', '{"article": "Art. 5(1)(c)"}', 30, true),
 ('ai_prohibited_practice', 'crime_prediction', 'Predicting crime from profiling alone', 'Prédiction d''infractions sur la seule base du profilage',
  'Assessing the risk that a person commits a criminal offence based solely on profiling or personality traits.', '{"article": "Art. 5(1)(d)"}', 40, true),
 ('ai_prohibited_practice', 'facial_scraping', 'Untargeted scraping of facial images', 'Moissonnage non ciblé d''images faciales',
  'Creating or expanding facial recognition databases from the internet or CCTV footage.', '{"article": "Art. 5(1)(e)"}', 50, true),
 ('ai_prohibited_practice', 'emotion_work_education', 'Emotion recognition at work or in education', 'Reconnaissance des émotions au travail ou dans l''enseignement',
  'Except for medical or safety reasons.', '{"article": "Art. 5(1)(f)"}', 60, true),
 ('ai_prohibited_practice', 'biometric_sensitive', 'Biometric categorisation by sensitive traits', 'Catégorisation biométrique selon des caractéristiques sensibles',
  'Inferring race, political opinions, trade union membership, religious or philosophical beliefs, sex life or sexual orientation.', '{"article": "Art. 5(1)(g)"}', 70, true),
 ('ai_prohibited_practice', 'realtime_biometric_id', 'Real-time remote biometric identification in public spaces', 'Identification biométrique à distance en temps réel dans l''espace public',
  'For law enforcement, outside the narrow exceptions.', '{"article": "Art. 5(1)(h)"}', 80, true),
 ('ai_prohibited_practice', 'intimate_imagery', 'Non-consensual intimate imagery', 'Images intimes non consenties',
  'Generating non-consensual intimate imagery ("nudification"). Added by the Digital Omnibus, from 2 Dec 2026.', '{"article": "Art. 5 (as amended)", "applies_from": "2026-12-02"}', 90, true),
 ('ai_prohibited_practice', 'csam', 'Child sexual abuse material', 'Matériel pédopornographique',
  'Generating child sexual abuse material. Added by the Digital Omnibus, from 2 Dec 2026.', '{"article": "Art. 5 (as amended)", "applies_from": "2026-12-02"}', 100, true)
on conflict do nothing;
