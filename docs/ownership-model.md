# Ownership Model — KM Entities

Defines who owns what, and who can do what. Direct input for SQL migrations and RLS policies.

---

## Context

- Auth: Supabase Auth (`auth.users`). Current user = `auth.uid()`.
- Roles: `profiles.role` — `free`, `pro`, `admin`. Checked via `private.is_admin(auth.uid())` helper function (avoids direct `profiles` join in every policy).
- Current live data: stored in `user_app_data.data` JSONB blob per user (migration 0002). Each user has their own isolated copy of events, sessions, stats.
- Schema v1 tables (0001): designed pre-auth, **no `user_id` columns**. Not yet used as source of truth — serve as target schema for future per-table migration.
- `km_screenshots` (0004): already has ownership columns + RLS. Reference pattern for all other entities.

---

## Ownership Columns (standard set)

Every owned entity table must have:

| Column | Type | Required | Purpose |
|--------|------|----------|---------|
| `user_id` | `uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE` | Yes | Row owner. Primary RLS filter. |
| `created_by` | `uuid NOT NULL REFERENCES auth.users(id)` | Yes | Who created. Usually = `user_id`. |
| `updated_by` | `uuid REFERENCES auth.users(id)` | No | Last modifier. Set on UPDATE. Nullable (never updated = NULL). |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | Yes | Already exists in v1 schema. |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | Yes | Already exists in v1 schema. Auto-trigger. |

**Rule**: `user_id` = data owner. `created_by` / `updated_by` = audit trail. In single-user flow they are the same. They diverge only when admin modifies another user's data (future).

---

## Entity Matrix

### 1. events (`calendar_events`)

KM events on the calendar (Epic, Siege, TV, Manual).

| Aspect | Rule |
|--------|------|
| Owner | `user_id` — the user whose calendar contains the event |
| "My data" | Yes — each user manages their own calendar |
| Shared? | No. Each user has independent event set (matches current `user_app_data` blob model) |
| CREATE | Owner only (`auth.uid() = user_id AND auth.uid() = created_by`) |
| SELECT | Owner reads own. Admin reads all. |
| UPDATE | Owner updates own (`updated_by` set to `auth.uid()`). |
| DELETE | Owner deletes own. |
| Admin | SELECT all (read-only). Admin write deferred — not in v1 scope. |
| Fields for RLS | `user_id` (primary filter), `created_by` (insert check) |

**Migration needed**: add `user_id`, `created_by`, `updated_by` to `calendar_events`.

### 2. event_entries (`km_sessions` + `km_session_player_stats`)

KM session data: per-date session metadata + per-player stat rows.

| Aspect | Rule |
|--------|------|
| Owner | `km_sessions.user_id` — the user who recorded/imported the session |
| "My data" | Yes — each user records their own KM stats |
| Shared? | No. Same isolation as events. |
| CREATE | Owner only |
| SELECT | Owner reads own. Admin reads all. |
| UPDATE | Owner updates own |
| DELETE | Owner deletes own. CASCADE: deleting `km_sessions` row cascades to `km_session_player_stats`. |
| Admin | SELECT all (read-only). |
| Fields for RLS | `km_sessions.user_id` (primary). `km_session_player_stats` inherits access via `session_id` FK — RLS on child checks `EXISTS (SELECT 1 FROM km_sessions WHERE id = session_id AND user_id = auth.uid())`. |

**Migration needed**: add `user_id`, `created_by`, `updated_by` to `km_sessions`. Child table `km_session_player_stats` does NOT need its own `user_id` — access derived from parent.

### 3. screenshots (`km_screenshots`)

Already implemented in migration 0004. Reference pattern.

| Aspect | Rule |
|--------|------|
| Owner | `user_id` |
| "My data" | Yes |
| Shared? | No |
| CREATE | Owner only |
| SELECT | Owner reads own. Admin reads all. |
| UPDATE | Owner updates own |
| DELETE | Owner deletes own. Storage file + DB row deleted together (app logic). |
| Admin | SELECT all (read-only). |
| Storage path | `{user_id}/{date_str}/{uuid}.{ext}` — ownership encoded in path. Storage RLS matches first path segment to `auth.uid()`. |

**No migration needed** — already done.

### 4. screenshot_analysis (future table)

Analysis results from AI processing of screenshots. Does not exist yet.
**Child table** — no own `user_id`. Access derived from parent `km_screenshots.user_id` via FK, same pattern as `km_session_player_stats`.

| Aspect | Rule |
|--------|------|
| Owner | Inherited from parent `km_screenshots.user_id` via `screenshot_id` FK |
| "My data" | Yes — analysis is derived from user's screenshots |
| Shared? | No |
| CREATE | App on behalf of screenshot owner |
| SELECT | Via parent: `EXISTS (SELECT 1 FROM km_screenshots WHERE id = screenshot_id AND user_id = auth.uid())`. Admin reads all. |
| UPDATE | Via parent (manual corrections). |
| DELETE | CASCADE from parent `km_screenshots`. No independent orphan rows. |
| Admin | SELECT all (read-only). |
| Fields for RLS | `screenshot_id` FK (used in parent-join check). No own `user_id`. |

**Proposed schema** (for future migration):

```sql
CREATE TABLE km_screenshot_analysis (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    screenshot_id   uuid NOT NULL REFERENCES km_screenshots(id) ON DELETE CASCADE,
    analysis_json   jsonb,          -- raw AI response
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','done','error','corrected')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
```

---

## Access Summary

| Entity | Owner CRUD | Admin Read | Admin Write | Shared |
|--------|-----------|------------|-------------|--------|
| `calendar_events` | Full | Yes | Deferred | No |
| `km_sessions` | Full | Yes | Deferred | No |
| `km_session_player_stats` | Via parent | Via parent | Deferred | No |
| `km_screenshots` | Full | Yes | Deferred | No |
| `km_screenshot_analysis` | Via parent (`km_screenshots`) | Via parent | Deferred | No |

---

## RLS Pattern (consistent across all entities)

### Prerequisite: `private.is_admin()` helper

Create once, use in every admin policy. Lives in `private` schema to prevent direct client calls.

```sql
CREATE SCHEMA IF NOT EXISTS private;

CREATE OR REPLACE FUNCTION private.is_admin(uid uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
    SELECT EXISTS (SELECT 1 FROM profiles WHERE id = uid AND role = 'admin');
$$;
```

### Owned tables (have `user_id`)

```sql
-- Owner CRUD
CREATE POLICY {table}_select_own ON {table}
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY {table}_insert_own ON {table}
    FOR INSERT WITH CHECK (auth.uid() = user_id AND auth.uid() = created_by);

CREATE POLICY {table}_update_own ON {table}
    FOR UPDATE USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY {table}_delete_own ON {table}
    FOR DELETE USING (auth.uid() = user_id);

-- Admin read-only
CREATE POLICY {table}_select_admin ON {table}
    FOR SELECT USING (private.is_admin(auth.uid()));
```

### Child tables without `user_id` (e.g. `km_session_player_stats`, `km_screenshot_analysis`)

Access derived from parent row's `user_id` via FK join.

```sql
-- Owner via parent
CREATE POLICY {child}_select_own ON {child}
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM {parent} WHERE {parent}.id = {child}.{parent_fk} AND {parent}.user_id = auth.uid())
    );

CREATE POLICY {child}_insert_own ON {child}
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM {parent} WHERE {parent}.id = {child}.{parent_fk} AND {parent}.user_id = auth.uid())
    );

CREATE POLICY {child}_update_own ON {child}
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM {parent} WHERE {parent}.id = {child}.{parent_fk} AND {parent}.user_id = auth.uid())
    );

CREATE POLICY {child}_delete_own ON {child}
    FOR DELETE USING (
        EXISTS (SELECT 1 FROM {parent} WHERE {parent}.id = {child}.{parent_fk} AND {parent}.user_id = auth.uid())
    );

-- Admin read-only
CREATE POLICY {child}_select_admin ON {child}
    FOR SELECT USING (private.is_admin(auth.uid()));
```

---

## What Remains (next steps)

1. **Migration 0005**: create `private.is_admin()` function. Update existing `km_screenshots` admin policy to use it. Add `user_id`, `created_by`, `updated_by` to `calendar_events` and `km_sessions`. Enable RLS + apply standard policies.
2. **Migration 0006**: create `km_screenshot_analysis` table (child, no `user_id` — access via parent FK). Apply child RLS pattern.
3. **Frontend**: when writing to owned tables, include `user_id = window._currentUserId` and `created_by = window._currentUserId` in every insert.
4. **Admin write access**: define when admin should be able to modify other users' data. Not needed for v1 — owner-first is sufficient.
5. **Transition from blob to per-table**: migrate data from `user_app_data.data` JSONB into owned rows in `calendar_events`, `km_sessions`, etc. Each row gets `user_id` from the blob's owner.

---

## Design Decisions

1. **No shared entities in v1.** Every row belongs to one user. This matches the current `user_app_data` blob isolation. Clan-wide shared views are a future feature.
2. **Admin = read-only expansion.** Admin can see all data but cannot modify others' data yet. This is safe and matches the existing `_cc().canAccessForeignUserData` capability gate.
3. **Child table access via parent FK.** `km_session_player_stats` (parent: `km_sessions`) and `km_screenshot_analysis` (parent: `km_screenshots`) derive access from their parent's `user_id`. No own `user_id` — avoids redundancy and guarantees no orphan-ownership drift.
4. **`created_by` / `updated_by` separate from `user_id`.** On owned tables only. Prepares for future admin-write scenarios without changing the schema again. Child tables omit these — audit trail lives on the parent.
5. **`private.is_admin()` over direct `profiles` join.** Single place to change admin logic. `SECURITY DEFINER` + `private` schema prevents client-side bypass.
