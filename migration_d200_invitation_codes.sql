-- D-200, 20 Nov 2026: invitation codes for beta testers.
--
-- A personal code (BETA-PRABIN-7K3Q) sent with the LinkedIn invitation turns
-- the account it signs up into an ACTIVE Professional account, free during the
-- beta, with no trial clock (D-173's rule for beta testers, automated). One use
-- by default; the random suffix keeps a code from being guessed from a name.
--
-- Nothing here is readable by the public: the tables have RLS on and no
-- policy (service role only). Two functions:
--   invitation_code_valid  — anyone may ask "is this code usable?" (true/false),
--                            so the free check can show the invitation before
--                            sign-up. It reveals nothing else.
--   claim_invitation_code  — service role only: uses the code for one person,
--                            atomically, and is safe to call again for the same
--                            person (first login may run more than once).

CREATE TABLE IF NOT EXISTS invitation_codes (
    code        text PRIMARY KEY,
    plan        text NOT NULL DEFAULT 'professional',
    note        text,
    max_uses    integer NOT NULL DEFAULT 1 CHECK (max_uses > 0),
    uses        integer NOT NULL DEFAULT 0 CHECK (uses >= 0),
    active      boolean NOT NULL DEFAULT true,
    created_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invitation_redemptions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL REFERENCES invitation_codes(code),
    user_id     uuid NOT NULL,
    redeemed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (code, user_id)
);

ALTER TABLE invitation_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitation_redemptions ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.invitation_code_valid(p_code text)
 RETURNS boolean
 LANGUAGE sql
 STABLE
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
    SELECT EXISTS (SELECT 1 FROM invitation_codes
                    WHERE code = upper(btrim(p_code)) AND active AND uses < max_uses);
$function$;

CREATE OR REPLACE FUNCTION public.claim_invitation_code(p_code text, p_user uuid)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_code text := upper(btrim(p_code));
    v_plan text;
BEGIN
    -- Already used by this person: the same answer again, nothing counted twice.
    SELECT c.plan INTO v_plan
      FROM invitation_redemptions r JOIN invitation_codes c ON c.code = r.code
     WHERE r.code = v_code AND r.user_id = p_user;
    IF FOUND THEN
        RETURN v_plan;
    END IF;
    UPDATE invitation_codes SET uses = uses + 1
     WHERE code = v_code AND active AND uses < max_uses
    RETURNING plan INTO v_plan;
    IF v_plan IS NULL THEN
        RETURN NULL;          -- unknown, used up or switched off
    END IF;
    INSERT INTO invitation_redemptions (code, user_id) VALUES (v_code, p_user);
    RETURN v_plan;
END;
$function$;

REVOKE ALL ON FUNCTION public.invitation_code_valid(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.invitation_code_valid(text) TO anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.claim_invitation_code(text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_invitation_code(text, uuid) TO service_role;
