-- pepcorp's own tables (`pcorp_*`), in peploop's database. What pepcorp sends goes
-- through the joint send ledger (`wd_*`, peploop/schema.sql); the articles it
-- reads are kept in peploop's `article` table.

-- One row per enterprise a load found; `dropped` is the filter's reason, NULL when kept.
-- `chain` is the ownership path to a state actor, when the load found one.
CREATE TABLE IF NOT EXISTS pcorp_item (
    country text NOT NULL,
    qid text NOT NULL,
    lanes text[] NOT NULL,
    entity jsonb NOT NULL,
    chain jsonb,
    seed jsonb,
    dropped text,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (country, qid)
);

-- The answer ledger: one row per distinct request (content key), so a re-run
-- pays only for what changed.
CREATE TABLE IF NOT EXISTS pcorp_call (
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

-- Every proposed statement ends apply or skip, with the rule that decided it.
-- Rewritten whole for a country on each run.
CREATE TABLE IF NOT EXISTS pcorp_decision (
    country text NOT NULL,
    qid text NOT NULL,
    n integer NOT NULL,
    prop text NOT NULL,
    value text,
    detail jsonb NOT NULL DEFAULT '{}',
    disposition text NOT NULL,
    rule text NOT NULL,
    call_key text,
    decided_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (country, qid, n)
);
