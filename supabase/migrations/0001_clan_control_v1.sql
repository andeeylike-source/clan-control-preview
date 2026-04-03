-- =============================================================================
-- Clan Control v1 — Supabase / PostgreSQL schema
-- Migration: 0001_clan_control_v1.sql
-- Safe for first clean run (all CREATE IF NOT EXISTS / idempotent).
-- =============================================================================

-- 0. Extensions -----------------------------------------------------------------
create extension if not exists pgcrypto;

-- 1. Tables ---------------------------------------------------------------------

-- 1.1 packs
create table if not exists packs (
    id          uuid        primary key default gen_random_uuid(),
    name        text        unique not null,
    is_active   boolean     not null default true,
    created_at  timestamptz not null default now()
);

-- 1.2 players
create table if not exists players (
    id              uuid        primary key default gen_random_uuid(),
    name            text        not null,
    -- Canonical values: 'KL', 'PL', 'Player'.
    -- Current BASA data stores Cyrillic: 'КЛ', 'ПЛ', 'ИГРОК'.
    -- Migration script must normalize before insert:
    --   'КЛ'    → 'KL'
    --   'ПЛ'    → 'PL'
    --   'ИГРОК' → 'Player'
    rank            text        not null check (rank in ('KL','PL','Player')),
    primary_profa   text        null,
    pack_id         uuid        null references packs(id) on delete set null,
    verified        boolean     not null default false,
    is_new          boolean     not null default false,
    status          text        not null default 'active' check (status in ('active','archived')),
    archived_at     timestamptz null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- 1.3 player_aliases
create table if not exists player_aliases (
    id                      uuid        primary key default gen_random_uuid(),
    player_id               uuid        not null references players(id) on delete cascade,
    alias_text              text        not null,
    alias_text_normalized   text        not null,
    created_from            text        not null default 'manual'
                                        check (created_from in ('manual','fuzzy','ocr')),
    created_at              timestamptz not null default now(),
    unique(alias_text_normalized)
);

-- 1.4 calendar_events
create table if not exists calendar_events (
    id              uuid        primary key default gen_random_uuid(),
    title           text        not null,
    event_date      date        not null,
    event_time      text        null,
    type            text        not null check (type in ('Epic','Siege','TV','Manual')),
    status          text        null,
    source          text        not null default 'manual'
                                check (source in ('manual','preset','system')),
    override_json   jsonb       null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- 1.5 km_sessions
create table if not exists km_sessions (
    id                      uuid        primary key default gen_random_uuid(),
    session_date            date        not null unique,
    event_id                uuid        null references calendar_events(id) on delete set null,
    raid_total              integer     null,
    applied_at              timestamptz null,
    command_channel_json    jsonb       null,
    pack_leaders_json       jsonb       null,
    screen_players_map_json jsonb       null,
    raw_snapshot_json       jsonb       null,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

-- 1.6 km_session_player_stats
create table if not exists km_session_player_stats (
    id                  uuid        primary key default gen_random_uuid(),
    session_id          uuid        not null references km_sessions(id) on delete cascade,
    player_id           uuid        null references players(id) on delete set null,
    raw_name            text        not null,
    resolved_name       text        null,
    detected_profa      text        null,
    kills               integer     not null default 0,
    deaths              integer     not null default 0,
    pvp_dmg             numeric     not null default 0,
    pve_dmg             numeric     not null default 0,
    pack_name           text        null,
    leader_name         text        null,
    raw_payload_json    jsonb       null,
    created_at          timestamptz not null default now()
);

-- 1.7 player_profa_history
create table if not exists player_profa_history (
    id              uuid        primary key default gen_random_uuid(),
    player_id       uuid        not null references players(id) on delete cascade,
    session_id      uuid        null references km_sessions(id) on delete cascade,
    session_date    date        not null,
    profa           text        not null,
    source          text        not null default 'manual',
    created_at      timestamptz not null default now(),
    unique(player_id, session_date)
);

-- 1.8 player_notes
create table if not exists player_notes (
    id          uuid        primary key default gen_random_uuid(),
    player_id   uuid        not null references players(id) on delete cascade,
    content     text        not null,
    author      text        null,
    created_at  timestamptz not null default now()
);

-- 1.9 app_settings
create table if not exists app_settings (
    key         text        primary key,
    value_json  jsonb       not null,
    updated_at  timestamptz not null default now()
);

-- 2. Indexes --------------------------------------------------------------------

create index if not exists idx_players_name          on players(name);
create index if not exists idx_players_status        on players(status);
create index if not exists idx_players_pack_id       on players(pack_id);

create index if not exists idx_player_aliases_player_id on player_aliases(player_id);

create index if not exists idx_calendar_events_event_date on calendar_events(event_date);

create index if not exists idx_km_sessions_session_date on km_sessions(session_date);
create index if not exists idx_km_sessions_event_id     on km_sessions(event_id);

create index if not exists idx_km_session_player_stats_session_id on km_session_player_stats(session_id);
create index if not exists idx_km_session_player_stats_player_id  on km_session_player_stats(player_id);

create index if not exists idx_player_profa_history_pid_date on player_profa_history(player_id, session_date);

create index if not exists idx_player_notes_player_id on player_notes(player_id);

-- 3. Trigger: auto-update updated_at ------------------------------------------------

create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- Apply to every table that carries an updated_at column.
-- DROP + CREATE makes re-runs safe.

drop trigger if exists trg_players_updated_at          on players;
create trigger trg_players_updated_at
    before update on players
    for each row execute function set_updated_at();

drop trigger if exists trg_calendar_events_updated_at  on calendar_events;
create trigger trg_calendar_events_updated_at
    before update on calendar_events
    for each row execute function set_updated_at();

drop trigger if exists trg_km_sessions_updated_at      on km_sessions;
create trigger trg_km_sessions_updated_at
    before update on km_sessions
    for each row execute function set_updated_at();

drop trigger if exists trg_app_settings_updated_at     on app_settings;
create trigger trg_app_settings_updated_at
    before update on app_settings
    for each row execute function set_updated_at();

-- =============================================================================
-- End of migration 0001
-- =============================================================================
