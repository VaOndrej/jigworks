-- Hub schema. Idempotent: applied on the first request of every cold start.
CREATE TABLE IF NOT EXISTS meta (
  key   text PRIMARY KEY,
  value text NOT NULL
);

CREATE TABLE IF NOT EXISTS workflows (
  id          text PRIMARY KEY,
  name        text NOT NULL,
  description text,
  owner_email text,
  source      text NOT NULL DEFAULT 'hub',
  updated_at  timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
  workflow_id     text PRIMARY KEY REFERENCES workflows(id) ON DELETE CASCADE,
  files           jsonb NOT NULL,          -- [{path, content}] sorted by path
  files_hash      text NOT NULL,
  base_release_id text,
  updated_at      timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS releases (
  id           text PRIMARY KEY,
  workflow_id  text NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  version      text NOT NULL,
  digest       text NOT NULL,
  published_at timestamptz NOT NULL,
  published_by text,
  notes        text,
  manifest     jsonb,
  graph        jsonb,
  bundle_bytes integer NOT NULL,
  bundle_url   text,                       -- Blob URL; NULL when the bytes live in bundles
  files_hash   text,
  UNIQUE (workflow_id, version)
);

CREATE TABLE IF NOT EXISTS bundles (       -- local store (no Blob token)
  release_id text PRIMARY KEY REFERENCES releases(id) ON DELETE CASCADE,
  data       bytea NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
  workflow_id text NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  channel     text NOT NULL,
  release_id  text NOT NULL REFERENCES releases(id),
  updated_at  timestamptz NOT NULL,
  PRIMARY KEY (workflow_id, channel)
);

CREATE TABLE IF NOT EXISTS validations (   -- cache: one result per draft content
  workflow_id text NOT NULL,
  files_hash  text NOT NULL,
  result      jsonb NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workflow_id, files_hash)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id      text PRIMARY KEY,
  workflow_id text NOT NULL,
  release     text NOT NULL,
  status      text NOT NULL,
  started_at  timestamptz NOT NULL,
  updated_at  timestamptz,
  created     jsonb NOT NULL,              -- RunCreate as registered
  summary     jsonb NOT NULL,              -- RunSummary projected from the events (without cost)
  audit       jsonb NOT NULL               -- AuditRecord projected from the events
);
CREATE INDEX IF NOT EXISTS runs_by_start ON runs (started_at DESC, run_id DESC);

CREATE TABLE IF NOT EXISTS events (
  run_id      text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  seq         integer NOT NULL,
  kind        text NOT NULL,
  at          timestamptz NOT NULL,
  body        jsonb NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS usage (         -- raw tokens per call (design.md §8)
  run_id       text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  seq          integer NOT NULL,
  node         text NOT NULL,
  attempt      integer NOT NULL,
  model        text NOT NULL,
  adapter      text NOT NULL,
  input        bigint NOT NULL,
  output       bigint NOT NULL,
  cache_write  bigint NOT NULL,
  cache_read   bigint NOT NULL,
  cli_cost_usd double precision,
  at           timestamptz NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS prices (        -- price list with validity
  model          text NOT NULL,
  token_type     text NOT NULL,
  price_per_mtok double precision NOT NULL,
  valid_from     timestamptz NOT NULL,
  PRIMARY KEY (model, token_type, valid_from)
);

CREATE TABLE IF NOT EXISTS human_deltas (  -- PLANNED: sample data only
  run_id  text PRIMARY KEY,
  release text NOT NULL,
  body    jsonb NOT NULL
);
