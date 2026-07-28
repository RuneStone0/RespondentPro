import { describe, it, expect } from 'vitest';
import { whyHide } from '../src/lib/filter.js';

const base = {
  name: 'Coffee taste test',
  description: 'Quick study on caffeinated beverages',
  respondentRemuneration: 50,
  timeMinutesRequired: 30,
};
// base derived: hourly = 50 / 30 * 60 = 100; incentive=50; duration=30

describe('whyHide', () => {
  it('returns null when no filters are set', () => {
    expect(whyHide(base, {})).toBeNull();
    expect(whyHide(base)).toBeNull();
  });

  describe('keyword rule', () => {
    it('matches title case-insensitively', () => {
      expect(whyHide(base, { keywords: ['coffee'] })).toBe('keyword "coffee"');
      expect(whyHide(base, { keywords: ['COFFEE'] })).toBe('keyword "COFFEE"');
    });

    it('matches description', () => {
      expect(whyHide(base, { keywords: ['caffeinated'] })).toBe('keyword "caffeinated"');
    });

    it('returns null when no keyword matches', () => {
      expect(whyHide(base, { keywords: ['tea'] })).toBeNull();
    });

    it('skips empty keyword entries', () => {
      expect(whyHide(base, { keywords: ['', null, undefined] })).toBeNull();
    });

    it('returns the first matching keyword', () => {
      expect(whyHide(base, { keywords: ['nope', 'coffee', 'caffeinated'] })).toBe('keyword "coffee"');
    });
  });

  describe('minHourlyRate rule', () => {
    it('hides when hourly rate is below threshold', () => {
      // hourly = 100; minHourlyRate = 150 → hidden
      expect(whyHide(base, { minHourlyRate: 150 })).toBe('$100/hr < min $150');
    });
    it('does not hide when hourly rate meets threshold', () => {
      expect(whyHide(base, { minHourlyRate: 100 })).toBeNull();
      expect(whyHide(base, { minHourlyRate: 50 })).toBeNull();
    });
    it('does not hide when threshold is 0/disabled', () => {
      expect(whyHide(base, { minHourlyRate: 0 })).toBeNull();
    });
    it('does not hide when project hourly rate is unknown/0', () => {
      const noPay = { name: 'X', description: '' };
      expect(whyHide(noPay, { minHourlyRate: 50 })).toBeNull();
    });
  });

  describe('minIncentive rule', () => {
    it('hides when incentive is below threshold', () => {
      expect(whyHide(base, { minIncentive: 80 })).toBe('incentive $50 < min $80');
    });
    it('does not hide when incentive meets threshold', () => {
      expect(whyHide(base, { minIncentive: 50 })).toBeNull();
    });
    it('does not hide when threshold is 0', () => {
      expect(whyHide(base, { minIncentive: 0 })).toBeNull();
    });
  });

  describe('maxDuration rule', () => {
    it('hides when duration exceeds max', () => {
      const long = { ...base, timeMinutesRequired: 90 };
      expect(whyHide(long, { maxDuration: 60 })).toBe('90min > max 60min');
    });
    it('does not hide when duration is within max', () => {
      expect(whyHide(base, { maxDuration: 60 })).toBeNull();
    });
    it('does not hide when max is 0', () => {
      expect(whyHide(base, { maxDuration: 0 })).toBeNull();
    });
  });

  describe('minDuration rule', () => {
    it('hides when duration is below min', () => {
      const short = { ...base, timeMinutesRequired: 5 };
      expect(whyHide(short, { minDuration: 15 })).toBe('5min < min 15min');
    });
    it('does not hide when duration meets min', () => {
      expect(whyHide(base, { minDuration: 30 })).toBeNull();
    });
    it('does not hide when min is 0', () => {
      expect(whyHide(base, { minDuration: 0 })).toBeNull();
    });
  });

  describe('hideNotEligible rule', () => {
    it('hides when project is tagged not eligible and rule is on', () => {
      expect(whyHide({ ...base, _eligible: false }, { hideNotEligible: true })).toBe('not eligible');
    });
    it('does not hide when project is eligible', () => {
      expect(whyHide({ ...base, _eligible: true }, { hideNotEligible: true })).toBeNull();
    });
    it('does not hide when eligibility is unknown (project not tagged)', () => {
      expect(whyHide({ ...base }, { hideNotEligible: true })).toBeNull();
    });
    it('does not hide when the rule is off, even if not eligible', () => {
      expect(whyHide({ ...base, _eligible: false }, { hideNotEligible: false })).toBeNull();
    });
    it('wins over keyword and numeric rules', () => {
      const f = { hideNotEligible: true, keywords: ['nope'], minHourlyRate: 0 };
      expect(whyHide({ ...base, _eligible: false }, f)).toBe('not eligible');
    });
  });

  describe('precedence', () => {
    it('keyword wins over numeric rules', () => {
      const f = { keywords: ['coffee'], minHourlyRate: 999, maxDuration: 1, minDuration: 999 };
      expect(whyHide(base, f)).toBe('keyword "coffee"');
    });

    it('numeric rules evaluated in order: hourly, incentive, max, min', () => {
      const f = { minHourlyRate: 200, minIncentive: 100, maxDuration: 10, minDuration: 100 };
      expect(whyHide(base, f)).toBe('$100/hr < min $200');
    });
  });
});
