-- peptree's own tables. They live in peploop's database and never touch its tables.

-- Class-level reads that are not "what does Wikidata hold now": the place
-- gazetteer, class labels, Wikipedia leads, the closure's upper edges.
CREATE TABLE IF NOT EXISTS ptree_cache (
    key text PRIMARY KEY,
    body jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ptree_type_edge (
    qid text PRIMARY KEY,
    targets text[] NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

-- One row per item a load found; `dropped` is the filter's reason, NULL when kept.
CREATE TABLE IF NOT EXISTS ptree_item (
    country text NOT NULL,
    qid text NOT NULL,
    lanes text[] NOT NULL,
    lastrevid bigint,
    entity jsonb NOT NULL,
    holders integer NOT NULL DEFAULT 0,
    holder_countries jsonb NOT NULL DEFAULT '{}',
    kind text,
    dropped text,
    drop_detail text,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (country, qid)
);

-- What each kept item is missing. `category` is set on a class-fix gap.
CREATE TABLE IF NOT EXISTS ptree_gap (
    country text NOT NULL,
    qid text NOT NULL,
    prop text NOT NULL,
    gap text NOT NULL,
    category text,
    PRIMARY KEY (country, qid, prop)
);

-- The answer ledger: one row per distinct request (content key), so a re-run
-- pays only for what changed.
CREATE TABLE IF NOT EXISTS ptree_call (
    key text PRIMARY KEY,
    country text NOT NULL,
    qid text NOT NULL,
    model text NOT NULL,
    prompt_hash text NOT NULL,
    request jsonb NOT NULL,
    answer jsonb NOT NULL,
    usage jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Every slot ends apply or skip, with the rule that decided it.
CREATE TABLE IF NOT EXISTS ptree_decision (
    country text NOT NULL,
    qid text NOT NULL,
    prop text NOT NULL,
    value text,
    disposition text NOT NULL,
    rule text NOT NULL,
    channels text[] NOT NULL DEFAULT '{}',
    confidence text,
    evidence text,
    source text,
    call_key text,
    decided_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (country, qid, prop)
);

CREATE TABLE IF NOT EXISTS ptree_run (
    id serial PRIMARY KEY,
    country text NOT NULL,
    qs_path text,
    lines integer,
    parse_ok boolean,
    parse_detail text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- One row per holder of an item ({h, s, e, b, d, c}: tenure, life, citizenships), for the era rule.
ALTER TABLE ptree_item ADD COLUMN IF NOT EXISTS holder_rows jsonb NOT NULL DEFAULT '[]';

-- One QS batch: a paste-era chunk or a QS3 batch. The row is written before the
-- request, so an answer lost in flight leaves a row with no qs3_id, never a second send.
CREATE TABLE IF NOT EXISTS ptree_batch (
    id serial PRIMARY KEY,
    kind text NOT NULL,              -- 'paste' | 'qs3'
    op text NOT NULL,                -- 'add' | 'remove': a batch never mixes them
    name text NOT NULL,
    qs3_id integer UNIQUE,           -- NULL until QS3 answers, and for every paste chunk
    paste_chunk integer UNIQUE,      -- 1..64, the paste era
    status text NOT NULL,            -- 'sending' | 'running' | 'done' | 'stopped' | 'unknown'
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

-- One row per statement sent, added or removed, keyed on the statement itself:
-- an addition by its line without summary or retrieval date, a removal by its GUID.
-- 'sent' → 'landed' (live, or for a removal: gone) | 'failed'; 'reverted' is an
-- addition that landed and was later removed by hand.
CREATE TABLE IF NOT EXISTS ptree_edit (
    op text NOT NULL,
    key text NOT NULL,
    country text NOT NULL,
    line text NOT NULL,
    batch_id integer NOT NULL REFERENCES ptree_batch(id),
    status text NOT NULL DEFAULT 'sent',
    status_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (op, key)
);

-- A reviewer's veto on a proposed addition: never send it. Value '*' strikes
-- every value of (qid, prop).
CREATE TABLE IF NOT EXISTS ptree_strike (
    qid text NOT NULL,
    prop text NOT NULL,
    value text NOT NULL DEFAULT '*',
    country text NOT NULL,
    reason text NOT NULL,
    origin text NOT NULL,            -- 'cli' | 'note' (imported from sweep.md)
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (qid, prop, value)
);

-- A statement that should leave Wikidata, by GUID. `ours`: our batch added it and
-- nobody else has sourced it, so the strike that queued it was its approval.
-- 'proposed' | 'approved' | 'rejected' | 'gone' (absent at pre-flight); sending
-- is tracked in ptree_edit with op 'remove'.
CREATE TABLE IF NOT EXISTS ptree_removal (
    guid text PRIMARY KEY,
    qid text NOT NULL,
    prop text NOT NULL,
    value text NOT NULL,
    country text,
    reason text NOT NULL,
    origin text NOT NULL,            -- 'strike' | 'revert' | 'byproduct:<file>' | 'cli'
    ours boolean NOT NULL,
    status text NOT NULL,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
