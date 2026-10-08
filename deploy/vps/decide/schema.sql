-- The decide service's tables. Idempotent: PostgresStore.ensure_schema() runs this file at start-up.
create schema if not exists decide;

create table if not exists decide.suggestions (
  id bigserial primary key,
  qtype text not null default '',
  subject text not null default '',
  key char(64) not null unique,
  state text not null,                       -- display text, cut to 2,000 characters
  state_json jsonb not null,                 -- the full canonical state
  question json not null,                    -- json, not jsonb: jsonb reorders keys, and a Choice's option order matters
  answer jsonb,                              -- jsonb: a bool stays a bool, an int an int, a str a str
  confidence double precision not null default 0,
  probabilities jsonb not null default '{}', -- string-keyed
  model text not null default '',
  source text not null,
  status text not null default 'pending' check (status in ('pending','accepted','changed')),
  owner_answer jsonb,
  reviewed_at timestamptz,
  reviewed_by text,
  created_at timestamptz not null default now());

create index if not exists suggestions_owner on decide.suggestions (qtype, subject, reviewed_at desc);
create index if not exists suggestions_status on decide.suggestions (status, qtype);

create table if not exists decide.calls (
  id bigserial primary key,
  at timestamptz not null default now(),
  questions int not null,
  latency_ms int,
  input_tokens int,
  output_tokens int,
  model text,
  ok boolean not null,
  error_class text);
