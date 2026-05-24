// Schedule + cron helpers — pure functions.
import cron from 'node-cron';
import cronstrue from 'cronstrue';
import { CronExpressionParser } from 'cron-parser';

export const SCHEDULES = Object.freeze({
  '15m':    '*/15 * * * *',
  '30m':    '*/30 * * * *',
  'hourly': '0 * * * *',
  '3h':     '0 */3 * * *',
  '6h':     '0 */6 * * *',
  'daily':  '0 9 * * *',
});

// Human-readable labels via cronstrue, computed once at import.
export const SCHEDULE_OPTIONS = Object.entries(SCHEDULES).map(([key, cronExpr]) => ({
  key,
  cron: cronExpr,
  label: cronstrue.toString(cronExpr, { verbose: false }),
}));

/**
 * Validate a cron expression (5- or 6-field).
 * @param {string} expr
 * @returns {boolean}
 */
export function isValidCron(expr) {
  if (!expr || typeof expr !== 'string') return false;
  try {
    return cron.validate(expr);
  /* c8 ignore start */
  } catch {
    return false;
  }
  /* c8 ignore stop */
}

/**
 * Resolve the cron expression for a section ({schedule, customCron}).
 * If schedule === 'custom' and customCron is set, returns customCron.
 * Otherwise looks up the preset; falls back to hourly when missing.
 *
 * @param {{schedule?: string, customCron?: string}} section
 * @returns {string} cron expression
 */
export function resolveCron(section) {
  if (!section) return SCHEDULES.hourly;
  if (section.schedule === 'custom' && section.customCron) return section.customCron;
  return SCHEDULES[section.schedule] || SCHEDULES.hourly;
}

/**
 * Build a cron expression from a count + unit ('s'|'m'|'h').
 * Clamps N to [1, 3600]. Falls back to minutes for unknown units.
 *
 * @param {number|string} n
 * @param {'s'|'m'|'h'} unit
 * @returns {string} cron expression
 */
export function buildCustomCron(n, unit) {
  const num = Math.max(1, Math.min(3600, Math.floor(Number(n)) || 1));
  if (unit === 's') return `*/${num} * * * * *`;
  if (unit === 'h') return `0 */${num} * * *`;
  return `*/${num} * * * *`; // minutes (default)
}

/**
 * Next-fire timestamp for a cron expression, as an ISO string. Returns null
 * if the expression is invalid.
 *
 * @param {string} expr
 * @returns {string|null}
 */
export function nextRunForExpr(expr) {
  if (!expr) return null;
  try {
    return CronExpressionParser.parse(expr).next().toISOString();
  } catch {
    return null;
  }
}
