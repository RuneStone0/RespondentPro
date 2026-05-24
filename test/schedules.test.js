import { describe, it, expect } from 'vitest';
import {
  SCHEDULES,
  SCHEDULE_OPTIONS,
  isValidCron,
  resolveCron,
  buildCustomCron,
  nextRunForExpr,
} from '../src/lib/schedules.js';

describe('SCHEDULES', () => {
  it('maps every preset key to a valid 5-field cron', () => {
    for (const [key, expr] of Object.entries(SCHEDULES)) {
      expect(isValidCron(expr), `${key}: ${expr}`).toBe(true);
    }
  });

  it('is frozen', () => {
    expect(Object.isFrozen(SCHEDULES)).toBe(true);
  });
});

describe('SCHEDULE_OPTIONS', () => {
  it('has one entry per preset, each with key/cron/label', () => {
    const keys = Object.keys(SCHEDULES);
    expect(SCHEDULE_OPTIONS).toHaveLength(keys.length);
    for (const opt of SCHEDULE_OPTIONS) {
      expect(opt.key).toBeTypeOf('string');
      expect(opt.cron).toBeTypeOf('string');
      expect(opt.label).toBeTypeOf('string');
      expect(opt.label.length).toBeGreaterThan(0);
    }
  });

  it('preserves preset ordering', () => {
    expect(SCHEDULE_OPTIONS.map(o => o.key)).toEqual(Object.keys(SCHEDULES));
  });
});

describe('isValidCron', () => {
  it.each([
    ['0 * * * *', true],
    ['*/15 * * * *', true],
    ['*/60 * * * * *', true],     // 6-field with seconds
    ['0 9 * * 1-5', true],         // weekdays
  ])('returns %s for %s → %s', (expr, expected) => {
    expect(isValidCron(expr)).toBe(expected);
  });

  it.each([
    ['', false],
    ['not a cron', false],
    ['* * *', false],
    [null, false],
    [undefined, false],
    [123, false],
    [{}, false],
  ])('rejects invalid input %s', (expr, expected) => {
    expect(isValidCron(expr)).toBe(expected);
  });
});

describe('resolveCron', () => {
  it('returns hourly when section is null/undefined', () => {
    expect(resolveCron(null)).toBe(SCHEDULES.hourly);
    expect(resolveCron(undefined)).toBe(SCHEDULES.hourly);
  });

  it('returns the preset for a known schedule key', () => {
    expect(resolveCron({ schedule: '15m' })).toBe(SCHEDULES['15m']);
    expect(resolveCron({ schedule: 'daily' })).toBe(SCHEDULES.daily);
  });

  it('falls back to hourly for unknown keys', () => {
    expect(resolveCron({ schedule: 'bogus' })).toBe(SCHEDULES.hourly);
  });

  it('returns customCron when schedule === "custom" and customCron is set', () => {
    expect(resolveCron({ schedule: 'custom', customCron: '*/5 * * * *' })).toBe('*/5 * * * *');
  });

  it('falls back to hourly when schedule === "custom" but customCron is empty', () => {
    expect(resolveCron({ schedule: 'custom', customCron: '' })).toBe(SCHEDULES.hourly);
    expect(resolveCron({ schedule: 'custom' })).toBe(SCHEDULES.hourly);
  });
});

describe('buildCustomCron', () => {
  it('builds a seconds-field cron for unit "s"', () => {
    expect(buildCustomCron(60, 's')).toBe('*/60 * * * * *');
    expect(buildCustomCron(15, 's')).toBe('*/15 * * * * *');
  });

  it('builds a minutes-field cron for unit "m"', () => {
    expect(buildCustomCron(5, 'm')).toBe('*/5 * * * *');
  });

  it('defaults to minutes when unit is unknown', () => {
    expect(buildCustomCron(10, 'x')).toBe('*/10 * * * *');
    expect(buildCustomCron(10, '')).toBe('*/10 * * * *');
    expect(buildCustomCron(10, undefined)).toBe('*/10 * * * *');
  });

  it('builds an hours-field cron for unit "h"', () => {
    expect(buildCustomCron(2, 'h')).toBe('0 */2 * * *');
  });

  it('clamps N to at least 1', () => {
    expect(buildCustomCron(0, 'm')).toBe('*/1 * * * *');
    expect(buildCustomCron(-50, 'm')).toBe('*/1 * * * *');
    expect(buildCustomCron('abc', 'm')).toBe('*/1 * * * *');
  });

  it('clamps N to at most 3600', () => {
    expect(buildCustomCron(99999, 'm')).toBe('*/3600 * * * *');
  });

  it('floors fractional N', () => {
    expect(buildCustomCron(5.7, 'm')).toBe('*/5 * * * *');
  });
});

describe('nextRunForExpr', () => {
  it('returns an ISO string for a valid cron', () => {
    const next = nextRunForExpr('0 * * * *');
    expect(next).toBeTypeOf('string');
    expect(() => new Date(next).toISOString()).not.toThrow();
  });

  it('returns a future timestamp', () => {
    const next = nextRunForExpr('*/5 * * * *');
    expect(new Date(next).getTime()).toBeGreaterThan(Date.now());
  });

  it('returns null for invalid input', () => {
    expect(nextRunForExpr('')).toBe(null);
    expect(nextRunForExpr(null)).toBe(null);
    expect(nextRunForExpr('not a cron')).toBe(null);
  });
});
