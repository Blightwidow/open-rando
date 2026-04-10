import { describe, expect, test } from 'bun:test';
import { getSlopeColor, computeSlopePercent, formatTime, DEFAULT_SLOPE_THRESHOLDS } from './elevation';

describe('getSlopeColor', () => {
  test('flat slope returns green', () => {
    expect(getSlopeColor(2)).toBe(DEFAULT_SLOPE_THRESHOLDS[3].color);
  });

  test('moderate slope returns yellow', () => {
    expect(getSlopeColor(7)).toBe(DEFAULT_SLOPE_THRESHOLDS[2].color);
  });

  test('steep slope returns orange', () => {
    expect(getSlopeColor(12)).toBe(DEFAULT_SLOPE_THRESHOLDS[1].color);
  });

  test('extreme slope returns red', () => {
    expect(getSlopeColor(20)).toBe(DEFAULT_SLOPE_THRESHOLDS[0].color);
  });

  test('negative slope uses absolute value', () => {
    expect(getSlopeColor(-8)).toBe(DEFAULT_SLOPE_THRESHOLDS[2].color);
  });

  test('zero slope returns flat color', () => {
    expect(getSlopeColor(0)).toBe(DEFAULT_SLOPE_THRESHOLDS[3].color);
  });

  test('boundary at exactly 5%', () => {
    expect(getSlopeColor(5)).toBe(DEFAULT_SLOPE_THRESHOLDS[2].color);
  });

  test('boundary at exactly 10%', () => {
    expect(getSlopeColor(10)).toBe(DEFAULT_SLOPE_THRESHOLDS[1].color);
  });

  test('boundary at exactly 15%', () => {
    expect(getSlopeColor(15)).toBe(DEFAULT_SLOPE_THRESHOLDS[0].color);
  });
});

describe('computeSlopePercent', () => {
  test('uphill slope', () => {
    // 100m gain over 1km = 10%
    expect(computeSlopePercent(0, 100, 1, 200)).toBe(10);
  });

  test('downhill slope', () => {
    // -100m over 1km = -10%
    expect(computeSlopePercent(0, 200, 1, 100)).toBe(-10);
  });

  test('flat terrain', () => {
    expect(computeSlopePercent(0, 100, 1, 100)).toBe(0);
  });

  test('zero distance returns 0', () => {
    expect(computeSlopePercent(5, 100, 5, 200)).toBe(0);
  });

  test('steep section', () => {
    // 200m gain over 0.5km = 40%
    expect(computeSlopePercent(0, 500, 0.5, 700)).toBe(40);
  });
});

describe('formatTime', () => {
  test('hours and minutes with padding', () => {
    expect(formatTime(65)).toBe('1h05');
  });

  test('hours only', () => {
    expect(formatTime(60)).toBe('1h');
  });

  test('minutes only', () => {
    expect(formatTime(45)).toBe('45min');
  });

  test('zero', () => {
    expect(formatTime(0)).toBe('0min');
  });

  test('large duration', () => {
    expect(formatTime(150)).toBe('2h30');
  });

  test('single digit minutes padded', () => {
    expect(formatTime(121)).toBe('2h01');
  });
});
