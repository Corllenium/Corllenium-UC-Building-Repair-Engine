-- UC Model Fixer: a dedicated schema in the UC Supabase project, separate from UC-BCF's public tables.
-- Nothing here touches public.*. RLS is on for every table, with no policies, so neither the anon nor the
-- authenticated key can read or write. Only server-side access (the service role, or a direct database
-- connection) can reach them.

create schema if not exists uc_fixer;
comment on schema uc_fixer is 'UC Model Fixer (Corllenium UC Building Repair System): models, versions, the campus map, census error maps, Validator verdicts and the owner''s reviews. Separate from UC-BCF''s public schema.';

-- 1. The dashboard's own tables (mirror of the local Postgres the fixer API uses today) -------------
create table uc_fixer.models (
  id            bigint generated always as identity primary key,
  name          text not null unique,
  source_file   text not null,
  created_at    timestamptz not null default now()
);

create table uc_fixer.model_versions (
  id              bigint generated always as identity primary key,
  model_id        bigint not null references uc_fixer.models(id) on delete cascade,
  kind            text not null check (kind in ('snapshot', 'fixed')),
  sha256          text not null,
  asset_sha256    text,
  tri_count       integer not null,
  flat_materials  jsonb,
  created_at      timestamptz not null default now()
);

create table uc_fixer.version_assets (
  id          bigint generated always as identity primary key,
  version_id  bigint not null references uc_fixer.model_versions(id) on delete cascade,
  kind        text not null,
  path        text not null,             -- relative to the fixer's data directory
  sha256      text,
  size_bytes  bigint
);

create table uc_fixer.fix_runs (
  id                bigint generated always as identity primary key,
  version_id        bigint not null references uc_fixer.model_versions(id) on delete cascade,
  fixed_version_id  bigint references uc_fixer.model_versions(id),
  status            text not null,
  report            jsonb,
  started_at        timestamptz not null default now(),
  finished_at       timestamptz
);

-- 2. The campus: units from the inventory (P0-10), confirmed by the owner (P0-13) --------------------
create table uc_fixer.campus_units (
  unit                text primary key,               -- e.g. 'CHTM-L05'
  building            text not null,
  level               text,                            -- 'L05', or null for elements and site pieces
  type                text not null check (type in ('floor', 'element', 'site')),
  members             jsonb not null,                  -- groups, path ids, snapshot sha256, z ranges
  tris                integer not null,
  base_in             double precision,
  top_in              double precision,
  neighbours          jsonb,
  flags               jsonb,
  confirmed_by_owner  boolean not null default false,
  updated_at          timestamptz not null default now()
);

-- 3. The census: every floor's error map (P0-12) -----------------------------------------------------
create table uc_fixer.census_runs (
  id            bigint generated always as identity primary key,
  engine_commit text not null,
  units_ok      integer not null,
  units_error   integer not null,
  units_timeout integer not null,
  wall_seconds  double precision,
  created_at    timestamptz not null default now()
);

create table uc_fixer.census_units (
  run_id         bigint not null references uc_fixer.census_runs(id) on delete cascade,
  snapshot       text not null,              -- the frozen snapshot folder name
  unit           text,                       -- campus_units.unit, once the map is confirmed
  building       text not null,
  status         text not null check (status in ('ok', 'error', 'timeout')),
  triangles      integer,
  counts         jsonb,                      -- the 7 error kinds, in faces
  flicker_split  jsonb,                      -- pairs by look and by winding
  fix_plan       jsonb,                      -- [{engine, kinds, count, unit}] in pipeline order
  errors_path    text,                       -- the unit's whole error file (data/campus/errors/...)
  seconds        double precision,
  peak_mb        double precision,
  primary key (run_id, snapshot)
);

-- 4. The Validator's verdicts (P0-15) and the owner's floor reviews ----------------------------------
create table uc_fixer.validations (
  id              bigint generated always as identity primary key,
  unit            text not null,
  before_sha256   text not null,
  after_sha256    text not null,
  engine_commit   text not null,
  verdict         text not null check (verdict in ('PASS', 'FAIL')),
  checks          jsonb not null,            -- textures / problems / nothing_deleted
  sites           jsonb,
  evidence_path   text,
  created_at      timestamptz not null default now()
);

create table uc_fixer.floor_reviews (
  id             bigint generated always as identity primary key,
  validation_id  bigint not null references uc_fixer.validations(id) on delete cascade,
  decision       text not null check (decision in ('accept', 'reject')),
  spot_marks     jsonb,                      -- "this spot is wrong" marks; each becomes a test fixture
  note           text,
  reviewed_by    text not null,
  reviewed_at    timestamptz not null default now()
);

-- 5. The owner's decisions (the P0-13 sheet) and the check-2 targets --------------------------------
create table uc_fixer.owner_decisions (
  key         text primary key,              -- e.g. 'scienceA-obj1', 'targets', 'tint-groups'
  question    text not null,
  answer      jsonb not null,
  decided_at  timestamptz not null default now()
);

create index on uc_fixer.model_versions (model_id);
create index on uc_fixer.version_assets (version_id);
create index on uc_fixer.census_units (building);
create index on uc_fixer.validations (unit);

-- RLS on everywhere, no policies: server-side access only.
alter table uc_fixer.models          enable row level security;
alter table uc_fixer.model_versions  enable row level security;
alter table uc_fixer.version_assets  enable row level security;
alter table uc_fixer.fix_runs        enable row level security;
alter table uc_fixer.campus_units    enable row level security;
alter table uc_fixer.census_runs     enable row level security;
alter table uc_fixer.census_units    enable row level security;
alter table uc_fixer.validations     enable row level security;
alter table uc_fixer.floor_reviews   enable row level security;
alter table uc_fixer.owner_decisions enable row level security;
