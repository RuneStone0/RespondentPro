/**
 * Screener answer helpers.
 *
 * I/O (load/save/append) is handled by the store (src/lib/store/).
 * This module only contains the pure query helper used by the server.
 */

/**
 * Find the most-recent answer for a given question text.
 * Matches by normalised text (lowercase, collapsed whitespace).
 *
 * @param {string}    questionText
 * @param {object[]}  history  — result of store.getAnswers()
 * @returns {string|string[]|null}
 */
export function findSuggestion(questionText, history) {
  const needle = normalise(questionText);
  // Iterate newest-first
  for (let i = history.length - 1; i >= 0; i--) {
    const match = (history[i].answers || []).find(
      a => normalise(a.questionText) === needle,
    );
    if (match !== undefined) return match.answer;
  }
  return null;
}

function normalise(text) {
  return (text || '').toLowerCase().replace(/\s+/g, ' ').trim();
}
