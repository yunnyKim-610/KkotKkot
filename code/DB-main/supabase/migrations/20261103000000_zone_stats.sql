-- 센싱 모듈 통계 저장 (공정 단위 집계만)
-- 원칙: 개인별 기록, 태그 ID, 좌표, 영상은 이 DB에 저장하지 않는다.

create table if not exists public.devices (
  device_id   text primary key,
  token_hash  text not null,              -- 기기 토큰의 SHA-256 (원문 저장 금지)
  site        text,
  created_at  timestamptz not null default now(),
  revoked     boolean not null default false
);

create table if not exists public.zone_stats (
  id                 bigint generated always as identity primary key,
  device_id          text not null references public.devices(device_id),
  zone               text not null,
  period_start       timestamptz not null,
  period_end         timestamptz not null,
  observed_sec       real not null check (observed_sec >= 0),
  bad_sec_by_reason  jsonb not null default '{}'::jsonb,
  alerts             integer not null default 0 check (alerts >= 0),
  received_at        timestamptz not null default now(),
  check (period_end > period_start)
);

comment on table public.zone_stats is
  '공정 단위 자세 통계. 개인 식별 정보(태그 ID, 이름, 좌표, 영상)를 넣지 말 것.';

create index if not exists zone_stats_zone_period on public.zone_stats (zone, period_start);

-- 기기·익명 사용자는 직접 접근 불가. 쓰기는 Edge Function(ingest-stats)만, 읽기는 로그인한 관리자만.
alter table public.devices enable row level security;
alter table public.zone_stats enable row level security;

create policy "managers read zone stats" on public.zone_stats
  for select to authenticated using (true);
