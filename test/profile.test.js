import { describe, it, expect } from 'vitest';
import { pickProfileId } from '../src/lib/profile.js';

describe('pickProfileId', () => {
  it('returns null for falsy / non-object input', () => {
    expect(pickProfileId(null)).toBe(null);
    expect(pickProfileId(undefined)).toBe(null);
    expect(pickProfileId('string')).toBe(null);
    expect(pickProfileId(42)).toBe(null);
  });

  it('finds id at top level', () => {
    expect(pickProfileId({ id: 'abc' })).toBe('abc');
    expect(pickProfileId({ _id: 'def' })).toBe('def');
    expect(pickProfileId({ profileId: 'ghi' })).toBe('ghi');
  });

  it('finds id inside .response (Respondent wrapper)', () => {
    expect(pickProfileId({ response: { id: 'r1' } })).toBe('r1');
  });

  it('finds id inside .data', () => {
    expect(pickProfileId({ data: { _id: 'd1' } })).toBe('d1');
  });

  it('finds id inside .profile', () => {
    expect(pickProfileId({ profile: { id: 'p1' } })).toBe('p1');
  });

  it('finds id inside .response.profile (the real Respondent shape)', () => {
    expect(pickProfileId({
      success: true,
      response: { profile: { id: '691f593b2e2ac1bd7fa84915' } },
    })).toBe('691f593b2e2ac1bd7fa84915');
  });

  it('returns null when no id is present at any level', () => {
    expect(pickProfileId({})).toBe(null);
    expect(pickProfileId({ response: {} })).toBe(null);
    expect(pickProfileId({ response: { profile: {} } })).toBe(null);
  });

  it('ignores non-string id values', () => {
    expect(pickProfileId({ id: 123 })).toBe(null);
    expect(pickProfileId({ id: null })).toBe(null);
    expect(pickProfileId({ response: { profile: { id: { nested: true } } } })).toBe(null);
  });

  it('prefers earlier candidates (top-level > response > data > profile > response.profile)', () => {
    const b = {
      id: 'top',
      response: { id: 'r', profile: { id: 'rp' } },
      data: { id: 'd' },
      profile: { id: 'p' },
    };
    expect(pickProfileId(b)).toBe('top');
  });
});
