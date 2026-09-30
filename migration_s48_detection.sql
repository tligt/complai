-- S48: onboarding auto-detection.
--
-- 1. Two new fingerprint types for DNS signals: 'mx' (the domain's mail
--    servers) and 'spf_include' (services named in its SPF record).
-- 2. Loads the fingerprints from inventory_seed.py (the authored source).
--    Fingerprints only: the rest of the catalogue is untouched, so nothing
--    edited in the database since the last full seed is overwritten.
--
-- Generated from inventory_seed.py; idempotent, safe to run again.

ALTER TABLE public.vendor_domain_patterns
    DROP CONSTRAINT IF EXISTS vendor_domain_patterns_match_type_valid;
ALTER TABLE public.vendor_domain_patterns
    ADD CONSTRAINT vendor_domain_patterns_match_type_valid
    CHECK (match_type = ANY (ARRAY['domain', 'script_src', 'cookie_name', 'header',
                                   'mx', 'spf_include']));

INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'googletagmanager.com/gtag/js', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'google_analytics'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'google-analytics.com', 'domain', 'high' FROM public.vendor_catalogue WHERE key = 'google_analytics'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'googletagmanager.com', 'script_src', 'medium' FROM public.vendor_catalogue WHERE key = 'google_analytics'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, '_ga', 'cookie_name', 'high' FROM public.vendor_catalogue WHERE key = 'google_analytics'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'mail.protection.outlook.com', 'mx', 'high' FROM public.vendor_catalogue WHERE key = 'microsoft_365'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'spf.protection.outlook.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'microsoft_365'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'office.com', 'domain', 'medium' FROM public.vendor_catalogue WHERE key = 'microsoft_365'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'outlook.office365.com', 'domain', 'high' FROM public.vendor_catalogue WHERE key = 'microsoft_365'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hubspotemail.net', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hs-banner.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hs-analytics.net', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hsforms.net', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hsappstatic.net', 'script_src', 'medium' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hs-scripts.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'hubspot.com', 'domain', 'medium' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, '__hstc', 'cookie_name', 'high' FROM public.vendor_catalogue WHERE key = 'hubspot'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'spf.sendinblue.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'brevo'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'spf.brevo.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'brevo'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'sendinblue.com', 'domain', 'medium' FROM public.vendor_catalogue WHERE key = 'brevo'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'sibautomation.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'brevo'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'connect.facebook.net', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'meta_pixel'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'facebook.com/tr', 'domain', 'high' FROM public.vendor_catalogue WHERE key = 'meta_pixel'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, '_fbp', 'cookie_name', 'high' FROM public.vendor_catalogue WHERE key = 'meta_pixel'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'snap.licdn.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'linkedin_insight'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'li_sugr', 'cookie_name', 'medium' FROM public.vendor_catalogue WHERE key = 'linkedin_insight'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'js.stripe.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'stripe'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, '__stripe_mid', 'cookie_name', 'high' FROM public.vendor_catalogue WHERE key = 'stripe'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'js.mollie.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'mollie'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, '_spf.odoo.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'odoo'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'mail.ovh.net', 'mx', 'high' FROM public.vendor_catalogue WHERE key = 'ovhcloud'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'mx.ovh.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'ovhcloud'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'amazonses.com', 'spf_include', 'medium' FROM public.vendor_catalogue WHERE key = 'aws'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'aspmx.l.google.com', 'mx', 'high' FROM public.vendor_catalogue WHERE key = 'google_workspace'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'googlemail.com', 'mx', 'high' FROM public.vendor_catalogue WHERE key = 'google_workspace'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'smtp.google.com', 'mx', 'high' FROM public.vendor_catalogue WHERE key = 'google_workspace'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, '_spf.google.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'google_workspace'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'mail.zendesk.com', 'spf_include', 'high' FROM public.vendor_catalogue WHERE key = 'zendesk'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
INSERT INTO public.vendor_domain_patterns (catalogue_id, pattern, match_type, confidence)
SELECT id, 'zdassets.com', 'script_src', 'high' FROM public.vendor_catalogue WHERE key = 'zendesk'
ON CONFLICT (catalogue_id, pattern, match_type) DO UPDATE SET confidence = EXCLUDED.confidence;
