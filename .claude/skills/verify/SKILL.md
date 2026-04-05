---
name: verify
description: Open the preview URL in Playwright, take a screenshot, and report what you see. Use after pushing changes to preview to do a quick visual sanity-check.
---

1. Navigate to `https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html` using the Playwright MCP browser.
2. Wait for the page to finish loading (wait for `#page-dashboard` to be visible or for the auth screen if not logged in).
3. Take a full-page screenshot.
4. Report in one short paragraph: what is visible, whether it looks correct, and any obvious visual issues.
5. If $ARGUMENTS specifies a page (e.g. "calendar", "players"), navigate to that hash (`#page-calendar`, `#page-players`, etc.) before screenshotting.
