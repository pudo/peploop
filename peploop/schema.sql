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

-- Reconciliation targets for round 2: one row per Wikidata position item a
-- free-text office title may resolve to. Nothing here is a filter. An
-- abolished office is the right answer for a tenure that ended before it, an
-- item typed as an occupation is worth offering labelled as one, and whether
-- an office confers political exposure is a question for a consumer, not for
-- a lookup table. Every ranking signal is nullable and filled by its own
-- step, so one that proves too expensive for a large country is left null
-- there rather than blocking the load.
CREATE TABLE IF NOT EXISTS position (
    qid               TEXT PRIMARY KEY,   -- canonical, after any redirect
    label             TEXT,               -- en, then mul, then whatever it has
    description       TEXT,
    country_qid       TEXT,               -- P17, first un-ended value
    jurisdiction_qid  TEXT,               -- P1001, first un-ended value
    jurisdiction_text TEXT,               -- names of the P1001 item, all languages
    body_qid          TEXT,               -- P361, or P2389 for an organisation post
    kinds             TEXT[],             -- labels of the item's own P279 parents
    sources           TEXT[],             -- which discovery queries found it
    not_office        BOOLEAN,            -- declared an occupation, a rank, a body
    inception         DATE,               -- P571
    abolished         DATE,               -- P576, P582 as fallback
    replaces          TEXT[],             -- P1365, one hop
    replaced_by       TEXT[],             -- P1366, one hop
    holders           INTEGER,            -- NULL is "not counted", never zero
    holders_at        TIMESTAMPTZ,
    instance_count    INTEGER,            -- items whose P31 is this
    subclass_count    INTEGER,            -- items whose P279 is this
    held_subclasses   INTEGER,            -- of those, the ones somebody holds
    scope_qualifier   TEXT,               -- the qualifier that makes it concrete
    redirected_from   TEXT[],             -- QIDs merged into this one
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS position_country_idx ON position (country_qid);

-- One row per name per language, rather than a TEXT[] of aliases: the article
-- says "primátor Brna" and the item's English label is "Mayor of Brno", so the
-- language a name is in is part of the answer to which name matched.
CREATE TABLE IF NOT EXISTS position_name (
    qid   TEXT NOT NULL REFERENCES position (qid) ON DELETE CASCADE,
    lang  TEXT NOT NULL,
    text  TEXT NOT NULL,
    alias BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (qid, lang, text)
);

-- Not indexed for search. The search reads `position.tsv`, one document per
-- item; this table is the per-language source that document is built from and
-- the answer to *which* name matched, which is looked up by qid afterwards.
CREATE INDEX IF NOT EXISTS position_name_qid_idx ON position_name (qid);

-- The `P31`/`P279` edges of everything the closure has walked, so a second
-- country does not re-fetch the class hierarchy above the first one. Seeds
-- are always re-read live; only the stable ancestry is served from here.
CREATE TABLE IF NOT EXISTS type_edge (
    qid        TEXT PRIMARY KEY,
    targets    TEXT[] NOT NULL DEFAULT '{}',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

-- What `apply` recorded about a written proposal: the item revision its edit
-- produced, and the statement it created or sharpened. A label or an alias is
-- not a statement and leaves `claim_guid` null.
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS applied_rev BIGINT;
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS claim_guid TEXT;

-- One searchable document per position, and the only index the search reads.
-- The loader writes `search_text` as a de-duplicated bag of content tokens,
-- each beside its six-character prefix, drawn from every name of the item and
-- of the items it names (jurisdiction, country, body, kind, succession). A
-- bag rather than prose: with every lexeme appearing once, `ts_rank(tsv, q, 0)`
-- over an OR-query sums to the number of query terms the document matched,
-- which is the ranking that measured best.
--
-- `simple` because the names are in every language the item has one in and
-- no stemmer is right for all of them; the prefixes are what stands in for
-- one. `to_tsvector(regconfig, text)` is IMMUTABLE, so the column can be
-- generated and the GIN index sits on it directly.
ALTER TABLE position ADD COLUMN IF NOT EXISTS search_text TEXT;
ALTER TABLE position ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(search_text, ''))) STORED;
CREATE INDEX IF NOT EXISTS position_tsv_idx ON position USING gin (tsv);
