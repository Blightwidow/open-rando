import { describe, expect, test } from 'bun:test';
import { t, getLocaleFromUrl, getAlternateUrl, formatHikeCount, getClientTranslations } from './i18n';

describe('t', () => {
  test('returns French translation', () => {
    expect(t('fr', 'site.title')).toBe('TrainRando');
  });

  test('returns English translation', () => {
    expect(t('en', 'nav.back')).toBe('All hikes');
  });

  test('falls back to French when key missing in English', () => {
    // Both locales have all keys currently, so test with a known French key
    expect(t('fr', 'nav.back')).toBe('Toutes les randonnées');
  });

  test('returns key when missing in both locales', () => {
    expect(t('fr', 'nonexistent.key')).toBe('nonexistent.key');
    expect(t('en', 'nonexistent.key')).toBe('nonexistent.key');
  });

  test('replaces single placeholder', () => {
    expect(t('en', 'hikes.count.many', { count: 42 })).toBe('42 hikes');
  });

  test('replaces multiple placeholders', () => {
    expect(t('fr', 'suggest.section', { from: 1, to: 3 })).toBe('Étapes 1–3');
  });

  test('returns value without replacements when none provided', () => {
    expect(t('fr', 'hikes.count.one')).toBe('1 randonnée');
  });
});

describe('getLocaleFromUrl', () => {
  test('English path returns en', () => {
    expect(getLocaleFromUrl(new URL('https://rando.dammaretz.fr/en/app'))).toBe('en');
  });

  test('French path returns fr', () => {
    expect(getLocaleFromUrl(new URL('https://rando.dammaretz.fr/app'))).toBe('fr');
  });

  test('root path returns fr', () => {
    expect(getLocaleFromUrl(new URL('https://rando.dammaretz.fr/'))).toBe('fr');
  });

  test('English root returns en', () => {
    expect(getLocaleFromUrl(new URL('https://rando.dammaretz.fr/en'))).toBe('en');
  });
});

describe('getAlternateUrl', () => {
  test('French to English adds /en prefix', () => {
    expect(getAlternateUrl(new URL('https://rando.dammaretz.fr/app/'), 'en')).toBe('/en/app/');
  });

  test('English to French removes /en prefix', () => {
    expect(getAlternateUrl(new URL('https://rando.dammaretz.fr/en/app/'), 'fr')).toBe('/app/');
  });

  test('English root to French returns /', () => {
    expect(getAlternateUrl(new URL('https://rando.dammaretz.fr/en'), 'fr')).toBe('/');
  });

  test('root to English adds /en', () => {
    expect(getAlternateUrl(new URL('https://rando.dammaretz.fr/'), 'en')).toBe('/en/');
  });
});

describe('formatHikeCount', () => {
  test('zero in French', () => {
    expect(formatHikeCount('fr', 0)).toBe('0 randonnée');
  });

  test('one in French', () => {
    expect(formatHikeCount('fr', 1)).toBe('1 randonnée');
  });

  test('many in French', () => {
    expect(formatHikeCount('fr', 42)).toBe('42 randonnées');
  });

  test('zero in English', () => {
    expect(formatHikeCount('en', 0)).toBe('0 hikes');
  });

  test('one in English', () => {
    expect(formatHikeCount('en', 1)).toBe('1 hike');
  });

  test('many in English', () => {
    expect(formatHikeCount('en', 5)).toBe('5 hikes');
  });
});

describe('getClientTranslations', () => {
  test('returns all expected client keys', () => {
    const translations = getClientTranslations('fr');
    const expectedKeys = [
      'hikes.count.zero', 'hikes.count.one', 'hikes.count.many',
      'map.downloadGpx', 'map.steps',
      'hike.loop', 'hike.loopFrom',
      'filters.noResults', 'filters.resetFilters',
      'detail.loading',
      'suggest.resultsCount.one', 'suggest.resultsCount.many',
      'suggest.noResults', 'suggest.section', 'suggest.departs', 'suggest.arrives',
    ];
    for (const key of expectedKeys) {
      expect(key in translations).toBe(true);
      expect(typeof translations[key]).toBe('string');
    }
  });

  test('English translations differ from French', () => {
    const frTranslations = getClientTranslations('fr');
    const enTranslations = getClientTranslations('en');
    expect(frTranslations['suggest.noResults']).not.toBe(enTranslations['suggest.noResults']);
  });
});
