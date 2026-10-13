// 긴 문서를 documents(제목) + chunks(분할된 내용 + Gemini 임베딩)로 저장
// 실행: node ingest_document.mjs <문서.txt> [--user <user_id>] [--sql <out.sql>]
//   - 문서의 첫 줄이 제목, 나머지가 본문
//   - 기본: Supabase REST로 저장 (.env의 SUPABASE_KEY는 service_role 키 필요 — RLS 우회)
//   - --sql: DB에 쓰지 않고 실행할 SQL 파일만 생성
import { readFileSync, writeFileSync } from "node:fs";

try {
  for (const line of readFileSync(new URL("./.env", import.meta.url), "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([\w.]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
} catch {}

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const file = args.find((a, i) => !a.startsWith("--") && !args[i - 1]?.startsWith("--"));
const USER_ID = opt("--user") ?? null;
const SQL_OUT = opt("--sql");
if (!file) { console.error("사용법: node ingest_document.mjs <문서.txt> [--user <uuid>] [--sql <out.sql>]"); process.exit(1); }

const MODEL = "gemini-embedding-001";
const DIM = 768;
const MAX_CHARS = 500; // chunk 최대 길이
const OVERLAP_SENTENCES = 1; // 문단 중간에서 잘릴 때 앞 chunk의 마지막 문장을 겹쳐서 문맥 유지

// ---------- 분할 ----------
const splitSentences = (p) => p.match(/[^.!?。]+[.!?。]?\s*/g)?.map((s) => s.trim()).filter(Boolean) ?? [p];

function chunkText(body) {
  // 1) 빈 줄 기준 문단 → 2) 짧은 문단은 MAX_CHARS까지 합치고 → 3) 긴 문단은 문장 단위로 쪼갬
  const paragraphs = body.split(/\n\s*\n/).map((p) => p.replace(/[ \t]*\r?\n[ \t]*/g, "\n").trim()).filter(Boolean);
  const chunks = [];
  let cur = "";
  const flush = () => { if (cur) chunks.push(cur); cur = ""; };

  for (const p of paragraphs) {
    if (p.length > MAX_CHARS) {
      flush();
      const sents = splitSentences(p);
      let buf = [];
      for (const s of sents) {
        if (buf.length && [...buf, s].join(" ").length > MAX_CHARS) {
          chunks.push(buf.join(" "));
          buf = buf.slice(-OVERLAP_SENTENCES);
        }
        buf.push(s);
      }
      if (buf.length) chunks.push(buf.join(" "));
    } else if ((cur ? cur.length + 1 : 0) + p.length > MAX_CHARS) {
      flush();
      cur = p;
    } else {
      cur = cur ? `${cur}\n${p}` : p;
    }
  }
  flush();
  return chunks;
}

// ---------- 임베딩 ----------
async function embed(texts, title) {
  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:batchEmbedContents`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": process.env.GEMINI_API_KEY },
    body: JSON.stringify({
      requests: texts.map((text) => ({
        model: `models/${MODEL}`,
        content: { parts: [{ text }] },
        taskType: "RETRIEVAL_DOCUMENT",
        title, // 문서 제목을 함께 넘기면 검색 품질이 좋아짐
        outputDimensionality: DIM,
      })),
    }),
  });
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${await res.text()}`);
  return (await res.json()).embeddings.map(({ values }) => {
    const n = Math.hypot(...values) || 1;
    return values.map((x) => x / n);
  });
}

// ---------- 실행 ----------
const [title, ...rest] = readFileSync(file, "utf8").replace(/^﻿/, "").split(/\r?\n/);
const chunks = chunkText(rest.join("\n"));
console.log(`제목: ${title.trim()}\nchunk ${chunks.length}개 (길이: ${chunks.map((c) => c.length).join(", ")})`);
const vectors = await embed(chunks, title.trim());

if (SQL_OUT) {
  const q = (s) => `'${s.replace(/'/g, "''")}'`;
  const vec = (v) => `'[${v.map((x) => x.toFixed(5)).join(",")}]'`;
  const sql = `with d as (
  insert into public.documents (title, user_id) values (${q(title.trim())}, ${USER_ID ? q(USER_ID) + "::uuid" : "null"}) returning id
)
insert into public.chunks (document_id, content, embedding)
select d.id, x.content, x.embedding::extensions.vector from d, (values
${chunks.map((c, i) => `  (${i}, ${q(c)}, ${vec(vectors[i])})`).join(",\n")}
) as x(ord, content, embedding)
order by x.ord
returning id, document_id, length(content) as len;`;
  writeFileSync(SQL_OUT, sql);
  console.log(`SQL 저장: ${SQL_OUT} (${sql.length} bytes)`);
} else {
  const URL_ = process.env.SUPABASE_URL || "https://hzjigjfgdaytvwytesxu.supabase.co";
  const KEY = process.env.SUPABASE_KEY;
  const sb = (path, body) => fetch(`${URL_}/rest/v1/${path}`, {
    method: "POST",
    headers: { apikey: KEY, Authorization: `Bearer ${KEY}`, "Content-Type": "application/json", Prefer: "return=representation" },
    body: JSON.stringify(body),
  }).then(async (r) => { if (!r.ok) throw new Error(`Supabase ${r.status}: ${await r.text()}`); return r.json(); });

  const [doc] = await sb("documents", { title: title.trim(), user_id: USER_ID });
  const rows = await sb("chunks", chunks.map((content, i) => ({ document_id: doc.id, content, embedding: JSON.stringify(vectors[i]) })));
  console.log(`저장 완료: document id=${doc.id}, chunks id=${rows.map((r) => r.id).join(", ")}`);
}
