// embedding이 비어 있는 chunks를 찾아 Gemini 임베딩을 채워 넣음
// 새 문서/chunk를 넣은 뒤 이 함수를 한 번 호출하면 됨 (이미 임베딩된 행은 건드리지 않음)
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY") ?? "";
const MODEL = "gemini-embedding-001";
const DIM = 768;
const BATCH = 50;

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (!GEMINI_API_KEY) return json({ error: "서버에 GEMINI_API_KEY 비밀값이 설정되지 않았습니다." }, 500);

  try {
    // RLS를 우회해 모든 사용자의 미처리 chunk를 채움 (결과로는 개수만 반환)
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { data: rows, error } = await admin
      .from("chunks")
      .select("id, content, documents(title)")
      .is("embedding", null)
      .not("content", "is", null)
      .order("id")
      .limit(500);
    if (error) throw error;

    let embedded = 0;
    for (let i = 0; i < rows.length; i += BATCH) {
      const batch = rows.slice(i, i + BATCH);
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:batchEmbedContents`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY },
        body: JSON.stringify({
          requests: batch.map((r) => ({
            model: `models/${MODEL}`,
            content: { parts: [{ text: r.content }] },
            taskType: "RETRIEVAL_DOCUMENT",
            // deno-lint-ignore no-explicit-any
            title: (r.documents as any)?.title ?? undefined,
            outputDimensionality: DIM,
          })),
        }),
      });
      if (!res.ok) throw new Error(`Gemini ${res.status}: ${await res.text()}`);
      const { embeddings } = await res.json();

      for (const [j, row] of batch.entries()) {
        const v: number[] = embeddings[j].values;
        const n = Math.hypot(...v) || 1;
        const { error: upErr } = await admin
          .from("chunks")
          .update({ embedding: JSON.stringify(v.map((x) => x / n)) })
          .eq("id", row.id);
        if (upErr) throw upErr;
        embedded++;
      }
    }
    return json({ embedded, remaining: rows.length === 500 ? "더 있을 수 있음 - 다시 호출하세요" : 0 });
  } catch (e) {
    console.error(e);
    return json({ error: e instanceof Error ? e.message : String(e) }, 500);
  }
});
