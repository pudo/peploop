-- peptree's own tables (`ptree_*`), in peploop's database. What peptree sends goes
-- through the joint send ledger (`wd_*`, peploop/schema.sql).

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

-- One row per holder of an item ({h, s, e, b, d, c}: tenure, life, citizenships), for the era rule.
ALTER TABLE ptree_item ADD COLUMN IF NOT EXISTS holder_rows jsonb NOT NULL DEFAULT '[]';

-- What peptree sends, strikes and takes back lives in peploop's joint send
-- ledger: `wd_batch`, `wd_edit`, `wd_strike`, `wd_removal` (peploop/schema.sql).
