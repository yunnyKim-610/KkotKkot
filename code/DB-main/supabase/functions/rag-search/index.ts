// RAG 검색: 질문 임베딩 → match_chunks(문서 조각)·match_faqs(FAQ)로 관련 내용 검색 → Gemini로 답변 생성
// 홈페이지 공개 챗봇용 — 로그인 없이 누구나 호출하며, DB의 모든 문서(꼿꼿 AI 소개 자료)를 검색
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const GEMINI_API_KEY = Deno.env.get("GEMINI_API_KEY") ?? "";
const EMBED_MODEL = "gemini-embedding-001";
const DIM = 768;
// 첫 모델이 혼잡(503)·한도 초과(429)면 다음 모델로 재시도
// flash-lite가 문서 기반 답변에 충분히 정확하고 약 1초로 가장 빠름 (flash-latest는 3~15초, gemini-2.5-flash는 신규 사용자 404)
const GEN_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest"];
const MATCH_THRESHOLD = 0.5;
// 가장 비슷한 chunk가 이 값보다 낮으면 홈페이지와 무관한 질문으로 보고 답변 생성(Gemini) 없이 거절해 토큰 절약
// 측정값: 관련 질문 0.64~0.77, 무관한 질문(날씨·주가·인사 등) 0.48~0.61
const RELEVANCE_THRESHOLD = 0.63;
const OFF_TOPIC_ANSWER =
  "죄송해요, 저는 꼿꼿 AI 홈페이지 내용(자세 판정 기준, 개인정보 처리, 도입 비용, AI 모델 등)에 대해서만 답할 수 있어요.";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
// 검색 결과 한 건: 문서 조각(doc)이면 title=문서 제목, FAQ(faq)면 title=질문·content=답변
type Source = { type: "doc" | "faq"; id: number; title: string; content: string; similarity: number };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

const gemini = (path: string, body: unknown) =>
  fetch(`https://generativelanguage.googleapis.com/v1beta/models/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY },
    body: JSON.stringify(body),
  });

async function embedQuery(text: string): Promise<number[]> {
  const body = { content: { parts: [{ text }] }, taskType: "RETRIEVAL_QUERY", outputDimensionality: DIM };
  // 무료 한도(429)·일시 오류(503)면 1초, 2초 쉬고 최대 2번 재시도
  let res = await gemini(`${EMBED_MODEL}:embedContent`, body);
  for (let i = 1; i <= 2 && [429, 503].includes(res.status); i++) {
    await new Promise((r) => setTimeout(r, i * 1000));
    res = await gemini(`${EMBED_MODEL}:embedContent`, body);
  }
  if (!res.ok) throw new Error(`임베딩 실패 (${res.status}): ${await res.text()}`);
  const values: number[] = (await res.json()).embedding.values;
  const norm = Math.hypot(...values) || 1;
  return values.map((v) => v / norm);
}

async function generateAnswer(question: string, context: string): Promise<{ answer: string; model: string }> {
  const body = {
    systemInstruction: {
      parts: [{
        text:
          "당신은 자세 교정 피지컬 AI 제품 '꼿꼿 AI'의 홈페이지 안내 도우미입니다. 반드시 제공된 [참고 문서]의 내용만 근거로 한국어로 답변하세요. " +
          "질문이 문서와 다른 표현을 써도 뜻이 같으면 그 문서로 답하세요(예: 거북목 → 목 숙임, 구부정한 자세 → 허리 구부림·어깨 웅크림, 가격 → 도입 비용). " +
          "문서에 관련 내용이 일부라도 있으면 그 범위에서 답하고, 전혀 없을 때만 '제공된 문서에서 관련 내용을 찾을 수 없습니다.'라고 답하세요. " +
          `꼿꼿 AI와 무관한 질문(일상 대화, 다른 주제, 코딩·숙제 도움 등)에는 다른 말 없이 '${OFF_TOPIC_ANSWER}'라고만 답하세요. ` +
          "답변은 핵심만 3~5문장 이내로 간결하게 쓰고, 사용한 문서 번호를 [1], [2]처럼 문장 끝에 표시하세요. " +
          "각도, 시간, 금액, 비율 같은 수치는 문서 그대로 정확히 인용하세요.",
      }],
    },
    contents: [{ role: "user", parts: [{ text: `[참고 문서]\n${context}\n\n[질문]\n${question}` }] }],
    // 생각(thinking)을 최소로 해 지연과 토큰을 줄임 (두 모델 모두 thinkingLevel "low" 지원, "minimal"은 flash-latest가 거부)
    generationConfig: { temperature: 0.2, maxOutputTokens: 1024, thinkingConfig: { thinkingLevel: "low" } },
  };

  let lastError = "";
  for (const model of GEN_MODELS) {
    const res = await gemini(`${model}:generateContent`, body);
    if (res.ok) {
      const data = await res.json();
      const parts = data.candidates?.[0]?.content?.parts ?? [];
      const answer = parts.filter((p: { thought?: boolean }) => !p.thought).map((p: { text?: string }) => p.text ?? "").join("").trim();
      return { answer: answer || "답변을 생성하지 못했습니다.", model };
    }
    lastError = `${model} (${res.status}): ${await res.text()}`;
    if (![429, 500, 503, 404].includes(res.status)) break;
  }
  throw new Error(`답변 생성 실패 - ${lastError}`);
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST만 지원합니다." }, 405);

  try {
    if (!GEMINI_API_KEY) return json({ error: "서버에 GEMINI_API_KEY 비밀값이 설정되지 않았습니다." }, 500);

    const { question, matchCount = 5 } = await req.json().catch(() => ({}));
    if (typeof question !== "string" || !question.trim()) return json({ error: "질문을 입력하세요." }, 400);
    if (question.length > 500) return json({ error: "질문은 500자 이하로 입력하세요." }, 400);

    // 문서에 소유자(user_id)가 없어 RLS로는 보이지 않으므로 service_role로 검색 (결과는 검색된 chunk만 반환)
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const embedding = await embedQuery(question.trim());
    const count = Math.min(Math.max(Number(matchCount) || 5, 1), 10);
    const params = { query_embedding: JSON.stringify(embedding), match_count: count, match_threshold: MATCH_THRESHOLD };
    // 긴 문서 조각(chunks)과 FAQ(faqs)를 함께 검색한 뒤 유사도 순으로 합쳐 상위 count개만 사용
    const [docRes, faqRes] = await Promise.all([admin.rpc("match_chunks", params), admin.rpc("match_faqs", params)]);
    if (docRes.error) throw new Error(`문서 검색 실패: ${docRes.error.message}`);
    if (faqRes.error) throw new Error(`FAQ 검색 실패: ${faqRes.error.message}`);
    const sources: Source[] = [
      ...(docRes.data ?? []).map((s: { id: number; title: string; content: string; similarity: number }) =>
        ({ type: "doc" as const, id: s.id, title: s.title, content: s.content, similarity: s.similarity })),
      ...(faqRes.data ?? []).map((s: { id: number; question: string; answer: string; similarity: number }) =>
        ({ type: "faq" as const, id: s.id, title: s.question, content: s.answer, similarity: s.similarity })),
    ].sort((a, b) => b.similarity - a.similarity).slice(0, count);

    if (!sources.length || sources[0].similarity < RELEVANCE_THRESHOLD) {
      return json({ answer: OFF_TOPIC_ANSWER, sources: [], model: null });
    }

    const context = sources
      .map((s, i) => s.type === "faq" ? `[${i + 1}] (FAQ) Q: ${s.title}\nA: ${s.content}` : `[${i + 1}] (${s.title}) ${s.content}`)
      .join("\n\n");
    const { answer, model } = await generateAnswer(question.trim(), context);

    return json({ answer, model, sources });
  } catch (e) {
    console.error(e);
    return json({ error: e instanceof Error ? e.message : String(e) }, 500);
  }
});
