import { describe, expect, test } from 'bun:test';
import { buildPoiPopupHtml, escapeHtml, normalizePoiUrl } from './poi-popup';

const labels = { website: 'Website', timetable: 'Timetable' };

describe('escapeHtml', () => {
  test('escapes markup characters', () => {
    expect(escapeHtml(`<b>"B&B" l'hôtel</b>`)).toBe(
      '&lt;b&gt;&quot;B&amp;B&quot; l&#39;hôtel&lt;/b&gt;',
    );
  });
});

describe('normalizePoiUrl', () => {
  test('keeps https URL', () => {
    expect(normalizePoiUrl('https://example.fr/contact')).toBe('https://example.fr/contact');
  });

  test('keeps http URL', () => {
    expect(normalizePoiUrl('http://example.fr/')).toBe('http://example.fr/');
  });

  test('adds https to scheme-less URL', () => {
    expect(normalizePoiUrl('www.gite-rando.fr')).toBe('https://www.gite-rando.fr/');
  });

  test('trims surrounding whitespace', () => {
    expect(normalizePoiUrl('  www.example.fr  ')).toBe('https://www.example.fr/');
  });

  test('rejects javascript URL', () => {
    expect(normalizePoiUrl('javascript:alert(1)')).toBeNull();
  });

  test('rejects mailto URL', () => {
    expect(normalizePoiUrl('mailto:hotel@example.fr')).toBeNull();
  });

  test('returns null for empty string', () => {
    expect(normalizePoiUrl('')).toBeNull();
  });

  test('returns null for undefined', () => {
    expect(normalizePoiUrl(undefined)).toBeNull();
  });
});

describe('buildPoiPopupHtml', () => {
  test('escapes POI name', () => {
    const html = buildPoiPopupHtml(
      { name: '<img src=x onerror=alert(1)>', poi_type: 'hotel' },
      labels,
    );
    expect(html).not.toContain('<img');
  });

  test('replaces every underscore in type label', () => {
    const html = buildPoiPopupHtml({ name: 'Gare', poi_type: 'train_station' }, labels);
    expect(html).toContain('>train station<');
  });

  test('lists transit lines', () => {
    const html = buildPoiPopupHtml(
      { name: 'Arrêt', poi_type: 'bus_stop', transit_lines: ['12', 'N1'] },
      labels,
    );
    expect(html).toContain('12, N1');
  });

  test('links scheme-less accommodation URL with website label', () => {
    const html = buildPoiPopupHtml(
      { name: 'Gîte', poi_type: 'camping', url: 'www.gite.fr' },
      labels,
    );
    expect(html).toContain(
      '<a href="https://www.gite.fr/" target="_blank" rel="noopener noreferrer" class="text-xs underline">Website</a>',
    );
  });

  test('uses timetable label for stations', () => {
    const html = buildPoiPopupHtml(
      { name: 'Gare', poi_type: 'train_station', url: 'https://sncf.example/horaires' },
      labels,
    );
    expect(html).toContain('>Timetable</a>');
  });

  test('omits link for unsafe URL', () => {
    const html = buildPoiPopupHtml(
      { name: 'Hôtel', poi_type: 'hotel', url: 'javascript:alert(1)' },
      labels,
    );
    expect(html).not.toContain('<a');
  });
});
