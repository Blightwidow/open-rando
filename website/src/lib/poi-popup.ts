// Builds MapLibre popup HTML for route POIs. POI names, lines and URLs come
// from OpenStreetMap (user-editable), so every value is escaped and links are
// restricted to http(s).

export interface PopupPoi {
  name: string;
  poi_type: string;
  transit_lines?: string[];
  url?: string;
}

export interface PopupLabels {
  website: string;
  timetable: string;
}

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

export function buildPoiPopupHtml(poi: PopupPoi, labels: PopupLabels): string {
  const typeLabel = poi.poi_type.replaceAll('_', ' ');
  let popupHtml = `<strong>${escapeHtml(poi.name)}</strong><br><span class="text-xs">${escapeHtml(typeLabel)}</span>`;

  if (poi.transit_lines?.length) {
    popupHtml += `<br><span class="text-xs text-blue-600">${escapeHtml(poi.transit_lines.join(', '))}</span>`;
  }

  const safeUrl = normalizePoiUrl(poi.url);
  if (safeUrl) {
    const isAccommodation = poi.poi_type === 'hotel' || poi.poi_type === 'camping';
    const linkLabel = isAccommodation ? labels.website : labels.timetable;
    popupHtml += `<br><a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="text-xs underline">${escapeHtml(linkLabel)}</a>`;
  }

  return popupHtml;
}
