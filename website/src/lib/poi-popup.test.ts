import { describe, expect, test } from 'bun:test';
import { buildPoiPopupHtml, escapeHtml, normalizePhone, normalizePoiUrl } from './poi-popup';

const labels = {
  website: 'Website',
  timetable: 'Timetable',
  openingHours: 'Hours:',
  categories: { bakery: 'Bakery', cafe: 'Cafe' },
};

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

describe('normalizePhone', () => {
  test('keeps digits and a leading plus', () => {
    expect(normalizePhone('+33 4 92 00 00 00')).toBe('tel:+33492000000');
  });

  test('takes the first of several numbers', () => {
    expect(normalizePhone('04 92 00 00 00; 06 00 00 00 00')).toBe('tel:0492000000');
  });

  test('rejects text that is not a number', () => {
    expect(normalizePhone('javascript:alert(1)')).toBeNull();
  });

  test('returns null when there is none', () => {
    expect(normalizePhone(undefined)).toBeNull();
  });
});

describe('buildPoiPopupHtml for shops and eateries', () => {
  const bakery = {
    name: 'Chez Paul',
    poi_type: 'shop',
    category: 'bakery',
    opening_hours: 'Mo-Sa 07:00-19:00',
    url: 'www.chezpaul.fr',
    phone: '+33 4 92 00 00 00',
  };

  test('shows the translated category instead of the kind', () => {
    expect(buildPoiPopupHtml(bakery, labels)).toContain('>Bakery<');
  });

  test('falls back to the raw category when it has no translation', () => {
    const html = buildPoiPopupHtml({ ...bakery, category: 'ice_cream' }, labels);
    expect(html).toContain('>ice cream<');
  });

  test('shows the opening hours', () => {
    expect(buildPoiPopupHtml(bakery, labels)).toContain('Mo-Sa 07:00-19:00');
  });

  test('omits the opening hours line when the shop has none', () => {
    const html = buildPoiPopupHtml({ ...bakery, opening_hours: undefined }, labels);
    expect(html).not.toContain('Hours:');
  });

  test('escapes the opening hours', () => {
    const html = buildPoiPopupHtml({ ...bakery, opening_hours: '<script>x</script>' }, labels);
    expect(html).not.toContain('<script>');
  });

  test('links the shop website as a website, not a timetable', () => {
    expect(buildPoiPopupHtml(bakery, labels)).toContain('>Website</a>');
  });

  test('links the phone number', () => {
    expect(buildPoiPopupHtml(bakery, labels)).toContain('href="tel:+33492000000"');
  });

  test('omits the phone link for an unusable number', () => {
    const html = buildPoiPopupHtml({ ...bakery, phone: 'ask inside' }, labels);
    expect(html).not.toContain('tel:');
  });
});
