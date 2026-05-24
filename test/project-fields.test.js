import { describe, it, expect } from 'vitest';
import {
  toNumber,
  getProjectId,
  getTitle,
  getDescription,
  getDuration,
  getIncentive,
  getHourlyRate,
} from '../src/lib/project-fields.js';

describe('toNumber', () => {
  it('passes through finite numbers', () => {
    expect(toNumber(0)).toBe(0);
    expect(toNumber(42)).toBe(42);
    expect(toNumber(-5)).toBe(-5);
    expect(toNumber(3.14)).toBe(3.14);
  });

  it('returns 0 for non-finite numbers', () => {
    expect(toNumber(NaN)).toBe(0);
    expect(toNumber(Infinity)).toBe(0);
    expect(toNumber(-Infinity)).toBe(0);
  });

  it('parses the first numeric run from a string', () => {
    expect(toNumber('$24')).toBe(24);
    expect(toNumber('12.5/hr')).toBe(12.5);
    expect(toNumber('about 100 dollars')).toBe(100);
  });

  it('returns 0 for strings with no digits', () => {
    expect(toNumber('hello')).toBe(0);
    expect(toNumber('')).toBe(0);
  });

  it('unwraps {amount} and {value} objects', () => {
    expect(toNumber({ amount: 50 })).toBe(50);
    expect(toNumber({ value: 75 })).toBe(75);
    expect(toNumber({ amount: 0, value: 99 })).toBe(0);  // amount preferred
  });

  it('returns 0 for objects without amount/value', () => {
    expect(toNumber({})).toBe(0);
    expect(toNumber({ amount: 'nope' })).toBe(0);
  });

  it('returns 0 for null/undefined/booleans', () => {
    expect(toNumber(null)).toBe(0);
    expect(toNumber(undefined)).toBe(0);
    expect(toNumber(true)).toBe(0);
    expect(toNumber(false)).toBe(0);
  });
});

describe('getProjectId', () => {
  it('prefers id over _id over projectId over project._id', () => {
    expect(getProjectId({ id: 'A', _id: 'B' })).toBe('A');
    expect(getProjectId({ _id: 'B' })).toBe('B');
    expect(getProjectId({ projectId: 'C' })).toBe('C');
    expect(getProjectId({ project: { _id: 'D' } })).toBe('D');
  });

  it('returns empty string when no id present', () => {
    expect(getProjectId({})).toBe('');
    expect(getProjectId(null)).toBe('');
    expect(getProjectId(undefined)).toBe('');
  });
});

describe('getTitle', () => {
  it('prefers name', () => {
    expect(getTitle({ name: 'N', title: 'T' })).toBe('N');
  });
  it('falls through name → title → projectName → project.title → empty', () => {
    expect(getTitle({ title: 'T' })).toBe('T');
    expect(getTitle({ projectName: 'P' })).toBe('P');
    expect(getTitle({ project: { title: 'X' } })).toBe('X');
    expect(getTitle({})).toBe('');
    expect(getTitle(null)).toBe('');
  });
});

describe('getDescription', () => {
  it('falls through description → summary → shortDescription → empty', () => {
    expect(getDescription({ description: 'd' })).toBe('d');
    expect(getDescription({ summary: 's' })).toBe('s');
    expect(getDescription({ shortDescription: 'sd' })).toBe('sd');
    expect(getDescription({})).toBe('');
    expect(getDescription(null)).toBe('');
  });
});

describe('getDuration', () => {
  it('uses timeMinutesRequired first', () => {
    expect(getDuration({ timeMinutesRequired: 15, duration: 30 })).toBe(15);
  });
  it('falls through to other field names', () => {
    expect(getDuration({ duration: 30 })).toBe(30);
    expect(getDuration({ sessionLength: 45 })).toBe(45);
    expect(getDuration({ lengthInMinutes: 60 })).toBe(60);
    expect(getDuration({ length: 90 })).toBe(90);
  });
  it('returns 0 when missing', () => {
    expect(getDuration({})).toBe(0);
    expect(getDuration(null)).toBe(0);
  });
});

describe('getIncentive', () => {
  it('uses respondentRemuneration first', () => {
    expect(getIncentive({ respondentRemuneration: 24, incentive: 99 })).toBe(24);
  });
  it('falls through other fields', () => {
    expect(getIncentive({ incentive: 50 })).toBe(50);
    expect(getIncentive({ compensation: 75 })).toBe(75);
    expect(getIncentive({ amount: 100 })).toBe(100);
  });
  it('handles string values with currency symbols', () => {
    expect(getIncentive({ respondentRemuneration: '$30' })).toBe(30);
  });
  it('returns 0 when missing', () => {
    expect(getIncentive({})).toBe(0);
    expect(getIncentive(null)).toBe(0);
  });
});

describe('getHourlyRate', () => {
  it('uses direct hourlyRate when set and positive', () => {
    expect(getHourlyRate({ hourlyRate: 80 })).toBe(80);
  });
  it('uses snake_case hourly_rate alias', () => {
    expect(getHourlyRate({ hourly_rate: 65 })).toBe(65);
  });
  it('uses pay or rate aliases', () => {
    expect(getHourlyRate({ pay: 55 })).toBe(55);
    expect(getHourlyRate({ rate: 45 })).toBe(45);
  });
  it('computes from incentive / duration when no direct field', () => {
    // $24 for 15 min → $96/hr
    expect(getHourlyRate({ respondentRemuneration: 24, timeMinutesRequired: 15 })).toBe(96);
    // $50 for 60 min → $50/hr
    expect(getHourlyRate({ respondentRemuneration: 50, timeMinutesRequired: 60 })).toBe(50);
  });
  it('returns 0 when neither direct field nor computable', () => {
    expect(getHourlyRate({})).toBe(0);
    expect(getHourlyRate({ respondentRemuneration: 24 })).toBe(0);            // no duration
    expect(getHourlyRate({ timeMinutesRequired: 30 })).toBe(0);                // no incentive
    expect(getHourlyRate({ respondentRemuneration: 0, timeMinutesRequired: 60 })).toBe(0);
    expect(getHourlyRate(null)).toBe(0);
  });
  it('ignores zero/negative direct fields and falls through to computation', () => {
    expect(getHourlyRate({ hourlyRate: 0, respondentRemuneration: 24, timeMinutesRequired: 15 })).toBe(96);
  });
});
