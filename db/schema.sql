-- ============================================================================
-- Rigorlytics — full schema (9 tables)
-- Target: Supabase / PostgreSQL 15+
--
-- Reconstructed from the session-handoff decisions:
--   * stats as JSONB (sport-agnostic)
--   * external_id on players/teams for ESPN mapping + idempotent upserts
--   * money as bigint in whole dollars (no floats)
--   * per + true_shooting promoted to first-class columns for fast leaderboards
--   * cap hits live in their own money table (contracts), separate from players
--
-- Idempotent: safe to re-run. Uses IF NOT EXISTS everywhere and CREATE OR
-- REPLACE for the trigger function.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Shared: updated_at auto-touch trigger
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 1. leagues  — NBA / NFL / MLB / NHL / WNBA
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leagues (
    id          smallint     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text         NOT NULL UNIQUE,          -- 'NBA','NFL','MLB','NHL','WNBA'
    name        text         NOT NULL,
    sport       text         NOT NULL,                 -- 'basketball','football','baseball','hockey'
    espn_slug   text,                                  -- e.g. 'basketball/nba' for ESPN endpoints
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 2. seasons  — one row per league per year
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seasons (
    id          integer      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    league_id   smallint     NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    year        smallint     NOT NULL,                 -- the ending year, e.g. 2024 for 2023-24
    label       text,                                  -- display label, e.g. '2023-24'
    season_type text         NOT NULL DEFAULT 'regular', -- 'regular','post','pre'
    start_date  date,
    end_date    date,
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (league_id, year, season_type)
);
CREATE INDEX IF NOT EXISTS idx_seasons_league_year ON seasons (league_id, year);

-- ----------------------------------------------------------------------------
-- 3. teams  — keyed to ESPN via external_id for upserts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id           integer      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    league_id    smallint     NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    source       text         NOT NULL DEFAULT 'espn',
    external_id  text         NOT NULL,                 -- ESPN team id
    abbreviation text,                                  -- real abbrev, e.g. 'GSW'
    location     text,                                  -- 'Golden State'
    name         text,                                  -- 'Warriors'
    display_name text,                                  -- 'Golden State Warriors'
    active       boolean      NOT NULL DEFAULT true,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    updated_at   timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_teams_league       ON teams (league_id);
CREATE INDEX IF NOT EXISTS idx_teams_abbreviation ON teams (league_id, abbreviation);

-- ----------------------------------------------------------------------------
-- 4. players  — keyed to ESPN via external_id for upserts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    id             integer      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source         text         NOT NULL DEFAULT 'espn',
    external_id    text         NOT NULL,               -- ESPN athlete id
    league_id      smallint     REFERENCES leagues(id) ON DELETE SET NULL, -- primary league
    full_name      text         NOT NULL,
    first_name     text,
    last_name      text,
    position       text,
    jersey         text,
    birth_date     date,
    height_in      smallint,                            -- inches
    weight_lb      smallint,
    active         boolean      NOT NULL DEFAULT true,
    headshot_url   text,
    created_at     timestamptz  NOT NULL DEFAULT now(),
    updated_at     timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_players_league    ON players (league_id);
CREATE INDEX IF NOT EXISTS idx_players_full_name ON players (lower(full_name));
-- trigram index for fuzzy name lookup (disambiguation); needs pg_trgm
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_players_name_trgm ON players USING gin (lower(full_name) gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- 5. player_seasons  — season line per player; stats JSONB + promoted metrics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_seasons (
    id            bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id     integer      NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season_id     integer      NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    team_id       integer      REFERENCES teams(id) ON DELETE SET NULL,
    league_id     smallint     NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    games_played  smallint,
    stats         jsonb        NOT NULL DEFAULT '{}'::jsonb,  -- sport-agnostic raw/derived stats
    -- promoted for fast leaderboards (not buried in JSONB):
    per           numeric(6,3),                          -- Player Efficiency Rating
    true_shooting numeric(6,4),                          -- TS% as a fraction, e.g. 0.5860
    created_at    timestamptz  NOT NULL DEFAULT now(),
    updated_at    timestamptz  NOT NULL DEFAULT now(),
    -- ESPN's types/2 endpoint returns ONE regular-season aggregate per player
    -- per season, so the natural key is (player, season). team_id is a nullable
    -- attribute (per-season team isn't reliably available from that endpoint);
    -- keeping it out of the key means NULLs can't spawn duplicate rows on re-run.
    UNIQUE (player_id, season_id)
);
CREATE INDEX IF NOT EXISTS idx_ps_player          ON player_seasons (player_id);
CREATE INDEX IF NOT EXISTS idx_ps_season          ON player_seasons (season_id);
CREATE INDEX IF NOT EXISTS idx_ps_league_season   ON player_seasons (league_id, season_id);
CREATE INDEX IF NOT EXISTS idx_ps_per             ON player_seasons (league_id, per DESC);
CREATE INDEX IF NOT EXISTS idx_ps_ts              ON player_seasons (league_id, true_shooting DESC);
CREATE INDEX IF NOT EXISTS idx_ps_stats_gin       ON player_seasons USING gin (stats);

-- ----------------------------------------------------------------------------
-- 6. contracts  — money table (per player-season cap hit). bigint whole dollars.
--    Kept separate from players so salary-cap analysis is a first-class query.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contracts (
    id             bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id      integer      NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id        integer      REFERENCES teams(id) ON DELETE SET NULL,
    league_id      smallint     NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season_id      integer      REFERENCES seasons(id) ON DELETE SET NULL,
    year           smallint     NOT NULL,               -- contract year (denormalized for range scans)
    cap_hit        bigint,                              -- whole dollars
    base_salary    bigint,
    dead_cap       bigint,
    signing_bonus  bigint,
    guaranteed     bigint,
    source         text         NOT NULL DEFAULT 'manual',
    external_id    text,                                -- source key if imported
    created_at     timestamptz  NOT NULL DEFAULT now(),
    updated_at     timestamptz  NOT NULL DEFAULT now(),
    -- one cap hit per player per league-year (team_id nullable, so kept out of
    -- the key for the same NULL-dedupe reason as player_seasons).
    UNIQUE (player_id, league_id, year)
);
CREATE INDEX IF NOT EXISTS idx_contracts_player       ON contracts (player_id);
CREATE INDEX IF NOT EXISTS idx_contracts_team_year    ON contracts (team_id, year);
CREATE INDEX IF NOT EXISTS idx_contracts_cap_hit      ON contracts (league_id, year, cap_hit DESC);

-- ----------------------------------------------------------------------------
-- 7. games  — schedule / results, keyed to ESPN via external_id
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS games (
    id            bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    league_id     smallint     NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season_id     integer      REFERENCES seasons(id) ON DELETE SET NULL,
    source        text         NOT NULL DEFAULT 'espn',
    external_id   text         NOT NULL,                -- ESPN event id
    game_date     timestamptz,
    status        text,                                 -- 'scheduled','in','final'
    home_team_id  integer      REFERENCES teams(id) ON DELETE SET NULL,
    away_team_id  integer      REFERENCES teams(id) ON DELETE SET NULL,
    home_score    smallint,
    away_score    smallint,
    created_at    timestamptz  NOT NULL DEFAULT now(),
    updated_at    timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_games_league_date ON games (league_id, game_date);
CREATE INDEX IF NOT EXISTS idx_games_season      ON games (season_id);
CREATE INDEX IF NOT EXISTS idx_games_home        ON games (home_team_id);
CREATE INDEX IF NOT EXISTS idx_games_away        ON games (away_team_id);

-- ----------------------------------------------------------------------------
-- 8. game_stats  — per-player box line for a game; stats JSONB
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS game_stats (
    id          bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id     bigint       NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id   integer      NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id     integer      REFERENCES teams(id) ON DELETE SET NULL,
    league_id   smallint     NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    stats       jsonb        NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (game_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_gs_game       ON game_stats (game_id);
CREATE INDEX IF NOT EXISTS idx_gs_player     ON game_stats (player_id);
CREATE INDEX IF NOT EXISTS idx_gs_stats_gin  ON game_stats USING gin (stats);

-- ----------------------------------------------------------------------------
-- 9. ingestion_log  — observability for every ingest run
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_log (
    id             bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source         text         NOT NULL,               -- 'espn','manual', etc.
    entity_type    text         NOT NULL,               -- 'teams','players','player_seasons','games'
    league_code    text,
    status         text         NOT NULL DEFAULT 'running', -- 'running','success','error'
    records_read   integer      DEFAULT 0,
    records_upsert integer      DEFAULT 0,
    started_at     timestamptz  NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    error          text,
    notes          jsonb        DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ingest_entity ON ingestion_log (entity_type, started_at DESC);

-- ----------------------------------------------------------------------------
-- updated_at triggers on every mutable table
-- ----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'leagues','seasons','teams','players','player_seasons',
        'contracts','games','game_stats'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$s;', t);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$s
             FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END $$;

COMMIT;

-- ============================================================================
-- Notes for reviewer:
--  * true_shooting stored as a fraction (0.586). If your pipeline computes it
--    as a percentage (58.6), change to numeric(6,3) and adjust the loader.
--  * `contracts` doubles as the per-season cap-hit table (one row per player /
--    league / year / team). The handoff said "cap hits -> separate table";
--    this is that table. If you'd rather split contract-terms from yearly cap
--    hits into two tables, that pushes the count to 10 — flag it and I'll split.
--  * All ESPN-sourced tables upsert on (source, external_id). Static tables
--    (leagues, seasons) upsert on their natural keys.
-- ============================================================================
