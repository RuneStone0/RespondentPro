// Pure field extraction from Respondent.io project shapes.
// Handles multiple possible field names and types defensively.

/**
 * Coerce many shapes to a number. Strings get their first numeric run parsed;
 * objects with `amount`/`value` are unwrapped; everything else falls back to 0.
 *
 * @param {*} raw
 * @returns {number}
 */
export function toNumber(raw) {
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  if (typeof raw === 'string') {
    const m = raw.match(/[\d.]+/);
    return m ? Number(m[0]) : 0;
  }
  if (raw && typeof raw === 'object') {
    return Number(raw.amount ?? raw.value ?? 0) || 0;
  }
  return 0;
}

export const getProjectId = (p) => p?.id || p?._id || p?.projectId || p?.project?._id || '';
export const getTitle = (p) => p?.name || p?.title || p?.projectName || p?.project?.title || '';
export const getDescription = (p) => p?.description || p?.summary || p?.shortDescription || '';

export const getDuration = (p) =>
  Number(p?.timeMinutesRequired || p?.duration || p?.sessionLength || p?.lengthInMinutes || p?.length || 0);

export const getIncentive = (p) =>
  toNumber(p?.respondentRemuneration ?? p?.incentive ?? p?.compensation ?? p?.amount ?? 0);

export function getHourlyRate(p) {
  const direct = toNumber(p?.hourlyRate ?? p?.hourly_rate ?? p?.pay ?? p?.rate ?? 0);
  if (direct > 0) return direct;
  const inc = getIncentive(p);
  const dur = getDuration(p);
  return inc > 0 && dur > 0 ? Math.round((inc / dur) * 60) : 0;
}
