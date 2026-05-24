# RespondentPro v2

A personal Node.js web app for browsing and managing your [Respondent.io](https://app.respondent.io) research study opportunities. Runs locally, authenticates with your existing session cookie, and adds filtering, sorting, auto-hide, and quality-of-life features that the Respondent UI doesn't provide.

---

## Features

### Project cards
- Title, incentive, hourly rate, duration, research type
- **Screener question count + $/question ratio** (fetched lazily in the background)
- Keyword highlighting in title and description
- **Apply button (↗)** — opens the referral link in a new tab, then prompts *"Did you apply?"* with **No, keep it / Yes, hide it** buttons
- **Enter key** opens the selected card's referral link
- Keyboard navigation (↑ / ↓ arrows, Ctrl+D to hide)

### Filtering
| Filter | Description |
|---|---|
| Min $/hr | Minimum calculated hourly rate |
| Min incentive | Minimum payout ($) |
| Min / Max duration | Study length in minutes |
| Research type | Multi-select (interview, survey, diary, etc.) |
| Exclude keywords | Hide projects whose title or description contain any keyword |
| **Priority keywords** | Pin matching projects to the top with a ⭐ badge |
| Sort | By score, date, pay, duration, question count, or $/question |

Keyword lists show the 3 most recent entries by default and collapse/expand cleanly.
Each keyword tag shows a live badge with how many currently-visible projects it matches.

### Auto-hide cron
Runs on a configurable schedule (every minute → daily) and automatically hides projects that match your filter criteria. Configurable max projects per run (default 1, max 20) to stay conservative.

### Keep-alive ping
Periodically calls the Respondent API to keep your session from expiring between visits.

### Stats footer
- **✓ N applied** — incremented each time you confirm applying to a project
- **🗑 N hidden** — total projects hidden (manual + auto)

---

## Requirements

- Node.js 24+
- A valid Respondent.io session cookie

---

## Setup

```bash
# 1. Install dependencies
npm install

# 2. Start the server
npm start
```

Open **http://localhost:3000** in your browser.

### Setting your session cookie

1. Log in to [app.respondent.io](https://app.respondent.io) in your browser
2. Open DevTools → Application → Cookies
3. Copy the value of `respondent.session.sid`
4. Paste it into the **Cookie** field in the app's settings panel

The cookie is stored in `data/config.json` (gitignored — never committed).

---

## Project structure

```
src/
  server.js          Express server, API proxy, cron scheduling
  public/
    index.html       Single-page UI (vanilla JS, no framework)
  lib/
    cookie.js        Cookie normalisation
    filter.js        Project filtering logic (whyHide)
    migrations.js    One-time config migrations on boot
    profile.js       Profile ID extraction
    project-fields.js  Field accessors (getId, getTitle, getIncentive, …)
    schedules.js     Cron schedule helpers
test/                Vitest unit tests (100% coverage on src/lib/)
data/                Runtime only — gitignored
  config.json        Persisted settings (cookie, filters, counters)
```

---

## Development

```bash
npm test             # Run tests once
npm run test:watch   # Watch mode
npm run test:coverage  # Coverage report
```

---

## Debug endpoints

| Endpoint | Description |
|---|---|
| `GET /api/debug` | In-memory request log + config snapshot |
| `GET /api/debug/first-project` | Raw first project from the Respondent list API (useful for inspecting data shape) |
| `GET /api/debug/upstream?path=…` | Proxies any Respondent path and returns status, content-type, and body — useful for exploring their API |
