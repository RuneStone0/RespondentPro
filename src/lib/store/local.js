/**
 * Local (file-based) data store.
 * Stores config and answer history as JSON files under `dataDir`.
 *
 * Files:
 *   <dataDir>/config.json  — application config
 *   <dataDir>/answers.json — screener answer history
 */
import { existsSync, readFileSync, writeFileSync } from 'fs';
import { join } from 'path';

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
  const configPath  = join(dataDir, 'config.json');
  const answersPath = join(dataDir, 'answers.json');

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
    writeFileSync(configPath, JSON.stringify(cfg, null, 2), 'utf8');
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

  return { getConfig, saveConfig, getAnswers, appendSession };
}
