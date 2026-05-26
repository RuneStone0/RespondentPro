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
4. Paste it into the **Cookie** field in the app's settings panel

The cookie is saved to the data store (see below) and is never committed to git.

## Data store

The app supports two storage backends, controlled by `DATA_STORE_MODE` in your `.env` file.

### Local (default)

Config and answer history are stored as JSON files in the `data/` directory (gitignored).

```
data/config.json   ← app settings, cookie, API keys
data/answers.json  ← screener answer history
```

No extra setup needed. Files are human-readable and easy to inspect.

### MongoDB

For persistent storage across redeployments (e.g. Portainer/Docker on a server):

```
DATA_STORE_MODE=mongodb
MONGODB_URI=mongodb://user:pass@host:27017/respondentpro
```

The app auto-creates the `respondentpro` database and the `config` / `answers` collections on first start. No manual DB setup required.

## Configuration

Copy `env.example` to `.env` and uncomment what you need:

```bash
cp env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_STORE_MODE` | `local` | `local` or `mongodb` |
| `MONGODB_URI` | — | Required when `DATA_STORE_MODE=mongodb` |
| `AI_PROVIDER` | — | Active AI provider: `anthropic`, `grok`, or `gpt` |
| `AI_API_KEY` | — | API key for the provider set in `AI_PROVIDER` (overrides value stored in data store) |

> **Security:** Never put `RESPONDENT_COOKIE` in `.env`. Your session cookie is a live auth token — set it via the cookie modal in the app UI.

## Docker / Portainer

A `docker-compose.yml` is included for running via Portainer or plain Docker Compose.

```bash
docker compose up -d
```

This builds the image and mounts a named volume at `/app/data` for persistent local storage. The app is available on port 3000.

To use MongoDB instead, add the environment variables to `docker-compose.yml`:

```yaml
environment:
  - NODE_ENV=production
  - DATA_STORE_MODE=mongodb
  - MONGODB_URI=mongodb://user:pass@mongo:27017/respondentpro
```

## Development

```bash
npm test           # run all tests
npm run test:watch # watch mode
```
