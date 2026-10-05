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

-- One row per statement the outbox wrote to a chunk, keyed on the statement itself.
CREATE TABLE IF NOT EXISTS ptree_emitted (
    key text PRIMARY KEY,
    country text NOT NULL,
    line text NOT NULL,
    chunk integer NOT NULL,
    emitted_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'emitted',
    status_at timestamptz NOT NULL DEFAULT now()
);
