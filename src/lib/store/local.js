/**
 * Local (file-based) data store.
 * Stores config and answer history as JSON files under `dataDir`.
 *
 * Files:
 *   <dataDir>/config.json   — application config (keywords omitted)
 *   <dataDir>/keywords.json — exclude/priority keyword lists
 *   <dataDir>/answers.json  — screener answer history
 */
import { existsSync, readFileSync, writeFileSync, statSync } from 'fs';
import { join } from 'path';
import { EMPTY_KEYWORDS, stripKeywordsFromConfig } from './keywords.js';

function mergeConfig(defaults, stored) {
  if (!stored) return structuredClone(defaults);
  return {
    ...defaults,
    ...stored,
    filters:   { ...defaults.filters,   ...(stored.filters   || {}) },
    autoHide:  { ...defaults.autoHide,  ...(stored.autoHide  || {}) },
    keepAlive: { ...defaults.keepAlive, ...(stored.keepAlive || {}) },
  };
}

export function createLocalStore(dataDir, defaults) {
  const configPath   = join(dataDir, 'config.json');
  const keywordsPath = join(dataDir, 'keywords.json');
  const answersPath  = join(dataDir, 'answers.json');

  async function getConfig() {
    if (!existsSync(configPath)) return structuredClone(defaults);
    try {
      const stored = JSON.parse(readFileSync(configPath, 'utf8'));
      return mergeConfig(defaults, stored);
    } catch (e) {
      console.error('Failed to load config, using defaults:', e.message);
      return structuredClone(defaults);
    }
  }

  async function saveConfig(cfg) {
    writeFileSync(configPath, JSON.stringify(stripKeywordsFromConfig(cfg), null, 2), 'utf8');
  }

  async function getKeywords() {
    if (existsSync(keywordsPath)) {
      try {
        const stored = JSON.parse(readFileSync(keywordsPath, 'utf8'));
        return {
          exclude: stored.exclude || [],
          priority: stored.priority || [],
        };
      } catch (e) {
        console.error('Failed to load keywords, using defaults:', e.message);
      }
    }

    // One-time fallback: lift keywords out of a legacy config.json.
    if (existsSync(configPath)) {
      try {
        const stored = JSON.parse(readFileSync(configPath, 'utf8'));
        const lifted = {
          exclude: stored.filters?.keywords || [],
          priority: stored.filters?.priorityKeywords || [],
        };
        if (lifted.exclude.length || lifted.priority.length) {
          await saveKeywords(lifted);
        }
        return lifted;
      } catch {}
    }

    return { ...EMPTY_KEYWORDS };
  }

  async function saveKeywords({ exclude = [], priority = [] } = {}) {
    writeFileSync(keywordsPath, JSON.stringify({ exclude, priority }, null, 2), 'utf8');
  }

  async function getAnswers() {
    if (!existsSync(answersPath)) return [];
    try {
      return JSON.parse(readFileSync(answersPath, 'utf8'));
    } catch {
      return [];
    }
  }

  async function appendSession(session) {
    const history = await getAnswers();
    history.push({ ...session, answeredAt: new Date().toISOString() });
    writeFileSync(answersPath, JSON.stringify(history, null, 2), 'utf8');
    return history;
  }

  async function ping() {
    statSync(dataDir); // throws if the directory is gone or unreadable
    return { mode: 'local', path: dataDir };
  }

  return { getConfig, saveConfig, getKeywords, saveKeywords, getAnswers, appendSession, ping };
}
