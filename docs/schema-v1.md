# Clan Control — Schema v1

Migration file: `supabase/migrations/0001_clan_control_v1.sql`

---

## Tables overview

| # | Table | Role | PK | Purpose |
|---|-------|------|----|---------|
| 1 | `packs` | Source of truth | `id` (uuid) | Clan packs / groups |
| 2 | `players` | Source of truth | `id` (uuid) | All players (active + archived via `status`) |
| 3 | `player_aliases` | Support | `id` (uuid) | Alternate in-game names per player |
| 4 | `calendar_events` | Source of truth | `id` (uuid) | Scheduled events (Epic, Siege, TV, Manual) |
| 5 | `km_sessions` | Source of truth | `id` (uuid) | One KM session per date |
| 6 | `km_session_player_stats` | Source of truth | `id` (uuid) | Per-player stats within a KM session |
| 7 | `player_profa_history` | Support | `id` (uuid) | Profa snapshot per player per session date |
| 8 | `player_notes` | Support | `id` (uuid) | Free-text notes attached to a player |
| 9 | `app_settings` | Config | `key` (text) | Key-value store for app-wide settings |

---

## Foreign keys

| Child table | Column | References | On delete |
|-------------|--------|------------|-----------|
| `players` | `pack_id` | `packs(id)` | SET NULL |
| `player_aliases` | `player_id` | `players(id)` | CASCADE |
| `km_sessions` | `event_id` | `calendar_events(id)` | SET NULL |
| `km_session_player_stats` | `session_id` | `km_sessions(id)` | CASCADE |
| `km_session_player_stats` | `player_id` | `players(id)` | SET NULL |
| `player_profa_history` | `player_id` | `players(id)` | CASCADE |
| `player_profa_history` | `session_id` | `km_sessions(id)` | CASCADE |
| `player_notes` | `player_id` | `players(id)` | CASCADE |

---

## Source-of-truth vs support/config

### Source-of-truth tables
These hold authoritative data that the app reads and writes directly.

- **packs** — canonical list of packs.
- **players** — canonical roster. Archived players live here with `status = 'archived'`; there is no separate archive table.
- **calendar_events** — canonical event list. Event statuses and overrides are folded into `status` and `override_json` columns.
- **km_sessions** — one row per KM date; stores session-level metadata and raw JSON snapshots.
- **km_session_player_stats** — per-player rows under a session; stores kills, deaths, damage, detected profa, etc.

### Support tables
Derived or supplementary data.

- **player_aliases** — additional names for fuzzy/OCR matching.
- **player_profa_history** — daily profa snapshot for trend tracking.
- **player_notes** — free-text annotations.

### Config table
- **app_settings** — stores app-wide key-value config (e.g. `valueWeights`, `exhaustedKeys`).

---

## Indexes

All indexes are documented in the migration file. Key lookup patterns:

- Players by `name`, `status`, `pack_id`
- Aliases by `player_id`
- Events by `event_date`
- Sessions by `session_date`, `event_id`
- Stats by `session_id`, `player_id`
- Profa history by `(player_id, session_date)` (also a unique constraint)
- Notes by `player_id`

---

## Triggers

One reusable function `set_updated_at()` auto-sets `updated_at = now()` on UPDATE.
Applied to: `players`, `calendar_events`, `km_sessions`, `app_settings`.

---

## Design decisions

1. **No separate archive table.** `players.status = 'archived'` + `archived_at` timestamp.
2. **No separate eventStatuses / eventOverrides tables.** Folded into `calendar_events.status` and `calendar_events.override_json`.
3. **No derived metric tables** (attendance, value_score, trend, synergy, boss_analysis). Those will be computed at query time or added later.
4. **No auth / RLS / storage / edge functions** in v1.
5. **Rank normalization required during migration.** The current frontend stores ranks as Cyrillic strings (`'КЛ'`, `'ПЛ'`, `'ИГРОК'`). The DB schema enforces Latin canonical values (`'KL'`, `'PL'`, `'Player'`). The migration script must convert values before insert. See `docs/localstorage-to-supabase-mapping.md` → *Rank normalization* for the mapping table.
