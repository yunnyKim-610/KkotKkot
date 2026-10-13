// chunks.content 를 Gemini 임베딩(gemini-embedding-001, 768차원)으로 변환해 chunks.embedding 에 저장
// 실행: node embed_chunks.mjs        (embedding 이 비어있는 행만)
//       node embed_chunks.mjs --all  (전체 다시 임베딩)
import { readFileSync } from "node:fs";

// .env 읽기 (GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY)
try {
  for (const line of readFileSync(new URL("./.env", import.meta.url), "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([\w.]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
} catch {}

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL || "https://hzjigjfgdaytvwytesxu.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY; // service_role 키 권장 (RLS 우회)
if (!GEMINI_API_KEY || !SUPABASE_KEY) {
  console.error(".env 에 GEMINI_API_KEY 와 SUPABASE_KEY 를 설정하세요.");
  process.exit(1);
}

const MODEL = "gemini-embedding-001";
const DIM = 768;
const BATCH = 50;

const sb = (path, init = {}) =>
  fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      "Content-Type": "application/json",
      ...init.headers,
    },
  });

// 768차원처럼 잘라낸 출력은 정규화되어 있지 않으므로 직접 L2 정규화
const normalize = (v) => {
  const n = Math.hypot(...v) || 1;
  return v.map((x) => x / n);
};

async function embedBatch(texts) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:batchEmbedContents`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY },
      body: JSON.stringify({
        requests: texts.map((text) => ({
          model: `models/${MODEL}`,
          content: { parts: [{ text }] },
          taskType: "RETRIEVAL_DOCUMENT",
          outputDimensionality: DIM,
        })),
      }),
    }
  );
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${await res.text()}`);
  const { embeddings } = await res.json();
  return embeddings.map((e) => normalize(e.values));
}

const filter = process.argv.includes("--all") ? "" : "&embedding=is.null";
const res = await sb(`chunks?select=id,content&content=not.is.null${filter}&order=id`);
if (!res.ok) throw new Error(`Supabase ${res.status}: ${await res.text()}`);
const rows = (await res.json()).filter((r) => r.content.trim());
console.log(`임베딩 대상: ${rows.length}개`);

for (let i = 0; i < rows.length; i += BATCH) {
  const batch = rows.slice(i, i + BATCH);
  const vectors = await embedBatch(batch.map((r) => r.content));
  for (const [j, row] of batch.entries()) {
    const up = await sb(`chunks?id=eq.${row.id}`, {
      method: "PATCH",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({ embedding: JSON.stringify(vectors[j]) }),
    });
    if (!up.ok) throw new Error(`id=${row.id} 저장 실패 ${up.status}: ${await up.text()}`);
    console.log(`✔ id=${row.id}`);
  }
}
console.log("완료");
