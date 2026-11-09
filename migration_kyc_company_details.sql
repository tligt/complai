-- KYC company details (9 Nov, with the user): the company's full address,
-- phone and VAT number are required at company setup; the person signing
-- up may add a direct phone number.
--
-- registered_address stays the text the documents print ("street\npostcode
-- city"); it is now composed from the structured fields below, which the
-- back office (KYC) and, later, invoicing (S46) read.

alter table public.clients
    add column if not exists address_street   text,
    add column if not exists address_postcode text,
    add column if not exists address_city     text,
    add column if not exists phone            text,
    add column if not exists vat_number       text;

alter table public.profiles
    add column if not exists phone text;

comment on column public.clients.address_street is 'KYC: street and number of the registered office.';
comment on column public.clients.phone is 'KYC: the company''s main phone number.';
comment on column public.clients.vat_number is 'KYC: VAT number with its country prefix (BE0783225609, FR12552032534, NL…B01).';
comment on column public.profiles.phone is 'The person''s direct phone number (optional).';
