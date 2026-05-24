-- Load Shape Lab — Supabase schema
-- Run this once in your Supabase SQL editor.
-- The publishable key in .env can read/write these tables if RLS is permissive.

-- ─── retailer_plans ──────────────────────────────────────────────────────
create table if not exists public.retailer_plans (
  id text primary key,
  retailer text not null,
  name text not null,
  plan_type text not null,                  -- 'TOU' | 'Flat' | 'Demand'
  state text,
  supply_charge numeric,
  peak_rate numeric,
  shoulder_rate numeric,
  offpeak_rate numeric,
  flat_rate numeric,
  demand_charge_per_kw_month numeric,
  tags jsonb default '[]'::jsonb,
  fragility text,
  source text,
  raw jsonb,                                -- raw CDR payload if synced from AER
  updated_at timestamptz default now()
);

-- ─── load_readings ───────────────────────────────────────────────────────
-- One row per meter × half-hour bucket. ~17,500 rows per meter per year.
create table if not exists public.load_readings (
  meter_id text not null,
  ts timestamptz not null,
  kw numeric not null,
  primary key (meter_id, ts)
);
create index if not exists idx_load_readings_meter_ts on public.load_readings (meter_id, ts desc);

-- ─── scenarios ───────────────────────────────────────────────────────────
-- Conversation transcripts + extracted profile + constraints document + result.
create table if not exists public.scenarios (
  id uuid primary key default gen_random_uuid(),
  meter_id text not null,
  messages jsonb not null default '[]'::jsonb,
  profile jsonb not null default '{}'::jsonb,
  constraints_doc jsonb not null default '{}'::jsonb,
  optimisation jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists idx_scenarios_meter on public.scenarios (meter_id, updated_at desc);

-- ─── RLS — permissive for the demo ───────────────────────────────────────
alter table public.retailer_plans enable row level security;
alter table public.load_readings enable row level security;
alter table public.scenarios     enable row level security;

drop policy if exists "public read retailer_plans" on public.retailer_plans;
drop policy if exists "public read load_readings"  on public.load_readings;
drop policy if exists "public read scenarios"      on public.scenarios;
drop policy if exists "public write retailer_plans" on public.retailer_plans;
drop policy if exists "public write load_readings"  on public.load_readings;
drop policy if exists "public write scenarios"      on public.scenarios;

create policy "public read retailer_plans"  on public.retailer_plans for select using (true);
create policy "public read load_readings"   on public.load_readings  for select using (true);
create policy "public read scenarios"       on public.scenarios      for select using (true);
create policy "public write retailer_plans" on public.retailer_plans for all    using (true) with check (true);
create policy "public write load_readings"  on public.load_readings  for all    using (true) with check (true);
create policy "public write scenarios"      on public.scenarios      for all    using (true) with check (true);
