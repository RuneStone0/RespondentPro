// Cookie helpers — pure functions, no I/O.

export const COOKIE_NAME = 'respondent.session.sid';

/**
 * Accept either a bare cookie value or a full "name=value" string and return
 * a properly-formed cookie header value. If `raw` already contains an `=`
 * we trust it as-is; otherwise we prepend the canonical Respondent cookie name.
 *
 * @param {string|null|undefined} raw
 * @returns {string}
 */
export function normalizeCookie(raw) {
  if (!raw) return '';
  const trimmed = String(raw).trim();
  if (!trimmed) return '';
  if (trimmed.includes('=')) return trimmed;
  return `${COOKIE_NAME}=${trimmed}`;
}
