# CLAUDE.md

## Working rules

- Always communicate with the user in Russian.

## Auto-deploy to preview (mandatory)

After every successful site edit:

1. `git add` — only changed files, never `git add -A` blindly
2. `git commit -m "<short message>"`
3. `git push preview main`

After a successful push return exactly this block and nothing else:

```
preview pushed: yes
preview url: https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html
commit: <hash>
changed files: <list>
```

## Production — hard prohibition

- NEVER push to `origin main` automatically.
- NEVER run `deploy-production-pages.yml` automatically.
- Production only after user explicitly writes `да` in that turn.
- Task-level "deploy/push/publish" does NOT count as `да`.

## Output policy conflicts

`no status messages` / `no explanations` suppress prose only — never suppress the preview-push status block above.

## Project

**Active file:** `BASA (1).html` — single-file SPA, ~12 000 lines. All CSS, HTML, JS in one file. No build step.

Legacy files (`clan-control.html`, `BASA.html`, `BASAv1.html`) — do not edit.

**Backend:** Supabase (PostgreSQL). Client initialized with hardcoded credentials in the file. Data also in `localStorage` (current state); Supabase is target state.

**CSS cascade (later wins):**
1. Base rules
2. GLASS PREMIUM CALENDAR REDESIGN
3. `<style id="v1-shell-override">` — forces dark bg on both themes
4. `<style id="readability-layer">` — contrast boosts

**Key Supabase table:** `app_settings` — key-value config store (JSONB `value_json`).
