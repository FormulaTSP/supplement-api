// supabase/functions/lab-mock-callback/index.ts
import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

type IncomingObservation = {
  loinc?: string | null;
  lab_code?: string | null;
  specimen?: string | null;
  value?: number | null;
  unit?: string | null;
  ref_low?: number | null;
  ref_high?: number | null;
  flag?: string | null;
};

function errToMsg(e: unknown) {
  if (e && typeof e === "object") {
    const any = e as any;
    if (any.message) return String(any.message);
    if (any.error?.message) return String(any.error.message);
    try { return JSON.stringify(e); } catch {}
  }
  return String(e);
}

serve(async (req) => {
  try {
    // CORS preflight
    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "authorization, content-type",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
        },
      });
    }

    if (req.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Supabase injects SUPABASE_URL automatically; SERVICE_ROLE_KEY is your secret
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
    const SERVICE_ROLE = Deno.env.get("SERVICE_ROLE_KEY");
    if (!SUPABASE_URL || !SERVICE_ROLE) {
      return new Response(
        JSON.stringify({ ok: false, error: "Missing env: SUPABASE_URL or SERVICE_ROLE_KEY" }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      );
    }

    const sb = createClient(SUPABASE_URL, SERVICE_ROLE);

    const body = await req.json();
    const orderId: string | undefined = body?.order_id;
    if (!orderId) {
      return new Response(JSON.stringify({ ok: false, error: "Missing order_id" }), {
        status: 400, headers: { "Content-Type": "application/json" },
      });
    }

    const incoming: IncomingObservation[] = Array.isArray(body?.observations) ? body.observations : [];

    // 1) create results envelope
    const { data: resultIns, error: resErr } = await sb
      .from("results")
      .insert({ order_id: orderId, received_at: new Date().toISOString(), status: "final" })
      .select()
      .single();
    if (resErr) throw resErr;

    // 2) map obs -> marker_id via markers_map (prefer LOINC, fallback lab_code)
    const obsToInsert: any[] = [];
    for (const o of incoming) {
      let marker_id: string | null = null;

      if (o?.loinc) {
        const { data: mByLoinc } = await sb
          .from("markers_map")
          .select("marker_id")
          .eq("loinc_code", o.loinc)
          .maybeSingle();
        if (mByLoinc?.marker_id) marker_id = mByLoinc.marker_id;
      }

      if (!marker_id && o?.lab_code) {
        const { data: mByLab } = await sb
          .from("markers_map")
          .select("marker_id")
          .ilike("typical_local_codes", `%${o.lab_code}%`)
          .maybeSingle();
        if (mByLab?.marker_id) marker_id = mByLab.marker_id;
      }

      obsToInsert.push({
        result_id: resultIns.id,
        marker_id,
        loinc_code: o?.loinc ?? null,
        lab_code: o?.lab_code ?? null,
        specimen: o?.specimen ?? "S",
        value: o?.value ?? null,
        unit: o?.unit ?? null,
        ref_low: o?.ref_low ?? null,
        ref_high: o?.ref_high ?? null,
        flag: o?.flag ?? null,
        observed_at: new Date().toISOString(),
      });
    }

    // 3) insert observations and report counts
    let inserted = 0;
    if (obsToInsert.length > 0) {
      const { data: ins, error: obsErr } = await sb
        .from("observations")
        .insert(obsToInsert)
        .select("id");
      if (obsErr) throw obsErr;
      inserted = ins?.length ?? 0;
    }

    return new Response(
      JSON.stringify({
        ok: true,
        result_id: resultIns.id,
        requested: incoming.length,
        built: obsToInsert.length,
        inserted,
      }),
      { status: 200, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } },
    );
  } catch (e) {
    console.error("lab-mock-callback error:", e);
    return new Response(
      JSON.stringify({ ok: false, error: errToMsg(e) }),
      { status: 400, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } },
    );
  }
});