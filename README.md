# RespondentPro

A local Node.js app that supercharges your [Respondent.io](https://app.respondent.io) project feed with filtering, sorting, and automation that the default UI doesn't offer. No account or auth setup needed — it runs on your existing session cookie.

![Screenshot](screenshot.png)

## What it solves

Respondent's project list has no way to filter by pay rate, hide irrelevant studies, or surface the best opportunities first. This app pulls your project feed and gives you full control over what you see and how it's ranked.

## Features

- **Smart filtering** — set minimum $/hr, minimum incentive, and session length bounds
- **Keyword boost** — pin projects matching your keywords to the top with a ⭐ badge
- **Keyword exclude** — auto-hide projects whose title or description contain unwanted terms; live match counts on each tag
- **Sort modes** — by score, date, pay, duration, question count, or $/question
- **$/question ratio** — fetched lazily per project so you can compare screener value at a glance
- **Apply flow** — open the referral link, then confirm "Did you apply?" to hide it or keep it
- **Keyboard navigation** — ↑/↓ to move between cards, Enter to open, Ctrl+D to hide
- **Auto-hide cron** — runs on a configurable schedule and hides matched projects automatically
- **Keep-alive ping** — stops your session cookie from expiring between visits
- **Stats footer** — running count of applied and hidden projects

## How to run

**Requirements:** Node.js 24+

```bash
npm install
npm start
```

Open **http://localhost:3000** in your browser.

**Setting your session cookie:**

1. Log in to [app.respondent.io](https://app.respondent.io)
2. Open DevTools → Application → Cookies
3. Copy the value of `respondent.session.sid`
4. Paste it into the **Cookie** field in the app's top-right panel

The cookie is saved to `data/config.json` (gitignored, never committed).
