// Profile-id picker — walks the response wrapper used by Respondent.io.

/**
 * Extract a profile id from a (possibly nested) /v2/profiles/me response.
 * Respondent wraps responses as { success, response: { profile: {...} } }.
 *
 * @param {object|null|undefined} body
 * @returns {string|null}
 */
export function pickProfileId(body) {
  if (!body || typeof body !== 'object') return null;
  const candidates = [body, body.response, body.data, body.profile, body.response?.profile];
  for (const c of candidates) {
    if (!c || typeof c !== 'object') continue;
    const id = c._id || c.id || c.profileId;
    if (id && typeof id === 'string') return id;
  }
  return null;
}
