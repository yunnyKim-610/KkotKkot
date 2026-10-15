// FAQ CSV(title=질문, content=답변)를 faqs 테이블에 동기화 (질문 기준 upsert)
// 실행: node ingest_faq.mjs [kkotkkot_faq.csv] [--prune]
//   - 새 질문은 추가, 답변이 바뀐 질문은 수정하고 다시 임베딩, 그대로인 질문은 건너뜀
//   - --prune: CSV에 없는 질문을 faqs에서 삭제
//   - .env의 SUPABASE_KEY는 service_role 키 필요 (RLS 우회)
import { readFileSync } from "node:fs";

try {
  for (const line of readFileSync(new URL("./.env", import.meta.url), "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([\w.]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
} catch {}

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith("--")) ?? new URL("./kkotkkot_faq.csv", import.meta.url);
const PRUNE = args.includes("--prune");

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL || "https://hzjigjfgdaytvwytesxu.supabase.co";
const SUPABASE_KEY = process.env.SUPABASE_KEY;
if (!GEMINI_API_KEY || !SUPABASE_KEY) {
  console.error(".env 에 GEMINI_API_KEY 와 SUPABASE_KEY 를 설정하세요.");
  process.exit(1);
}

const MODEL = "gemini-embedding-001";
const DIM = 768;

// ---------- CSV 파싱 (따옴표 안의 쉼표·줄바꿈·"" 이스케이프 지원) ----------
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += ch;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows.filter((r) => r.some((f) => f.trim()));
}

const [header, ...lines] = parseCsv(readFileSync(file, "utf8").replace(/^﻿/, ""));
const qi = header.indexOf("title"), ai = header.indexOf("content");
if (qi < 0 || ai < 0) { console.error("CSV 첫 줄은 title,content 여야 합니다."); process.exit(1); }
const faqs = lines.map((r) => ({ question: r[qi].trim(), answer: r[ai].trim() })).filter((f) => f.question && f.answer);

// ---------- Supabase ----------
const sb = async (path, init = {}) => {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}`, "Content-Type": "application/json", ...init.headers },
  });
  if (!res.ok) throw new Error(`Supabase ${res.status}: ${await res.text()}`);
  return res.status === 204 ? null : res.json();
};

// ---------- 임베딩 (질문을 title로 함께 넘김) ----------
async function embed(items) {
  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:batchEmbedContents`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY },
    body: JSON.stringify({
      requests: items.map((f) => ({
        model: `models/${MODEL}`,
        content: { parts: [{ text: f.answer }] },
        taskType: "RETRIEVAL_DOCUMENT",
        title: f.question,
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
const existing = new Map((await sb("faqs?select=id,question,answer,embedding_set:embedding")).map((r) => [r.question, r]));
const changed = faqs.filter((f) => existing.get(f.question)?.answer !== f.answer || !existing.get(f.question)?.embedding_set);
console.log(`CSV ${faqs.length}개 / DB ${existing.size}개 / 추가·수정 ${changed.length}개`);

if (changed.length) {
  const vectors = await embed(changed);
  const rows = changed.map((f, i) => ({ question: f.question, answer: f.answer, embedding: JSON.stringify(vectors[i]) }));
  const saved = await sb("faqs?on_conflict=question", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates,return=representation" },
    body: JSON.stringify(rows),
  });
  for (const r of saved) console.log(`✔ ${existing.has(r.question) ? "수정" : "추가"}: [${r.id}] ${r.question}`);
}

const stale = [...existing.keys()].filter((q) => !faqs.some((f) => f.question === q));
if (stale.length) {
  if (PRUNE) {
    for (const q of stale) {
      await sb(`faqs?id=eq.${existing.get(q).id}`, { method: "DELETE" });
      console.log(`✖ 삭제: ${q}`);
    }
  } else {
    console.log(`CSV에 없는 질문 ${stale.length}개 (삭제하려면 --prune): ${stale.join(", ")}`);
  }
}
console.log("완료");
