import { describe, it, expect } from 'vitest';
import { applyMigrations, VALID_SORTS } from '../src/lib/migrations.js';

function freshConfig(overrides = {}) {
  return {
    cookie: '',
    filters: { sort: 'publishedAt' },
    keepAlive: { enabled: false },
    _migrations: {},
    ...overrides,
  };
}

describe('VALID_SORTS', () => {
  it('contains the upstream-accepted and client-side sort values', () => {
    expect(VALID_SORTS).toEqual([
      'v4Score', 'publishedAt', 'respondentRemuneration', 'timeMinutesRequired',
      'totalQuestions', 'dollarPerQuestion',
    ]);
  });
  it('is frozen', () => {
    expect(Object.isFrozen(VALID_SORTS)).toBe(true);
  });
});

describe('applyMigrations', () => {
  it('is a no-op on a fully migrated config', () => {
    const c = freshConfig({
      cookie: 'respondent.session.sid=abc',
      _migrations: { keepAliveDefaultOn: true },
      keepAlive: { enabled: true },
    });
    const { dirty, applied } = applyMigrations(c);
    expect(dirty).toBe(false);
    expect(applied).toEqual([]);
  });

  describe('cookie prefix migration', () => {
    it('prepends the cookie name to a bare value', () => {
      const c = freshConfig({ cookie: 'bareValue', _migrations: { keepAliveDefaultOn: true } });
      const { dirty, applied } = applyMigrations(c);
      expect(c.cookie).toBe('respondent.session.sid=bareValue');
      expect(dirty).toBe(true);
      expect(applied).toContain('cookie_added_respondent.session.sid_prefix');
    });

    it('leaves an already-prefixed cookie alone', () => {
      const c = freshConfig({ cookie: 'name=value', _migrations: { keepAliveDefaultOn: true } });
      applyMigrations(c);
      expect(c.cookie).toBe('name=value');
    });

    it('does not flag dirty when cookie is empty (normalization is a no-op)', () => {
      const c = freshConfig({ _migrations: { keepAliveDefaultOn: true } });
      const { dirty } = applyMigrations(c);
      expect(dirty).toBe(false);
    });
  });

  describe('sort migration', () => {
    it('resets unknown sort values to publishedAt', () => {
      const c = freshConfig({
        filters: { sort: 'incentive' },           // legacy
        _migrations: { keepAliveDefaultOn: true },
      });
      const { dirty, applied } = applyMigrations(c);
      expect(c.filters.sort).toBe('publishedAt');
      expect(dirty).toBe(true);
      expect(applied).toContain('sort_reset_to_publishedAt');
    });

    it('keeps valid sort values', () => {
      for (const s of VALID_SORTS) {
        const c = freshConfig({
          filters: { sort: s },
          _migrations: { keepAliveDefaultOn: true },
        });
        applyMigrations(c);
        expect(c.filters.sort).toBe(s);
      }
    });

    it('does nothing when filters or sort is missing', () => {
      const c1 = freshConfig({ filters: {}, _migrations: { keepAliveDefaultOn: true } });
      applyMigrations(c1);
      expect(c1.filters.sort).toBeUndefined();

      const c2 = freshConfig({ filters: null, _migrations: { keepAliveDefaultOn: true } });
      applyMigrations(c2);
      expect(c2.filters).toBeNull();
    });
  });

  describe('keep-alive default-on migration', () => {
    it('enables keep-alive on first run', () => {
      const c = freshConfig({ keepAlive: { enabled: false } });
      const { applied } = applyMigrations(c);
      expect(c.keepAlive.enabled).toBe(true);
      expect(c._migrations.keepAliveDefaultOn).toBe(true);
      expect(applied).toContain('keepalive_enabled_by_default');
    });

    it('only flips once — respects user disabling after migration', () => {
      const c = freshConfig({
        keepAlive: { enabled: false },
        _migrations: { keepAliveDefaultOn: true },
      });
      const { dirty } = applyMigrations(c);
      expect(c.keepAlive.enabled).toBe(false);
      expect(dirty).toBe(false);
    });

    it('leaves an already-enabled keepAlive alone but still marks migration as run', () => {
      const c = freshConfig({ keepAlive: { enabled: true } });
      const { applied } = applyMigrations(c);
      expect(c.keepAlive.enabled).toBe(true);
      expect(c._migrations.keepAliveDefaultOn).toBe(true);
      expect(applied).toContain('keepalive_default_flag_set');
    });

    it('creates keepAlive object if missing', () => {
      const c = freshConfig({ keepAlive: undefined });
      applyMigrations(c);
      expect(c.keepAlive.enabled).toBe(true);
    });

    it('creates _migrations object if missing', () => {
      const c = freshConfig({ _migrations: undefined });
      applyMigrations(c);
      expect(c._migrations.keepAliveDefaultOn).toBe(true);
    });
  });

  it('reports multiple applied migrations together', () => {
    const c = freshConfig({
      cookie: 'bare',
      filters: { sort: 'incentive' },
      keepAlive: { enabled: false },
      _migrations: {},
    });
    const { dirty, applied } = applyMigrations(c);
    expect(dirty).toBe(true);
    expect(applied.length).toBeGreaterThanOrEqual(3);
  });
});
