export type Locale = 'fr' | 'en';

const translations: Record<Locale, Record<string, string>> = {
  fr: {
    // Header & navigation
    'site.title': 'open-rando',
    'site.subtitle': 'Randonnées entre gares sur les sentiers GR',
    'site.description': 'Randonnées entre gares sur les sentiers GR',
    'nav.back': 'Toutes les randonnées',
    'nav.language': 'EN',

    // Filters
    'filters.title': 'Filtres',
    'filters.show': 'Afficher les filtres',
    'filters.hide': 'Masquer les filtres',
    'filters.reset': 'Réinitialiser',
    'filters.distance': 'Distance totale',
    'filters.duration': 'Durée totale',
    'filters.maxStep': 'Étape max',
    'filters.steps': "Nombre d'étapes",
    'filters.elevationGain': 'Dénivelé positif',
    'filters.hotel': 'Hôtel à chaque étape',
    'filters.camping': 'Camping à chaque étape',
    'filters.noResults': 'Aucune randonnée ne correspond à vos filtres.',
    'filters.resetFilters': 'Réinitialiser les filtres',

    // Hike count
    'hikes.count.zero': '0 randonnée',
    'hikes.count.one': '1 randonnée',
    'hikes.count.many': '{count} randonnées',

    // Difficulty
    'difficulty.easy': 'Facile',
    'difficulty.moderate': 'Modéré',
    'difficulty.difficult': 'Difficile',
    'difficulty.very_difficult': 'Très difficile',

    // Steps
    'steps.label': '{count} étapes',

    // Detail page
    'detail.summary': 'Résumé',
    'detail.distance': 'Distance',
    'detail.estimatedDuration': 'Durée estimée',
    'detail.stepCount': "Nombre d'étapes",
    'detail.trail': 'Sentier',
    'detail.elevationGain': 'Dénivelé positif',
    'detail.elevationLoss': 'Dénivelé négatif',
    'detail.maxAltitude': 'Altitude max',
    'detail.difficulty': 'Difficulté',
    'detail.downloadGpx': 'Télécharger GPX',
    'detail.steps': 'Étapes',
    'detail.stations': 'Gares',
    'detail.elevationProfile': 'Profil altimétrique',
    'detail.loading': 'Chargement...',
    'detail.sectionTitle': 'Randonner une section',
    'detail.sectionFrom': 'De',
    'detail.sectionTo': "Jusqu'à",
    'detail.sectionReset': "Tout l'itinéraire",
    'detail.sectionDownloadGpx': 'Télécharger GPX section',

    // Accommodation
    'accommodation.hotel': 'Hôtel',
    'accommodation.camping': 'Camping',
    'accommodation.hotelAndCamping': 'Hôtel & Camping',
    'accommodation.none': "Pas d'hébergement répertorié",

    // Map popup
    'map.downloadGpx': 'Télécharger GPX',
    'map.steps': 'étapes',

    // Footer
    'footer.data': 'Données',

    // Theme
    'theme.toggle': 'Basculer thème sombre',
  },
  en: {
    // Header & navigation
    'site.title': 'open-rando',
    'site.subtitle': 'Train station-to-station hikes on GR trails',
    'site.description': 'Train station-to-station hikes on GR trails in France',
    'nav.back': 'All hikes',
    'nav.language': 'FR',

    // Filters
    'filters.title': 'Filters',
    'filters.show': 'Show filters',
    'filters.hide': 'Hide filters',
    'filters.reset': 'Reset',
    'filters.distance': 'Total distance',
    'filters.duration': 'Total duration',
    'filters.maxStep': 'Max step',
    'filters.steps': 'Number of steps',
    'filters.elevationGain': 'Elevation gain',
    'filters.hotel': 'Hotel at every stop',
    'filters.camping': 'Campsite at every stop',
    'filters.noResults': 'No hikes match your filters.',
    'filters.resetFilters': 'Reset filters',

    // Hike count
    'hikes.count.zero': '0 hikes',
    'hikes.count.one': '1 hike',
    'hikes.count.many': '{count} hikes',

    // Difficulty
    'difficulty.easy': 'Easy',
    'difficulty.moderate': 'Moderate',
    'difficulty.difficult': 'Difficult',
    'difficulty.very_difficult': 'Very difficult',

    // Steps
    'steps.label': '{count} steps',

    // Detail page
    'detail.summary': 'Summary',
    'detail.distance': 'Distance',
    'detail.estimatedDuration': 'Estimated duration',
    'detail.stepCount': 'Number of steps',
    'detail.trail': 'Trail',
    'detail.elevationGain': 'Elevation gain',
    'detail.elevationLoss': 'Elevation loss',
    'detail.maxAltitude': 'Max altitude',
    'detail.difficulty': 'Difficulty',
    'detail.downloadGpx': 'Download GPX',
    'detail.steps': 'Steps',
    'detail.stations': 'Stations',
    'detail.elevationProfile': 'Elevation profile',
    'detail.loading': 'Loading...',
    'detail.sectionTitle': 'Hike a section',
    'detail.sectionFrom': 'From',
    'detail.sectionTo': 'To',
    'detail.sectionReset': 'Full itinerary',
    'detail.sectionDownloadGpx': 'Download section GPX',

    // Accommodation
    'accommodation.hotel': 'Hotel',
    'accommodation.camping': 'Campsite',
    'accommodation.hotelAndCamping': 'Hotel & Campsite',
    'accommodation.none': 'No accommodation listed',

    // Map popup
    'map.downloadGpx': 'Download GPX',
    'map.steps': 'steps',

    // Footer
    'footer.data': 'Data',

    // Theme
    'theme.toggle': 'Toggle dark mode',
  },
};

export function t(locale: Locale, key: string, replacements?: Record<string, string | number>): string {
  const value = translations[locale]?.[key] ?? translations.fr[key] ?? key;
  if (!replacements) return value;
  return Object.entries(replacements).reduce(
    (result, [placeholder, replacement]) => result.replace(`{${placeholder}}`, String(replacement)),
    value,
  );
}

export function getLocaleFromUrl(url: URL): Locale {
  const firstSegment = url.pathname.split('/')[1];
  if (firstSegment === 'en') return 'en';
  return 'fr';
}

export function getAlternateUrl(url: URL, targetLocale: Locale): string {
  const pathname = url.pathname;
  if (targetLocale === 'en') {
    return `/en${pathname}`;
  }
  // Remove /en prefix for French
  return pathname.replace(/^\/en/, '') || '/';
}

export function formatHikeCount(locale: Locale, count: number): string {
  if (count === 0) return t(locale, 'hikes.count.zero');
  if (count === 1) return t(locale, 'hikes.count.one');
  return t(locale, 'hikes.count.many', { count });
}

/** Subset of translations needed in client-side scripts */
export function getClientTranslations(locale: Locale): Record<string, string> {
  const keys = [
    'hikes.count.zero', 'hikes.count.one', 'hikes.count.many',
    'map.downloadGpx', 'map.steps',
    'filters.noResults', 'filters.resetFilters',
    'detail.loading',
    'detail.sectionTitle', 'detail.sectionFrom', 'detail.sectionTo',
    'detail.sectionReset', 'detail.sectionDownloadGpx',
  ];
  const result: Record<string, string> = {};
  for (const key of keys) {
    result[key] = t(locale, key);
  }
  return result;
}
