-- peploop enrichment pipeline schema. Applied wholesale by peploop.db.init_schema();
-- every statement is idempotent, so there are no migrations.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Generic response cache for PetScan, SPARQL and search. Wikidata items and
-- Wikipedia articles are state and live in their own tables instead.
CREATE TABLE IF NOT EXISTS http_cache (
    url         TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    params      JSONB,
    body        TEXT NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (url, params_hash)
);

CREATE TABLE IF NOT EXISTS person (
    qid        TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'queued',
    error      TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS person_status_idx ON person (status);

-- Which seed categories admitted a person. A person found through six
-- categories is one `person` row and six rows here, so a wrong inclusion can
-- be traced back to the category that caused it.
CREATE TABLE IF NOT EXISTS membership (
    qid      TEXT NOT NULL,
    category TEXT NOT NULL,
    lang     TEXT NOT NULL,
    seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (qid, category, lang)
);

CREATE INDEX IF NOT EXISTS membership_category_idx ON membership (lang, category);

CREATE TABLE IF NOT EXISTS item (
    qid        TEXT PRIMARY KEY,
    lastrevid  BIGINT,
    json       JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS article (
    qid        TEXT NOT NULL,
    lang       TEXT NOT NULL,
    title      TEXT NOT NULL,
    rev_id     BIGINT,
    url        TEXT NOT NULL,
    text       TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (qid, lang)
);

CREATE INDEX IF NOT EXISTS article_lang_idx ON article (lang);

CREATE TABLE IF NOT EXISTS extraction (
    id            BIGSERIAL PRIMARY KEY,
    qid           TEXT NOT NULL,
    prompt_hash   TEXT NOT NULL,
    model         TEXT NOT NULL,
    article_langs TEXT[] NOT NULL DEFAULT '{}',
    request_json  JSONB,
    response_json JSONB,
    usage_json    JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS extraction_qid_idx ON extraction (qid);

CREATE TABLE IF NOT EXISTS proposal (
    id            BIGSERIAL PRIMARY KEY,
    person_qid    TEXT NOT NULL,
    property      TEXT NOT NULL,
    value         JSONB NOT NULL,
    qualifiers    JSONB,
    quote         TEXT,
    source_lang   TEXT,
    source_url    TEXT,
    source_rev    BIGINT,
    extraction_id BIGINT REFERENCES extraction (id),
    item_rev      BIGINT,
    status        TEXT NOT NULL,
    decided_by    TEXT,
    decided_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS proposal_person_idx ON proposal (person_qid);
CREATE INDEX IF NOT EXISTS proposal_status_idx ON proposal (status);

-- Reconciliation targets for round 2. `search_text` is label, aliases and
-- jurisdiction text joined by the loader: index expressions must be
-- IMMUTABLE, which array_to_string() over aliases is not.
CREATE TABLE IF NOT EXISTS candidate (
    qid               TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,
    label             TEXT,
    aliases           TEXT[] NOT NULL DEFAULT '{}',
    description       TEXT,
    country_qid       TEXT,
    jurisdiction_qid  TEXT,
    jurisdiction_text TEXT,
    search_text       TEXT,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS candidate_kind_idx ON candidate (kind, country_qid);
CREATE INDEX IF NOT EXISTS candidate_label_trgm_idx ON candidate USING gin (label gin_trgm_ops);
CREATE INDEX IF NOT EXISTS candidate_juris_trgm_idx ON candidate USING gin (jurisdiction_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS candidate_fts_idx ON candidate USING gin (to_tsvector('simple', coalesce(search_text, '')));

-- Added after the CREATE above, because schema.sql is applied wholesale to a
-- database that already holds a seeded run.
ALTER TABLE extraction ADD COLUMN IF NOT EXISTS bad_quotes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE extraction ADD COLUMN IF NOT EXISTS dropped_langs TEXT[] NOT NULL DEFAULT '{}';
-- The extraction key: `lang:rev_id` per article sent, sorted. Languages alone
-- would let a re-fetched article pass for the one that was read.
ALTER TABLE extraction ADD COLUMN IF NOT EXISTS article_revs TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS extraction_key_idx ON extraction (qid, prompt_hash);

-- Records what a human made of a proposal. Nothing writes it yet; the table
-- exists from round 1 so the review command has no back-fill to do.
CREATE TABLE IF NOT EXISTS verdict (
    id          BIGSERIAL PRIMARY KEY,
    proposal_id BIGINT NOT NULL REFERENCES proposal (id) ON DELETE CASCADE,
    decision    TEXT NOT NULL CHECK (decision IN ('accept', 'reject')),
    reason      TEXT CHECK (reason IN ('wrong_value', 'wrong_precision', 'quote_unsupported',
                 'wrong_person', 'already_recorded', 'rule_missing', 'source_wrong', 'other')),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS verdict_proposal_idx ON verdict (proposal_id);

ALTER TABLE proposal ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS proposal_property_idx ON proposal (property, status);
