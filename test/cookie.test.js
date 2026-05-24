import { describe, it, expect } from 'vitest';
import { normalizeCookie, COOKIE_NAME } from '../src/lib/cookie.js';

describe('COOKIE_NAME', () => {
  it('is the Respondent.io session cookie name', () => {
    expect(COOKIE_NAME).toBe('respondent.session.sid');
  });
});

describe('normalizeCookie', () => {
  it('returns empty string for falsy inputs', () => {
    expect(normalizeCookie('')).toBe('');
    expect(normalizeCookie(null)).toBe('');
    expect(normalizeCookie(undefined)).toBe('');
    expect(normalizeCookie(0)).toBe('');
  });

  it('returns empty string for whitespace-only input', () => {
    expect(normalizeCookie('   ')).toBe('');
    expect(normalizeCookie('\n\t  ')).toBe('');
  });

  it('prepends the canonical cookie name when missing', () => {
    expect(normalizeCookie('s%3AfakeValue')).toBe('respondent.session.sid=s%3AfakeValue');
  });

  it('passes through a value that already has name=value', () => {
    expect(normalizeCookie('respondent.session.sid=abc123')).toBe('respondent.session.sid=abc123');
  });

  it('does not double-prefix an arbitrary name=value pair (trusts as-is)', () => {
    // Advanced users may legitimately want a different cookie name
    expect(normalizeCookie('other=xyz')).toBe('other=xyz');
  });

  it('trims surrounding whitespace before deciding', () => {
    expect(normalizeCookie('  bareValue  ')).toBe('respondent.session.sid=bareValue');
    expect(normalizeCookie('  name=val  ')).toBe('name=val');
  });

  it('coerces non-string inputs to string', () => {
    // Number coerces to "12345"
    expect(normalizeCookie(12345)).toBe('respondent.session.sid=12345');
  });
});
