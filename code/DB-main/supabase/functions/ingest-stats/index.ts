// 센싱 모듈 telemetry → zone_stats 저장
// 기기는 x-device-token 헤더로 인증하고, 함수 안에서만 service role로 DB에 쓴다.
import { createClient } from "jsr:@supabase/supabase-js@2";

const ALLOWED = ["device_id", "zone", "period_start", "period_end", "observed_sec", "bad_sec_by_reason", "alerts"];

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
  const token = req.headers.get("x-device-token");
  if (!token) return new Response("unauthorized", { status: 401 });

  const rows = await req.json().catch(() => null);
  if (!Array.isArray(rows) || rows.length === 0 || rows.length > 500) {
    return new Response("bad request", { status: 400 });
  }

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const deviceId = rows[0].device_id;
  const { data: device } = await db.from("devices").select("token_hash, revoked").eq("device_id", deviceId).single();
  if (!device || device.revoked || device.token_hash !== (await sha256(token))) {
    return new Response("unauthorized", { status: 401 });
  }

  // 허용된 집계 필드만 남기고, 다른 기기 ID를 섞어 보내는 요청은 거부
  if (rows.some((r) => r.device_id !== deviceId)) return new Response("bad request", { status: 400 });
  const clean = rows.map((r) => Object.fromEntries(ALLOWED.map((k) => [k, r[k]])));
  for (const r of clean) {
    r.period_start = new Date(Number(r.period_start) * 1000).toISOString();
    r.period_end = new Date(Number(r.period_end) * 1000).toISOString();
  }

  const { error } = await db.from("zone_stats").insert(clean);
  if (error) return new Response("insert failed", { status: 500 });
  return new Response(null, { status: 204 });
});
