/** Shared helpers for exclude/priority keyword storage (separate from config.json). */

export const EMPTY_KEYWORDS = { exclude: [], priority: [] };

export function stripKeywordsFromConfig(cfg) {
  return {
    ...cfg,
    filters: {
      ...cfg.filters,
      keywords: [],
      priorityKeywords: [],
    },
  };
}

export function keywordsFromFilters(filters = {}) {
  return {
    exclude: filters.keywords || [],
    priority: filters.priorityKeywords || [],
  };
}

export function applyKeywordsToFilters(filters, { exclude = [], priority = [] } = {}) {
  return {
    ...filters,
    keywords: exclude,
    priorityKeywords: priority,
  };
}
