import { describe, expect, test } from 'bun:test';
import { formatDuration } from './format';

describe('formatDuration', () => {
  test('hours and minutes', () => {
    expect(formatDuration(90)).toBe('1h30min');
  });

  test('hours only', () => {
    expect(formatDuration(120)).toBe('2h');
  });

  test('exact one hour', () => {
    expect(formatDuration(60)).toBe('1h');
  });

  test('minutes only', () => {
    expect(formatDuration(45)).toBe('45min');
  });

  test('zero minutes', () => {
    expect(formatDuration(0)).toBe('0min');
  });

  test('large duration', () => {
    expect(formatDuration(605)).toBe('10h5min');
  });
});
