// Config migrations — one-time mutations applied on load.
import { normalizeCookie, COOKIE_NAME } from './cookie.js';

export const VALID_SORTS = Object.freeze([
  'v4Score', 'publishedAt', 'respondentRemuneration', 'timeMinutesRequired',
  'totalQuestions', 'dollarPerQuestion',
]);

/**
 * Apply one-time migrations to a config object. Mutates and also returns a
 * summary describing what changed; caller decides whether to persist.
 *
 * @param {object} config
 * @returns {{dirty: boolean, applied: string[]}}
 */
export function applyMigrations(config) {
  const applied = [];

  // 1) Cookie name prefix
  const migrated = normalizeCookie(config.cookie);
  if (migrated !== (config.cookie || '')) {
    config.cookie = migrated;
    applied.push(`cookie_added_${COOKIE_NAME}_prefix`);
  }

  // 2) Drop sort values the API no longer accepts
  if (config.filters?.sort && !VALID_SORTS.includes(config.filters.sort)) {
    config.filters.sort = 'publishedAt';
    applied.push('sort_reset_to_publishedAt');
  }

  // 3) One-time default-on for keep-alive
  config._migrations = config._migrations || {};
  if (!config._migrations.keepAliveDefaultOn) {
    config.keepAlive = config.keepAlive || {};
    if (!config.keepAlive.enabled) {
      config.keepAlive.enabled = true;
      applied.push('keepalive_enabled_by_default');
    }
    config._migrations.keepAliveDefaultOn = true;
    if (!applied.includes('keepalive_enabled_by_default')) {
      applied.push('keepalive_default_flag_set');
    }
  }

  // 4) One-time default-on for hiding not-eligible projects
  if (!config._migrations.hideNotEligibleDefaultOn) {
    if (config.filters && config.filters.hideNotEligible === undefined) {
      config.filters.hideNotEligible = true;
      applied.push('hide_not_eligible_enabled_by_default');
    }
    config._migrations.hideNotEligibleDefaultOn = true;
  }

  return { dirty: applied.length > 0, applied };
}
