-- FAQ를 documents/chunks에서 분리해 faqs 테이블로 옮김
--   - documents/chunks: 긴 문서(쪼개서 저장)
--   - faqs: 질문·답변 한 쌍(쪼개지 않음)
-- Supabase 대시보드 > SQL Editor에서 이 파일 전체를 실행하세요. 여러 번 실행해도 안전합니다.

-- 1. faqs 테이블
create table if not exists public.faqs (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  question text not null unique,
  answer text not null,
  embedding extensions.vector(768)
);

-- 홈페이지에 공개된 내용이라 누구나 읽기 가능, 쓰기는 service_role만
alter table public.faqs enable row level security;
drop policy if exists "faqs are readable by everyone" on public.faqs;
create policy "faqs are readable by everyone" on public.faqs for select to anon, authenticated using (true);

-- 2. 기존 FAQ 문서("FAQ: 질문" 제목)를 faqs로 복사 (임베딩도 그대로 재사용)
insert into public.faqs (question, answer, embedding, created_at)
select regexp_replace(d.title, '^FAQ:\s*', ''), c.content, c.embedding, d.created_at
from public.documents d
join public.chunks c on c.document_id = d.id
where d.title like 'FAQ:%'
on conflict (question) do nothing;

-- 3. FAQ 검색 함수 (match_chunks와 같은 방식: 코사인 유사도)
create or replace function public.match_faqs(
  query_embedding extensions.vector(768),
  match_count int default 5,
  match_threshold float default 0.5
)
returns table (id bigint, question text, answer text, similarity float)
language sql stable
set search_path = public, extensions
as $$
  select f.id, f.question, f.answer, 1 - (f.embedding <=> query_embedding) as similarity
  from public.faqs f
  where f.embedding is not null
    and 1 - (f.embedding <=> query_embedding) > match_threshold
  order by f.embedding <=> query_embedding
  limit match_count;
$$;

-- 기존 FAQ 문서(documents/chunks)는 rag-search 함수를 새 버전으로 배포한 뒤 삭제합니다.
-- (먼저 지우면 배포 전까지 챗봇이 FAQ를 못 찾음)
--   delete from public.chunks where document_id in (select id from public.documents where title like 'FAQ:%');
--   delete from public.documents where title like 'FAQ:%';
