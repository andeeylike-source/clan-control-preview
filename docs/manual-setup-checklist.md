# Manual Setup Checklist — Supabase v1

---

## 1. Create Supabase project

1. Go to [https://supabase.com/dashboard](https://supabase.com/dashboard).
2. Click **New project**.
3. Choose an organization (or create one).
4. Set project name: e.g. `clan-control`.
5. Set a strong database password — save it somewhere secure.
6. Choose the region closest to your users.
7. Click **Create new project** and wait for provisioning (~2 min).

---

## 2. Apply migration

1. Open **SQL Editor** in the Supabase dashboard (left sidebar).
2. Click **New query**.
3. Paste the entire contents of `supabase/migrations/0001_clan_control_v1.sql`.
4. Click **Run** (or Ctrl+Enter).
5. Verify the output shows no errors.

Alternative (Supabase CLI):

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

---

## 3. Verify tables

1. Open **Table Editor** in the Supabase dashboard.
2. Confirm these 9 tables exist:
   - `packs`
   - `players`
   - `player_aliases`
   - `calendar_events`
   - `km_sessions`
   - `km_session_player_stats`
   - `player_profa_history`
   - `player_notes`
   - `app_settings`
3. Click into each table and verify columns match the schema in `docs/schema-v1.md`.
4. Quick sanity check — run in SQL Editor:
   ```sql
   select table_name
   from information_schema.tables
   where table_schema = 'public'
   order by table_name;
   ```
   Expected: 9 rows.

---

## 4. Verify indexes and triggers

Run in SQL Editor:

```sql
-- Indexes
select indexname, tablename
from pg_indexes
where schemaname = 'public'
order by tablename, indexname;

-- Triggers
select trigger_name, event_object_table
from information_schema.triggers
where trigger_schema = 'public'
order by event_object_table;
```

Expected triggers on: `players`, `calendar_events`, `km_sessions`, `app_settings`.

---

## 5. Collect connection details for future frontend integration

1. Go to **Settings → API** in the Supabase dashboard.
2. Note down:
   - **Project URL** (`https://<ref>.supabase.co`)
   - **anon / public** API key
3. These will be needed when the frontend migration begins.
4. Do **not** embed keys in the HTML file yet — this checklist is preparation only.

---

## 6. Current site status

After completing steps 1–5:

- The current site (`BASA (1).html`) continues to work exactly as before.
- It still reads/writes `localStorage` only.
- No frontend code was changed.
- The Supabase database is empty and ready for a future data migration script.

---

## What comes next (out of scope for v1)

- Write a one-time migration script to export localStorage → Supabase.
- Add `@supabase/supabase-js` to the frontend.
- Implement dual-write (localStorage + Supabase) during transition.
- Enable RLS policies once auth is added.
