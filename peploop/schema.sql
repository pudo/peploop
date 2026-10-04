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
    -- Free text for a status that needs one: the exception a fetch died on,
    -- and the dates a person was set aside on before any article was read.
    error      TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS person_status_idx ON person (status);

-- Which country's run queued a person, stamped by `seed` from its own flag.
-- Added after the CREATE above, because schema.sql is applied wholesale to a
-- database that already holds a seeded run. It scopes a command's selection
-- and nothing else: the pipeline reasons about a person, never about a
-- country, and a person queued by two runs keeps the first one's stamp.
ALTER TABLE person ADD COLUMN IF NOT EXISTS country TEXT;
CREATE INDEX IF NOT EXISTS person_country_idx ON person (country, status);

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
                 'wrong_person', 'already_recorded', 'rule_missing', 'source_wrong',
                 'wrong_office', 'other')),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS verdict_proposal_idx ON verdict (proposal_id);

-- The CHECK above only reaches a database that does not have the table yet, so
-- the closed set is restated here for one that does. `wrong_office` says the
-- office was placed on the wrong item, which is the one thing a P39 row can be
-- wrong about that no other reason names.
ALTER TABLE verdict DROP CONSTRAINT IF EXISTS verdict_reason_check;
ALTER TABLE verdict ADD CONSTRAINT verdict_reason_check CHECK (reason IN (
    'wrong_value', 'wrong_precision', 'quote_unsupported', 'wrong_person',
    'already_recorded', 'rule_missing', 'source_wrong', 'wrong_office', 'other'));

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

-- Two more ranking signals, added after the CREATE above because schema.sql is
-- applied wholesale to a database that already holds a loaded run. Both are
-- nullable for the same reason every other signal is: null means nobody has
-- counted, never that the count came back zero.
--
-- `holders_by_country` is a map of state QID to how many of that state's
-- citizens hold the office, rather than one integer, because the same item is
-- a country's own convention in one place and a handful of misfilings in the
-- next -- which is the whole question the abstractness tags turn on.
ALTER TABLE position ADD COLUMN IF NOT EXISTS holders_by_country JSONB;
-- An ambassadorship, from the cached type closure. An inbound mission carries
-- the *receiving* state's P1001, so a country's table is full of other
-- countries' embassies to it; they are tagged and never dropped.
ALTER TABLE position ADD COLUMN IF NOT EXISTS diplomatic BOOLEAN;
-- Which state sends a diplomatic post: its "ambassador of <state>" class's
-- P17, else its own P137. Kept apart from country_qid, which stays the item's
-- P17 -- the receiver on a bilateral post -- because that is what the
-- inbound test and every per-state listing of the table read. NULL on
-- anything not diplomatic, and on a post that names no sender.
ALTER TABLE position ADD COLUMN IF NOT EXISTS sender_qid TEXT;

-- What the second turn made of one office mention: the model's verdict and the
-- mechanical gate's ruling on it, keyed to the exact extraction that produced
-- the mention (`mention_idx` indexes `response_json->'positions'`). This is the
-- ledger a re-run resumes from -- a mention answered under this prompt hash is
-- never asked again -- and a prompt edit or a rendering change re-asks everyone.
-- A row whose `qid` is null is the creation queue: the office was named and
-- could not be placed, and `kind`/`chosen` say how the shortlist misled.
CREATE TABLE IF NOT EXISTS resolution (
    id            BIGSERIAL PRIMARY KEY,
    extraction_id BIGINT NOT NULL REFERENCES extraction (id) ON DELETE CASCADE,
    mention_idx   INTEGER NOT NULL,
    title         TEXT NOT NULL,
    jurisdiction  TEXT,
    start_text    TEXT,               -- the tenure as round one wrote it
    end_text      TEXT,
    lang          TEXT,
    state_qid     TEXT,               -- whose holder counts the ranking read
    prompt_hash   TEXT NOT NULL,
    render_version INTEGER NOT NULL,   -- reconcile.RENDER_VERSION: what else the model saw
    model         TEXT NOT NULL,
    shortlist     TEXT[] NOT NULL DEFAULT '{}',  -- every QID the model saw, in rank order
    chosen        TEXT,               -- the model's pick, kept even when vetoed
    qid           TEXT,               -- the applied pick; null is a refusal or a veto
    kind          TEXT NOT NULL,
    confidence    TEXT NOT NULL,
    evidence      TEXT,
    reason        TEXT,
    veto          TEXT,
    usage_json    JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS resolution_qid_idx ON resolution (qid);

-- BEGIN resolution.reopened_for
-- A verdict re-asked because the item its office was missing has since been
-- minted. `reopened_for` names that item, and is '' on every ordinary verdict;
-- it is part of the key, so a re-ask under the same prompt and rendering is a
-- new row beside the original rather than a collision with it, and the newest
-- row per mention is the one `propose.placements` reads. The original stays:
-- what the model said before the item existed is history, not an error.
ALTER TABLE resolution ADD COLUMN IF NOT EXISTS reopened_for TEXT NOT NULL DEFAULT '';
ALTER TABLE resolution
    DROP CONSTRAINT IF EXISTS resolution_extraction_id_mention_idx_prompt_hash_render_ver_key;
CREATE UNIQUE INDEX IF NOT EXISTS resolution_key_idx ON resolution
    (extraction_id, mention_idx, prompt_hash, render_version, reopened_for);
-- END resolution.reopened_for

-- Which verdict placed a P39 proposal on its item. The review screen reads it
-- to show the office as the article named it and the shortlist the model was
-- offered, because whether a match is right cannot be judged from the QID it
-- landed on. Null on every proposal that is not a position.
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS resolution_id BIGINT
    REFERENCES resolution (id) ON DELETE SET NULL;

-- What the policy decided and what `propose` had said before it did. A row's
-- `status` is `accepted`, `skipped` or `pending` once the policy has read it,
-- with the rule in `decided_by` as `policy:<rule>`; `proposed_status` keeps the
-- `new` or `refine` it started as, because the rules read it and a re-run
-- must see what `propose` saw. A human's ruling sets `decided_by` to their
-- name instead, and the policy never touches such a row again.
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS proposed_status TEXT;

-- What `apply` sent, beside what it produced: the revision the edit was made
-- against and the EditGroups batch it went out in. Together with `applied_rev`
-- they are the diff link an audit reads, and the batch a bad run is reverted by.
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS base_rev BIGINT;
ALTER TABLE proposal ADD COLUMN IF NOT EXISTS applied_batch TEXT;

-- What the verifier made of one proposed edit, keyed on what was asked rather
-- than on the proposal row: `proposal_key` hashes the person, the property,
-- the value, the qualifiers and the (language, revision) of every source, so
-- a re-propose that replaces the row finds its verdict again and a re-fetched
-- article does not. `proposal_id` is the row it was asked for, kept for the
-- audit and not relied on. A prompt edit or a rendering change re-asks.
CREATE TABLE IF NOT EXISTS verification (
    id             BIGSERIAL PRIMARY KEY,
    proposal_key   TEXT NOT NULL,
    proposal_id    BIGINT,
    person_qid     TEXT NOT NULL,
    property       TEXT NOT NULL,
    prompt_hash    TEXT NOT NULL,
    render_version INTEGER NOT NULL,
    model          TEXT NOT NULL,
    verdict        TEXT NOT NULL,
    confidence     TEXT NOT NULL,
    evidence       TEXT,
    reason         TEXT,
    usage_json     JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (proposal_key, prompt_hash, render_version, model)
);

CREATE INDEX IF NOT EXISTS verification_key_idx ON verification (proposal_key);
CREATE INDEX IF NOT EXISTS verification_person_idx ON verification (person_qid);

-- The year an office's earliest recorded holder took it up, and when that was
-- asked. An item with no inception cannot earn `date-conflict`, and a tenure
-- generations before anyone Wikidata records in the office is the wrong item
-- or the wrong era; the policy skips it. Null year with a timestamp means
-- asked and nobody is dated, which is silence rather than a number.
ALTER TABLE position ADD COLUMN IF NOT EXISTS first_held_year INTEGER;
ALTER TABLE position ADD COLUMN IF NOT EXISTS first_held_at TIMESTAMPTZ;

-- The year the polity an office is scoped to came into being: `P571` of the
-- `P1001` target, or of the `P17` one. A tenure that predates the polity is
-- another era's office under a similar name.
ALTER TABLE position ADD COLUMN IF NOT EXISTS polity_inception_year INTEGER;
ALTER TABLE position ADD COLUMN IF NOT EXISTS polity_inception_at TIMESTAMPTZ;

-- The item's own `P31` and `P279` targets, as QIDs: what kind of office it
-- says it is. `kinds` keeps only the labels of the `P279` half, and an office
-- typed `P31 = interior minister` with no `P279` has its kind on the other
-- half. Null is "not read yet"; an empty array is an item with no type.
ALTER TABLE position ADD COLUMN IF NOT EXISTS kind_qids TEXT[];

-- BEGIN mint
-- The minting stage: offices reconciliation could not place, turned into items.
-- `mint_call` is the LLM ledger of both passes, keyed by what was shown, so a
-- prompt edit or a rendering change re-asks and an unchanged rerun pays nothing.
CREATE TABLE IF NOT EXISTS mint_call (
    id             BIGSERIAL PRIMARY KEY,
    pass           TEXT NOT NULL CHECK (pass IN ('categorize', 'verify')),
    country        TEXT NOT NULL,
    content_key    TEXT NOT NULL,      -- hash of the rendered request body
    prompt_hash    TEXT NOT NULL,
    render_version INTEGER NOT NULL,
    model          TEXT NOT NULL,
    request_json   JSONB,
    response_json  JSONB,
    usage_json     JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pass, content_key, prompt_hash, render_version, model)
);

-- One office the stage may mint, from the reconcile misses, the census or
-- both. `ref` is stable across reruns (a group key or a census key), so a
-- re-categorize updates the row it made rather than adding a second one.
-- `status` and `rule` are the disposition; a skip names the rule that decided
-- it, and nothing waits on a human. The intent fields make a create
-- crash-safe: a row left in `creating` is resolved by its tag, not retried.
CREATE TABLE IF NOT EXISTS office_candidate (
    id                BIGSERIAL PRIMARY KEY,
    country           TEXT NOT NULL,
    ref               TEXT NOT NULL,
    origin            TEXT[] NOT NULL DEFAULT '{}',   -- reconcile, census
    census_key        TEXT,
    institution_class TEXT,
    archetype         TEXT,
    single_seat       BOOLEAN NOT NULL DEFAULT false,
    draft             JSONB,           -- what categorize proposed
    corrections       JSONB,           -- what verify changed
    spec              JSONB,           -- the shape the guard read
    data              JSONB,           -- the wbeditentity payload
    holders           INTEGER,         -- distinct people attested
    current_holders   INTEGER,
    source_url        TEXT,
    source_checked_at TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'queued',
    rule              TEXT,
    problems          TEXT[] NOT NULL DEFAULT '{}',
    categorize_call   BIGINT REFERENCES mint_call (id),
    verify_call       BIGINT REFERENCES mint_call (id),
    qid               TEXT,            -- created or found
    created_rev       BIGINT,
    batch             TEXT,            -- the EditGroups batch it went out in
    intent_at         TIMESTAMPTZ,
    intent_tag        TEXT,
    decided_by        TEXT,
    decided_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (country, ref)
);

CREATE INDEX IF NOT EXISTS office_candidate_status_idx ON office_candidate (country, status);

-- Which mentions a candidate was clustered from: the floor counts them, and
-- `feed` reopens exactly these once the item exists, never a mention that
-- merely shares a word with it.
CREATE TABLE IF NOT EXISTS office_attestation (
    candidate_id  BIGINT NOT NULL REFERENCES office_candidate (id) ON DELETE CASCADE,
    resolution_id BIGINT REFERENCES resolution (id) ON DELETE SET NULL,
    extraction_id BIGINT NOT NULL,
    mention_idx   INTEGER NOT NULL,
    person_qid    TEXT NOT NULL,
    current       BOOLEAN NOT NULL DEFAULT false,
    retrieved     BOOLEAN,             -- would the new item reach its shortlist
    reopened_id   BIGINT REFERENCES resolution (id) ON DELETE SET NULL,
    PRIMARY KEY (candidate_id, extraction_id, mention_idx)
);

-- A group categorize gave no office, with its reason, so every group has a
-- disposition and the funnel adds up.
CREATE TABLE IF NOT EXISTS office_unassigned (
    country         TEXT NOT NULL,
    group_key       TEXT NOT NULL,
    reason          TEXT,
    categorize_call BIGINT REFERENCES mint_call (id),
    PRIMARY KEY (country, group_key)
);
-- END mint

-- BEGIN title_en
-- The English office name a small model writes for a title, as a second search
-- channel beside the lexical one. Cached because the model is not
-- deterministic (two runs agreed exactly on two thirds of titles), so a
-- shortlist built from it is reproducible only if the answer is asked once and
-- read back: `reconcile.shortlist_hits` reads this table and never calls the
-- model. Keyed by what was sent -- the state the request names, the article
-- language, the folded title and jurisdiction -- plus the prompt hash and the
-- model, so a prompt edit re-asks everything and nothing else does.
CREATE TABLE IF NOT EXISTS title_en_call (
    id          BIGSERIAL PRIMARY KEY,
    prompt_hash TEXT NOT NULL,
    model       TEXT NOT NULL,
    titles      INTEGER NOT NULL,      -- how many were sent
    answered    INTEGER NOT NULL,      -- how many came back usable
    usage_json  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS title_en (
    state_qid        TEXT NOT NULL,    -- '' when no state was given
    lang             TEXT NOT NULL,    -- '' when unknown
    title_key        TEXT NOT NULL,    -- titles.fold_key(title)
    jurisdiction_key TEXT NOT NULL,    -- titles.fold_key(jurisdiction), '' for none
    prompt_hash      TEXT NOT NULL,
    model            TEXT NOT NULL,
    title            TEXT NOT NULL,    -- as first sent
    jurisdiction     TEXT,
    english          TEXT NOT NULL,
    call_id          BIGINT REFERENCES title_en_call (id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (state_qid, lang, title_key, jurisdiction_key, prompt_hash, model)
);

-- The same pass's English name for a position with no `en` or `mul` label,
-- folded into `search_text` so an English title can reach it. A local search
-- aid only: it is not a `position_name` row, so it is never shown to the
-- reconcile model as a name the item carries, and nothing that writes to
-- Wikidata reads it.
ALTER TABLE position ADD COLUMN IF NOT EXISTS title_en TEXT;
-- END title_en
