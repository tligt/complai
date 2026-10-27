// RECOSA — Compliance Pulse Edge Function
// Returns approved + published items from regulatory_updates and marketing_updates
// Public endpoint — no auth required (read-only, published content only)

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { marked } from "https://esm.sh/marked@11";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

// Formats an ISO timestamp as "June 2026" for card display.
function formatPublishedLabel(isoString) {
  if (!isoString) return null;
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

// Converts stored Markdown body_content into HTML for the detail page.
// Raw markdown remains the source of truth in Postgres — this conversion
// happens fresh on every request, so a future styling/structure change
// never requires touching stored content.
function renderBodyHtml(markdownText) {
  if (!markdownText) return null;
  try {
    return marked.parse(markdownText);
  } catch (e) {
    console.error("Markdown parse error:", e.message);
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
    );

    const url = new URL(req.url);
    const type     = url.searchParams.get("type");     // "regulatory" | "marketing"
    const category = url.searchParams.get("category"); // "GDPR" | "NIS2" | etc.
    const language = url.searchParams.get("language"); // "en" | "fr" | "nl"
    const slug     = url.searchParams.get("slug");      // fetch a single article by slug
    const limit    = parseInt(url.searchParams.get("limit") ?? "20");

    // ── Fetch regulatory updates ──────────────────────────────
    let regQuery = supabase
      .from("regulatory_updates")
      .select("id, title, summary, url, source, regulations, countries, severity, published_at, approved_at, language")
      .eq("status", "approved")
      .eq("published_to_pulse", true)
      .order("approved_at", { ascending: false })
      .limit(limit);

    const { data: regData, error: regError } = await regQuery;
    if (regError) throw regError;

    // ── Fetch marketing updates ───────────────────────────────
    let mktQuery = supabase
      .from("marketing_updates")
      .select("id, title, summary, url, source, category, severity, published_at, created_at, body_content, slug, language")
      .eq("status", "approved")
      .eq("published_to_pulse", true)
      .order("created_at", { ascending: false })
      .limit(limit);

    const { data: mktData, error: mktError } = await mktQuery;
    if (mktError) throw mktError;

    // ── Normalise to unified format ───────────────────────────
    const regulatory = (regData ?? []).map((item) => {
      const publishedAt = item.approved_at ?? item.published_at;
      return {
        id:              item.id,
        content_type:    "regulatory",
        display_type:    "Regulatory News",
        title:           item.title,
        summary:         item.summary,
        url:             item.url || null,       // external source link
        detail_url:      null,                    // regulatory items have no internal detail page
        body_html:       null,
        slug:            null,
        source:          item.source,
        category:        (item.regulations ?? [])[0] ?? "General",
        countries:       item.countries ?? ["EU"],
        severity:        item.severity ?? "info",
        language:        item.language ?? "en",
        published_at:    publishedAt,
        published_label: formatPublishedLabel(publishedAt),
      };
    });

    const marketing = (mktData ?? []).map((item) => {
      const publishedAt = item.created_at ?? item.published_at;
      const hasSlug = !!item.slug;
      return {
        id:              item.id,
        content_type:    "marketing",
        display_type:    "Articles",
        title:           item.title,
        summary:         item.summary,
        url:             item.url || null,                       // rarely used for RECOSA-authored pieces
        detail_url:      hasSlug ? `/pulse/${item.slug}` : null,  // internal detail page, if it exists
        body_html:       renderBodyHtml(item.body_content),
        slug:            item.slug || null,
        source:          item.source,
        category:        item.category ?? "Policy",
        countries:       ["EU"],
        severity:        item.severity ?? "info",
        language:        item.language ?? "en",
        published_at:    publishedAt,
        published_label: formatPublishedLabel(publishedAt),
      };
    });

    // ── If a specific slug was requested, return just that item ──
    if (slug) {
      const match = marketing.find((item) => item.slug === slug);
      if (!match) {
        return new Response(
          JSON.stringify({ error: "not_found" }),
          { headers: { ...corsHeaders, "Content-Type": "application/json" }, status: 404 },
        );
      }
      return new Response(
        JSON.stringify({ item: match, generated_at: new Date().toISOString() }),
        { headers: { ...corsHeaders, "Content-Type": "application/json", "Cache-Control": "public, max-age=300" }, status: 200 },
      );
    }

    // ── Merge + filter + sort ─────────────────────────────────
    let combined = [...regulatory, ...marketing];

    if (type && (type === "regulatory" || type === "marketing")) {
      combined = combined.filter((item) => item.content_type === type);
    }

    if (category) {
      combined = combined.filter((item) =>
        item.category?.toLowerCase() === category.toLowerCase()
      );
    }

    if (language) {
      combined = combined.filter((item) =>
        item.language?.toLowerCase() === language.toLowerCase()
      );
    }

    combined.sort((a, b) => {
      const dateA = new Date(a.published_at ?? 0).getTime();
      const dateB = new Date(b.published_at ?? 0).getTime();
      return dateB - dateA;
    });

    combined = combined.slice(0, limit);

    return new Response(
      JSON.stringify({
        items: combined,
        count: combined.length,
        generated_at: new Date().toISOString(),
      }),
      {
        headers: {
          ...corsHeaders,
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=300",
        },
        status: 200,
      },
    );

  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 500,
      },
    );
  }
});
