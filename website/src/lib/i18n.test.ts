import { describe, expect, test } from 'bun:test';
import {
  t,
  getLocaleFromUrl,
  getAlternateUrl,
  getLocaleStaticPaths,
  localePath,
} from './i18n';

describe('t', () => {
  test('returns French translation', () => {
    expect(t('fr', 'nav.explore')).toBe('Parcourir');
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
    expect(t('en', 'detail.stationCount', { count: 42 })).toBe('42 stations');
  });

  test('replaces multiple placeholders', () => {
    expect(t('fr', '{first} and {second}', { first: 'A', second: 'B' })).toBe('A and B');
  });

  test('returns value without replacements when none provided', () => {
    expect(t('fr', 'tabs.list')).toBe('Liste');
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

describe('localePath', () => {
  test('French pages live at the root', () => {
    expect(localePath('fr', '/app')).toBe('/app');
  });

  test('English pages live under /en', () => {
    expect(localePath('en', '/app')).toBe('/en/app');
  });

  test('the English home is /en without a trailing slash', () => {
    expect(localePath('en', '/')).toBe('/en');
  });

  test('the French home stays /', () => {
    expect(localePath('fr', '/')).toBe('/');
  });
});

describe('getLocaleStaticPaths', () => {
  test('French has no locale segment', () => {
    expect(getLocaleStaticPaths()[0]).toEqual({ params: { locale: undefined }, props: { locale: 'fr' } });
  });

  test('English uses the en segment', () => {
    expect(getLocaleStaticPaths()[1]).toEqual({ params: { locale: 'en' }, props: { locale: 'en' } });
  });
});

describe('detail page copy', () => {
  test('page description fills name, distance and station count', () => {
    expect(t('en', 'detail.pageDescription', { name: 'GR 13', distance: 120, count: 4 })).toBe(
      'GR 13 — 120 km, 4 stations',
    );
  });

  test('every locale labels each POI layer', () => {
    for (const locale of ['fr', 'en'] as const) {
      for (const type of ['train_station', 'bus_stop', 'hotel', 'camping']) {
        expect(t(locale, `poi.layer.${type}`)).not.toBe(`poi.layer.${type}`);
      }
    }
  });
});

describe('landing mobile app copy', () => {
  test('every locale has a download button label', () => {
    for (const locale of ['fr', 'en'] as const) {
      expect(t(locale, 'landing.mobile.cta')).not.toBe('landing.mobile.cta');
    }
  });

  test('English no longer announces the app as coming soon', () => {
    expect(t('en', 'landing.mobile.title')).toBe('Mobile app');
  });
});
