-- Sign-up with a plan (27 Oct 2026, D-126).
--
-- The website sells Starter, Professional and Enterprise; the app knew only
-- Professional and Advisory. Widens the allowed tiers; no existing row
-- changes. Advisory stays (consultants, on request); Enterprise is set by an
-- admin after the "contact us" conversation.

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_subscription_tier_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_subscription_tier_check
    CHECK (subscription_tier = ANY (ARRAY['starter', 'professional', 'advisory', 'enterprise']));
