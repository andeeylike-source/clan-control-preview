# localStorage to Supabase — Mapping

All keys below live inside the `clanControl_v1` localStorage blob in `BASA (1).html`.

---

| # | localStorage key | Target table / field | Migrate now? | Notes |
|---|-----------------|---------------------|-------------|-------|
| 1 | `roster` | `players` | Yes | Each roster entry → one `players` row. `primary_profa`, `verified`, `is_new` map 1:1. `pack_id` resolved via `packs` lookup. **`rank` requires normalization** — see Rank normalization section below. |
| 2 | `archive` | `players` (status = `'archived'`) | Yes | Same table as roster; set `status = 'archived'`, populate `archived_at`. **`rank` requires same normalization as roster.** No separate archive table. |
| 3 | `packs` | `packs` | Yes | Array of pack names → one row each. `is_active` defaults to `true`. |
| 4 | `manualEvents` | `calendar_events` | Yes | Each event → one row. `type` = `'Manual'` for user-created; `source` = `'manual'`. |
| 5 | `eventStatuses` | `calendar_events.status` | Yes | Keyed by event; merge into the matching `calendar_events` row's `status` column. |
| 6 | `eventOverrides` | `calendar_events.override_json` | Yes | Keyed by event; merge into the matching `calendar_events` row's `override_json` JSONB column. |
| 7 | `kmStats` | `km_sessions` + `km_session_player_stats` | Yes | Top-level session metadata → `km_sessions`. Per-player stat lines → `km_session_player_stats`. JSON snapshots go into `raw_snapshot_json` / `raw_payload_json`. |
| 8 | `nickAliases` | `player_aliases` | Yes | Each alias entry → one `player_aliases` row. Normalize alias text into `alias_text_normalized` (lowercase, trimmed). Set `created_from` = `'manual'` unless source is known. |
| 9 | `exhaustedKeys` | `app_settings` (key = `'exhaustedKeys'`) | Yes | Store as `{ "key": "exhaustedKeys", "value_json": <array> }`. |
| 10 | `appliedStatsByDate` | `km_sessions.applied_at` + session-level data | Yes | Date-keyed applied stats map to `km_sessions` rows (set `applied_at` timestamp). |
| 11 | `playerNotes` | `player_notes` | Yes | Each note → one `player_notes` row per player. Resolve `player_id` via name lookup. |
| 12 | `playerProfaByDate` | `player_profa_history` | Yes | Date-keyed profa snapshots → one row per `(player_id, session_date)`. |
| 13 | `valueWeights` | `app_settings` (key = `'valueWeights'`) | Yes | Store as `{ "key": "valueWeights", "value_json": <object> }`. |

---

## Additional localStorage keys (outside `clanControl_v1`)

These are UI/preference keys stored separately. They do **not** need Supabase migration now.

| Key | Purpose | Migrate? |
|-----|---------|----------|
| `cc_theme` | Dark/light theme preference | Later (or never — keep client-side) |
| `cc_lang` | Language preference | Later |
| `cc_onboarded` | Onboarding flag | Later |
| `cc_notify` | Notification preference | Later |
| `cc_action_log` | Local action log buffer | Later |
| `cc_screenshot_cache` | Temporary screenshot data | No — ephemeral |
| `clanControl_geminiKeys` | Gemini API keys | Later (move to `app_settings` or env) |
| `clan_control_calendar_visual_editor_v1` | Calendar editor state | Later |

---

## Migration notes

1. **Player identity** — Players are matched by `name`. During migration, create a player first, then link aliases, notes, profa history, and stats via the generated `player_id`.
2. **Pack resolution** — Create all packs first. Then look up `pack_id` when inserting players.
3. **Event merging** — Insert `manualEvents` into `calendar_events`. Then update matching rows with values from `eventStatuses` and `eventOverrides`.
4. **KM stats denormalization** — `kmStats` contains nested per-player data. Flatten into `km_session_player_stats` rows; keep original JSON in `raw_payload_json` for audit.
5. **Idempotency** — Use upserts (`ON CONFLICT`) during migration scripts to allow safe re-runs.

---

## Rank normalization

The current frontend (`BASA (1).html`) stores player ranks as **Cyrillic uppercase** strings.
The Supabase schema uses **Latin canonical** values.

The migration script must convert ranks before inserting into `players.rank`:

| localStorage value | DB canonical value | Meaning |
|--------------------|-------------------|---------|
| `'КЛ'` | `'KL'` | Clan Leader (Клан Лидер) |
| `'ПЛ'` | `'PL'` | Pack Leader (Пак Лидер) |
| `'ИГРОК'` | `'Player'` | Regular player |

The frontend `rankPriority` map confirms all three values:
```js
rankPriority = { "КЛ": 1, "ПЛ": 2, "ИГРОК": 3 }
```

**Migration example (pseudocode):**
```js
const RANK_MAP = { 'КЛ': 'KL', 'ПЛ': 'PL', 'ИГРОК': 'Player' };
const dbRank = RANK_MAP[player.rank] || 'Player'; // fallback to 'Player'
```

Or in SQL after a raw JSON import:
```sql
UPDATE players SET rank = CASE rank
    WHEN 'КЛ'    THEN 'KL'
    WHEN 'ПЛ'    THEN 'PL'
    WHEN 'ИГРОК' THEN 'Player'
    ELSE 'Player'
END;
```
