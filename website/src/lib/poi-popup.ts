// Builds MapLibre popup HTML for route POIs. POI names, lines and URLs come
// from OpenStreetMap (user-editable), so every value is escaped and links are
// restricted to http(s).

export interface PopupPoi {
  name: string;
  poi_type: string;
  transit_lines?: string[];
  url?: string;
  /** Shops and eateries: the OSM kind, such as "bakery" or "cafe". */
  category?: string;
  /** Shops and eateries: the raw OSM `opening_hours` value. */
  opening_hours?: string;
  phone?: string;
}

export interface PopupLabels {
  website: string;
  timetable: string;
  openingHours: string;
  /** Translated name of each shop and eatery category, keyed by OSM kind. */
  categories: Record<string, string>;
}

/** POIs whose link goes to their own website, not to a timetable. */
const WEBSITE_POI_TYPES = new Set(['hotel', 'camping', 'shop', 'eatery']);

const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => HTML_ESCAPES[character]);
}

const URL_SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*:/i;

/**
 * Returns an absolute http(s) URL, or null when the value is unusable.
 * OSM `website` tags are often missing the scheme ("www.example.fr"), which
 * browsers would otherwise resolve as a relative path on our own site.
 */
export function normalizePoiUrl(rawUrl: string | undefined): string | null {
  const trimmedUrl = rawUrl?.trim();
  if (!trimmedUrl) return null;

  const candidateUrl = URL_SCHEME_PATTERN.test(trimmedUrl) ? trimmedUrl : `https://${trimmedUrl}`;
  try {
    const parsedUrl = new URL(candidateUrl);
    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') return null;
    return parsedUrl.href;
  } catch {
    return null;
  }
}

const PHONE_PATTERN = /^\+?[0-9][0-9 .()-]{3,}$/;

/** A `tel:` link target, or null when the value does not look like a phone number. */
export function normalizePhone(rawPhone: string | undefined): string | null {
  const trimmedPhone = rawPhone?.split(';')[0].trim();
  if (!trimmedPhone || !PHONE_PATTERN.test(trimmedPhone)) return null;
  return `tel:${trimmedPhone.replace(/[^0-9+]/g, '')}`;
}

export function buildPoiPopupHtml(poi: PopupPoi, labels: PopupLabels): string {
  const typeLabel = (poi.category && labels.categories[poi.category]) || (poi.category ?? poi.poi_type).replaceAll('_', ' ');
  let popupHtml = `<strong>${escapeHtml(poi.name)}</strong><br><span class="text-xs">${escapeHtml(typeLabel)}</span>`;

  if (poi.transit_lines?.length) {
    popupHtml += `<br><span class="text-xs text-blue-600">${escapeHtml(poi.transit_lines.join(', '))}</span>`;
  }

  if (poi.opening_hours) {
    popupHtml += `<br><span class="text-xs"><span class="font-medium">${escapeHtml(labels.openingHours)}</span> ${escapeHtml(poi.opening_hours)}</span>`;
  }

  const safeUrl = normalizePoiUrl(poi.url);
  if (safeUrl) {
    const linkLabel = WEBSITE_POI_TYPES.has(poi.poi_type) ? labels.website : labels.timetable;
    popupHtml += `<br><a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="text-xs underline">${escapeHtml(linkLabel)}</a>`;
  }

  const phoneLink = normalizePhone(poi.phone);
  if (phoneLink && poi.phone) {
    popupHtml += `<br><a href="${escapeHtml(phoneLink)}" class="text-xs underline">${escapeHtml(poi.phone.split(';')[0].trim())}</a>`;
  }

  return popupHtml;
}
