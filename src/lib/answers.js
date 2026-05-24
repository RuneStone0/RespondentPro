/**
 * Screener answer history — read/write data/answers.json.
 *
 * Schema:
 * [
 *   {
 *     projectId:   string,
 *     projectName: string,
 *     answeredAt:  ISO string,
 *     answers: [
 *       { questionId: string, questionText: string, questionType: number, answer: string | string[] }
 *     ]
 *   }
 * ]
 */
import { existsSync, readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ANSWERS_PATH = join(__dirname, '../../data/answers.json');

export function loadAnswers() {
  if (!existsSync(ANSWERS_PATH)) return [];
  try {
    return JSON.parse(readFileSync(ANSWERS_PATH, 'utf8'));
  } catch {
    return [];
  }
}

export function saveAnswers(entries) {
  writeFileSync(ANSWERS_PATH, JSON.stringify(entries, null, 2), 'utf8');
}

/**
 * Append a completed screener session to the history file.
 * @param {{ projectId, projectName, answers }} session
 * @returns {object[]} updated history array
 */
export function appendSession(session) {
  const history = loadAnswers();
  history.push({ ...session, answeredAt: new Date().toISOString() });
  saveAnswers(history);
  return history;
}

/**
 * Find the most-recent answer for a given question text.
 * Matches by normalised text (lowercase, collapsed whitespace).
 *
 * @param {string} questionText
 * @param {object[]} history  — result of loadAnswers()
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
