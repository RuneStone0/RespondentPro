// Filter-rule matching — decides whether a project should be hidden.
import { getTitle, getDescription, getDuration, getIncentive, getHourlyRate, getScreenerQuestionCount } from './project-fields.js';

/**
 * Returns a human-readable reason string if the project matches a hide rule,
 * otherwise `null`.
 *
 * Rules (any one matching → hide):
 *   - keyword present in title or description (case-insensitive)
 *   - minHourlyRate set AND project's hourly rate is positive but below it
 *   - minIncentive set AND project's incentive is positive but below it
 *   - maxDuration set AND project's duration is positive and above it
 *   - minDuration set AND project's duration is positive and below it
 *
 * @param {object} project
 * @param {{keywords?: string[], minHourlyRate?: number, minIncentive?: number,
 *          minDuration?: number, maxDuration?: number, maxQuestions?: number}} filters
 * @returns {string|null}
 */
export function whyHide(project, filters = {}) {
  const title = getTitle(project).toLowerCase();
  const desc = getDescription(project).toLowerCase();
  const hourly = getHourlyRate(project);
  const incentive = getIncentive(project);
  const duration = getDuration(project);
  const questions = getScreenerQuestionCount(project);

  for (const kw of (filters.keywords || [])) {
    if (!kw) continue;
    const k = String(kw).toLowerCase();
    if (title.includes(k) || desc.includes(k)) return `keyword "${kw}"`;
  }
  if (filters.minHourlyRate > 0 && hourly > 0 && hourly < filters.minHourlyRate) {
    return `$${hourly}/hr < min $${filters.minHourlyRate}`;
  }
  if (filters.minIncentive > 0 && incentive > 0 && incentive < filters.minIncentive) {
    return `incentive $${incentive} < min $${filters.minIncentive}`;
  }
  if (filters.maxDuration > 0 && duration > 0 && duration > filters.maxDuration) {
    return `${duration}min > max ${filters.maxDuration}min`;
  }
  if (filters.minDuration > 0 && duration > 0 && duration < filters.minDuration) {
    return `${duration}min < min ${filters.minDuration}min`;
  }
  if (filters.maxQuestions > 0 && questions > 0 && questions > filters.maxQuestions) {
    return `${questions}q > max ${filters.maxQuestions}q`;
  }
  return null;
}
