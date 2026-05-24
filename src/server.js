import 'dotenv/config';
import express from 'express';
import fetch from 'node-fetch';
import cron from 'node-cron';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

import { normalizeCookie, COOKIE_NAME } from './lib/cookie.js';
import {
  SCHEDULE_OPTIONS,
  isValidCron,
  resolveCron,
  nextRunForExpr,
} from './lib/schedules.js';
import { whyHide } from './lib/filter.js';
import { getProjectId, getTitle } from './lib/project-fields.js';
import { pickProfileId } from './lib/profile.js';
import { applyMigrations, VALID_SORTS } from './lib/migrations.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const DATA_DIR = join(ROOT, 'data');
const CONFIG_PATH = join(DATA_DIR, 'config.json');

const BASE_URL = 'https://app.respondent.io';
const PORT = 3000;

if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });

// ── Config ────────────────────────────────────────────────
const DEFAULT_CONFIG = {
  cookie: process.env.RESPONDENT_COOKIE || '',
  profileId: '',
  filters: {
    keywords: [],
    priorityKeywords: [],
    minHourlyRate: 0,
    minIncentive: 0,
    minDuration: 0,
    maxDuration: 120,
    kindsOfResearchStudy: [],
    sort: 'publishedAt',
    showEligible: true,
  },
  autoHide: {
    enabled: false,
    schedule: 'hourly',    // preset key OR 'custom'
    customCron: '',        // raw cron expression, used when schedule === 'custom'
    maxPerRun: 1,          // max projects to hide per cron run
    lastRunAt: null,
    lastRunResult: null,
  },
  keepAlive: {
    enabled: true,         // on by default
    schedule: 'hourly',
    lastRunAt: null,
    lastRunResult: null,
  },
  totalHidden: 0,
  totalApplied: 0,
  _migrations: {},
};

function loadConfig() {
  if (!existsSync(CONFIG_PATH)) return structuredClone(DEFAULT_CONFIG);
  try {
    const stored = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
    return {
      ...DEFAULT_CONFIG,
      ...stored,
      filters:   { ...DEFAULT_CONFIG.filters,   ...(stored.filters   || {}) },
      autoHide:  { ...DEFAULT_CONFIG.autoHide,  ...(stored.autoHide  || {}) },
      keepAlive: { ...DEFAULT_CONFIG.keepAlive, ...(stored.keepAlive || {}) },
    };
  } catch (e) {
    console.error('Failed to load config, using defaults:', e.message);
    return structuredClone(DEFAULT_CONFIG);
  }
}

function saveConfig() {
  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf8');
}

let config = loadConfig();
{
  const { dirty, applied } = applyMigrations(config);
  if (applied.length) console.log('[migration]', applied.join(', '));
  if (dirty || !existsSync(CONFIG_PATH)) saveConfig();
}

// ── Debug log (in-memory ring buffer) ─────────────────────
const DEBUG_LOG = [];
function debug(event, data = {}) {
  const entry = { t: new Date().toISOString(), event, ...data };
  DEBUG_LOG.unshift(entry);
  if (DEBUG_LOG.length > 50) DEBUG_LOG.pop();
  console.log(`[${entry.t}] ${event}`, Object.keys(data).length ? data : '');
}

// ── Respondent.io HTTP client ─────────────────────────────
// Minimal header set: enough for GET auth, plus Origin for POST (CSRF).
function buildHeaders(extra = {}) {
  return {
    cookie: config.cookie,
    'x-requested-with': 'XMLHttpRequest',
    'accept': 'application/json, text/plain, */*',
    'sec-fetch-site': 'same-origin',
    'origin': BASE_URL,
    ...extra,
  };
}

async function respondentFetch(path, { method = 'GET', query, body, extraHeaders = {} } = {}) {
  const url = `${BASE_URL}${path}${query ? '?' + query : ''}`;
  const headers = buildHeaders({ ...(body ? { 'content-type': 'application/json' } : {}), ...extraHeaders });
  const startedAt = Date.now();
  try {
    const res = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const ct = res.headers.get('content-type') ?? '';
    const isJson = ct.includes('json');
    debug('respondent_fetch', { method, url, status: res.status, ct: ct.slice(0, 40), ms: Date.now() - startedAt });
    return { res, isJson, ct };
  } catch (err) {
    debug('respondent_fetch_error', { method, url, error: err.message });
    throw err;
  }
}

// ── Domain operations ─────────────────────────────────────
async function discoverProfileId() {
  if (config.profileId) return config.profileId;
  const { res, isJson } = await respondentFetch('/v2/profiles/me');
  if (res.status === 401 || !isJson) throw new Error('session_expired');
  const body = await res.json();
  const id = pickProfileId(body);
  if (id) {
    debug('profile_id_discovered', { id });
    config.profileId = id;
    saveConfig();
    return id;
  }
  debug('profile_id_not_in_response', { topLevelKeys: Object.keys(body).slice(0, 20) });
  return null;
}

async function fetchAllProjects({ pageSize = 500, maxPages = 10, useFilters = true } = {}) {
  if (!config.cookie) throw new Error('no_cookie');
  const profileId = await discoverProfileId();
  if (!profileId) throw new Error('no_profile_id');

  const f = config.filters;
  const all = [];
  let pagesFetched = 0;

  for (let page = 1; page <= maxPages; page++) {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('pageSize', String(pageSize));
    // totalQuestions and dollarPerQuestion are client-side sorts — send publishedAt to the API
    const API_SORTS = ['v4Score', 'publishedAt', 'respondentRemuneration', 'timeMinutesRequired'];
    const apiSort = (useFilters && f.sort && API_SORTS.includes(f.sort)) ? f.sort : 'publishedAt';
    params.set('sort', apiSort);
    params.set('showEligible', String(useFilters ? (f.showEligible ?? true) : true));
    if (useFilters) {
      for (const k of (f.kindsOfResearchStudy || [])) params.append('kindsOfResearchStudy', k);
    }

    const { res, isJson } = await respondentFetch(
      `/next/v4/participant/matching/projects/search/profiles/${profileId}`,
      { query: params.toString() },
    );
    if (!isJson) throw new Error('session_expired');
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.errorDetails || `http_${res.status}`);
    }

    const data = await res.json();
    const items = extractResults(data);
    if (page === 1) debug('fetch_projects_first_page', { count: items.length, topLevelKeys: Object.keys(data).slice(0, 10) });

    pagesFetched++;
    if (items.length === 0) break;
    all.push(...items);
    if (items.length < pageSize) break;
  }

  return { projects: all, pagesFetched };
}

function extractResults(data) {
  if (Array.isArray(data)) return data;
  return data.results ?? data.projects ?? data.data ?? data.items ?? data.docs ?? [];
}

async function hideProject(id) {
  if (!/^[a-zA-Z0-9_-]{8,64}$/.test(id)) {
    return { ok: false, status: 400, error: 'invalid_id' };
  }
  const { res, isJson } = await respondentFetch(`/next/v4/participant/projects/hide/${id}`, { method: 'POST' });
  if (res.ok) return { ok: true, status: res.status };
  if (res.status === 404 || res.status === 409) {
    return { ok: true, status: res.status, alreadyHidden: true };
  }
  let bodySnippet = '';
  try {
    bodySnippet = isJson ? JSON.stringify(await res.json()).slice(0, 200) : (await res.text()).slice(0, 200);
  } catch {}
  debug('hide_failed', { id, upstreamStatus: res.status, bodySnippet });
  return { ok: false, status: res.status, error: `upstream_${res.status}`, bodySnippet };
}

// ── Auto-hide / keep-alive runners ────────────────────────
const HIDE_THROTTLE_MS = 250;
const HIDE_MAX_PER_RUN = 200;

let autoHideInFlight = false;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function runAutoHide({ dryRun = false } = {}) {
  if (autoHideInFlight) {
    debug('auto_hide_skipped_in_flight');
    return { ok: false, error: 'already_running' };
  }
  autoHideInFlight = true;

  debug('auto_hide_start', { dryRun });
  try {
    const { projects } = await fetchAllProjects({ useFilters: false });

    const matches = projects.map(p => ({
      id: getProjectId(p),
      title: getTitle(p),
      reason: whyHide(p, config.filters),
    })).filter(m => m.reason && m.id);

    debug('auto_hide_matches', { total: projects.length, toHide: matches.length, dryRun });

    if (dryRun) return { ok: true, dryRun: true, scanned: projects.length, matches };

    const cap = Math.max(1, Math.min(500, Number(config.autoHide.maxPerRun) || HIDE_MAX_PER_RUN));
    const toProcess = matches.slice(0, cap);
    const skipped = matches.length - toProcess.length;

    const results = [];
    let bumped = 0;
    for (const m of toProcess) {
      const r = await hideProject(m.id);
      results.push({ id: m.id, title: m.title, reason: m.reason, ...r });
      if (r.ok && !r.alreadyHidden) bumped++;
      await sleep(HIDE_THROTTLE_MS);
    }

    const summary = {
      scanned: projects.length,
      matched: matches.length,
      hidden: results.filter(r => r.ok).length,
      errors: results.filter(r => !r.ok).length,
      skipped,
    };
    config.totalHidden = (config.totalHidden || 0) + bumped;
    config.autoHide.lastRunAt = new Date().toISOString();
    config.autoHide.lastRunResult = summary;
    saveConfig();
    debug('auto_hide_done', summary);
    return { ok: true, results, ...summary };
  } catch (err) {
    config.autoHide.lastRunAt = new Date().toISOString();
    config.autoHide.lastRunResult = { error: err.message };
    saveConfig();
    debug('auto_hide_error', { error: err.message });
    return { ok: false, error: err.message };
  } finally {
    autoHideInFlight = false;
  }
}

async function runKeepAlive() {
  if (!config.cookie) {
    config.keepAlive.lastRunAt = new Date().toISOString();
    config.keepAlive.lastRunResult = { error: 'no_cookie' };
    saveConfig();
    return { ok: false, error: 'no_cookie' };
  }
  try {
    const { res, isJson } = await respondentFetch('/v2/profiles/me');
    const ok = res.ok && isJson;
    config.keepAlive.lastRunAt = new Date().toISOString();
    config.keepAlive.lastRunResult = ok ? { status: res.status } : { error: 'session_expired', status: res.status };
    saveConfig();
    debug('keep_alive_run', config.keepAlive.lastRunResult);
    return { ok, status: res.status };
  } catch (err) {
    config.keepAlive.lastRunAt = new Date().toISOString();
    config.keepAlive.lastRunResult = { error: err.message };
    saveConfig();
    return { ok: false, error: err.message };
  }
}

// ── Cron scheduling ───────────────────────────────────────
let autoHideTask = null;
let keepAliveTask = null;

function reschedule(section, taskRef, runner, label) {
  if (taskRef.task) { taskRef.task.stop(); taskRef.task = null; }
  if (!section.enabled) { debug(`${label}_disabled`); return; }
  const cronExpr = resolveCron(section);
  if (!isValidCron(cronExpr)) { debug(`${label}_invalid_cron`, { cron: cronExpr }); return; }
  taskRef.task = cron.schedule(cronExpr, runner, { scheduled: true });
  debug(`${label}_scheduled`, { schedule: section.schedule, cron: cronExpr });
}

const autoHideRef  = { task: null };
const keepAliveRef = { task: null };
const rescheduleAutoHide  = () => reschedule(config.autoHide,  autoHideRef,  runAutoHide,  'auto_hide');
const rescheduleKeepAlive = () => reschedule(config.keepAlive, keepAliveRef, runKeepAlive, 'keep_alive');

// ── Express app ───────────────────────────────────────────
export const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(express.static(join(__dirname, 'public')));

app.get('/api/config', (req, res) => {
  const { cookie, ...safe } = config;
  res.json({
    ...safe,
    hasCookie: Boolean(cookie),
    schedules: SCHEDULE_OPTIONS,
    cookieName: COOKIE_NAME,
    nextRuns: {
      keepAlive: config.keepAlive.enabled ? nextRunForExpr(resolveCron(config.keepAlive)) : null,
      autoHide:  config.autoHide.enabled  ? nextRunForExpr(resolveCron(config.autoHide))  : null,
    },
    resolvedCrons: {
      keepAlive: resolveCron(config.keepAlive),
      autoHide:  resolveCron(config.autoHide),
    },
  });
});

app.post('/api/config/filters', (req, res) => {
  const incoming = { ...config.filters, ...req.body };
  if (incoming.sort && !VALID_SORTS.includes(incoming.sort)) incoming.sort = 'publishedAt';
  config.filters = incoming;
  saveConfig();
  res.json({ ok: true, filters: config.filters });
});

app.post('/api/config/cookie', (req, res) => {
  const { cookie } = req.body ?? {};
  if (!cookie || typeof cookie !== 'string') return res.status(400).json({ error: 'cookie_required' });
  config.cookie = normalizeCookie(cookie);
  saveConfig();
  res.json({ ok: true });
});

app.post('/api/config/profile-id', (req, res) => {
  config.profileId = ((req.body?.profileId) || '').trim();
  saveConfig();
  res.json({ ok: true, profileId: config.profileId });
});

app.post('/api/config/auto-hide', (req, res) => {
  const { enabled, schedule, customCron, maxPerRun } = req.body ?? {};
  if (typeof enabled === 'boolean') config.autoHide.enabled = enabled;
  if (maxPerRun !== undefined) {
    const n = Math.max(1, Math.min(20, Math.floor(Number(maxPerRun)) || 1));
    config.autoHide.maxPerRun = n;
  }
  if (schedule === 'custom') {
    const expr = (customCron || config.autoHide.customCron || '').trim();
    if (!isValidCron(expr)) {
      return res.status(400).json({ error: 'invalid_custom_cron', detail: 'Provide a valid 5- or 6-field cron expression.' });
    }
    config.autoHide.schedule = 'custom';
    config.autoHide.customCron = expr;
  } else if (schedule && SCHEDULE_OPTIONS.some(o => o.key === schedule)) {
    config.autoHide.schedule = schedule;
  }
  saveConfig();
  rescheduleAutoHide();
  res.json({ ok: true, autoHide: config.autoHide });
});

app.post('/api/config/keep-alive', (req, res) => {
  const { enabled, schedule } = req.body ?? {};
  if (typeof enabled === 'boolean') config.keepAlive.enabled = enabled;
  if (schedule && SCHEDULE_OPTIONS.some(o => o.key === schedule)) config.keepAlive.schedule = schedule;
  saveConfig();
  rescheduleKeepAlive();
  res.json({ ok: true, keepAlive: config.keepAlive });
});

app.get('/api/profile', async (req, res) => {
  try {
    const id = await discoverProfileId();
    if (!id) return res.status(404).json({ error: 'not_found' });
    res.json({ profileId: id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/projects', async (req, res) => {
  try {
    const { projects, pagesFetched } = await fetchAllProjects();
    res.json({ projects, pages: pagesFetched });
  } catch (err) {
    if (err.message === 'no_cookie' || err.message === 'session_expired') return res.status(401).json({ error: err.message });
    if (err.message === 'no_profile_id') return res.status(400).json({ error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/projects/:id/detail', async (req, res) => {
  if (!config.cookie) return res.status(401).json({ error: 'no_cookie' });
  const { id } = req.params;
  if (!/^[a-zA-Z0-9_-]{8,64}$/.test(id)) return res.status(400).json({ error: 'invalid_id' });

  const path = `/next/v4/participant/projects/view/${id}`;
  try {
    const { res: upRes, isJson } = await respondentFetch(path);
    debug('project_detail_fetch', { id, status: upRes.status });

    if (upRes.status === 401) return res.status(401).json({ error: 'session_expired' });
    if (upRes.status === 404) {
      res.status(404).json({ error: 'not_found' });
      return;
    }
    if (!isJson) {
      res.status(502).json({ error: 'unexpected_response' });
      return;
    }
    const body = await upRes.json();
    if (!upRes.ok) {
      debug('project_detail_error', { id, status: upRes.status });
      res.status(upRes.status).json(body);
      return;
    }
    debug('project_detail_ok', { id, screenerQuestionsLength: body?.response?.screenerQuestionsLength });
    res.json(body);
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

app.post('/api/projects/:id/hide', async (req, res) => {
  if (!config.cookie) return res.status(401).json({ error: 'no_cookie' });
  const applied = req.body?.applied === true;
  const result = await hideProject(req.params.id);
  if (result.ok && !result.alreadyHidden) {
    config.totalHidden = (config.totalHidden || 0) + 1;
    if (applied) config.totalApplied = (config.totalApplied || 0) + 1;
    saveConfig();
  }
  if (result.ok) return res.json({ ...result, totalHidden: config.totalHidden, totalApplied: config.totalApplied });
  res.status(result.status || 502).json(result);
});

app.post('/api/auto-hide/run', async (req, res) => {
  const dryRun = req.body?.dryRun === true;
  const result = await runAutoHide({ dryRun });
  res.status(result.ok || result.error === 'already_running' ? 200 : 500).json(result);
});

app.post('/api/keep-alive/run', async (req, res) => {
  const result = await runKeepAlive();
  res.status(result.ok ? 200 : 500).json(result);
});

// Raw upstream probe — lets you inspect what Respondent actually returns for any path.
// GET /api/debug/upstream?path=/next/participants/projects/SOME_ID
app.get('/api/debug/upstream', async (req, res) => {
  const { path } = req.query;
  if (!path || typeof path !== 'string') return res.status(400).json({ error: 'path_required' });
  if (!config.cookie) return res.status(401).json({ error: 'no_cookie' });
  try {
    const { res: upRes, isJson, ct } = await respondentFetch(path, {
      extraHeaders: {
        'referer': `${BASE_URL}/participant/dashboard`,
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      },
    });
    const raw = await upRes.text();
    let parsed = null;
    try { parsed = JSON.parse(raw); } catch {}
    res.json({
      status: upRes.status,
      contentType: ct,
      isJson,
      bodyLength: raw.length,
      bodySnippet: raw.slice(0, 2000),
      parsed,
    });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// Returns the raw first project from the list API so you can inspect its data structure.
app.get('/api/debug/first-project', async (req, res) => {
  if (!config.cookie) return res.status(401).json({ error: 'no_cookie' });
  try {
    const { projects } = await fetchAllProjects({ pageSize: 1, maxPages: 1 });
    if (!projects.length) return res.status(404).json({ error: 'no_projects' });
    res.json({ project: projects[0], keys: Object.keys(projects[0]) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/debug', (req, res) => {
  res.json({
    log: DEBUG_LOG,
    config: {
      hasCookie: Boolean(config.cookie),
      cookieLength: config.cookie?.length ?? 0,
      profileId: config.profileId,
      filters: config.filters,
      autoHide: config.autoHide,
      keepAlive: config.keepAlive,
      totalHidden: config.totalHidden,
    },
  });
});

// ── Boot ──────────────────────────────────────────────────
// Skip listening when imported by tests.
const isTest = process.env.NODE_ENV === 'test' || process.env.VITEST;
if (!isTest) {
  app.listen(PORT, () => {
    console.log(`App running at http://localhost:${PORT}`);
    console.log(`Config:    ${CONFIG_PATH}`);
    console.log(`Cookie:    ${config.cookie ? `present (${config.cookie.length} chars)` : 'MISSING — set via UI'}`);
    console.log(`Profile:   ${config.profileId || '(none — will discover)'}`);
    console.log(`AutoHide:  ${config.autoHide.enabled ? `ON (${config.autoHide.schedule})` : 'off'}`);
    console.log(`KeepAlive: ${config.keepAlive.enabled ? `ON (${config.keepAlive.schedule})` : 'off'}`);

    rescheduleAutoHide();
    rescheduleKeepAlive();

    if (config.keepAlive.enabled && config.cookie) {
      runKeepAlive().catch((err) => debug('keep_alive_boot_error', { error: err.message }));
    }
  });
}
