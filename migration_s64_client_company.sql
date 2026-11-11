-- S64 (D-170): the client company is the account.
--
-- RECOSA's business relation is with the account: the company that signs and
-- pays. Its identity (KYC) now lives on the account. The companies inside an
-- account are the companies it monitors: no relation with RECOSA, and their
-- details are optional.
--
-- accounts already had name, contract contact, billing email, VAT number.

alter table public.accounts
  add column if not exists legal_name        text,
  add column if not exists legal_form        text,
  add column if not exists enterprise_number text,
  add column if not exists country           text,
  add column if not exists address_street    text,
  add column if not exists address_postcode  text,
  add column if not exists address_city      text,
  add column if not exists phone             text;

-- Backfill: an account that monitors itself. Its company is the only one in
-- the account, or the one named like the account ("creagent" for
-- "creagent.be", the email domain the account was named after). Copies only
-- into empty account fields; the company keeps its own copy.
with own as (
  select distinct on (a.id) a.id as acc_id, c.*
  from public.accounts a
  join public.clients c on c.account_id = a.id
  where lower(c.company_name) = lower(split_part(a.name, '.', 1))
     or (select count(*) from public.clients x where x.account_id = a.id) = 1
  order by a.id, (lower(c.company_name) = lower(split_part(a.name, '.', 1))) desc, c.created_at
)
update public.accounts a set
  legal_name        = coalesce(a.legal_name, own.legal_name, own.company_name),
  legal_form        = coalesce(a.legal_form, own.legal_form),
  enterprise_number = coalesce(a.enterprise_number, own.enterprise_number),
  vat_number        = coalesce(a.vat_number, own.vat_number),
  country           = coalesce(a.country, own.country),
  address_street    = coalesce(a.address_street, own.address_street,
                               nullif(split_part(own.registered_address, E'\n', 1), '')),
  address_postcode  = coalesce(a.address_postcode, own.address_postcode,
                               nullif(split_part(split_part(own.registered_address, E'\n', 2), ' ', 1), '')),
  address_city      = coalesce(a.address_city, own.address_city,
                               nullif(trim(substr(split_part(own.registered_address, E'\n', 2),
                                      length(split_part(split_part(own.registered_address, E'\n', 2), ' ', 1)) + 1)), '')),
  phone             = coalesce(a.phone, own.phone)
from own
where own.acc_id = a.id;
