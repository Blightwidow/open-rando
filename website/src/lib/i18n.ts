export type Locale = 'fr' | 'en';

const translations: Record<Locale, Record<string, string>> = {
  fr: {
    // Header & navigation
    'site.title': 'TrainRando',
    'site.subtitle': 'Randonnées entre gares sur les sentiers GR & PR',
    'site.description': 'Découvrez des itinéraires de randonnée sur les sentiers GR et PR, accessibles en train. TrainRando est un projet open-source qui répertorie des randonnées entre gares en France.',
    'nav.back': 'Toutes les randonnées',
    'nav.language': 'EN',
    'nav.explore': 'Parcourir',
    'nav.about': 'À propos',

    // Landing - Hero
    'landing.hero.title': 'Randonnez de gare en gare',
    'landing.hero.subtitle': 'Découvrez des itinéraires de randonnée sur les sentiers GR et PR, accessibles en train. Pas de voiture, pas de navette — juste le train, vos chaussures et le sentier.',
    'landing.hero.cta': 'Explorer les randonnées',

    // Landing - Features
    'landing.features.title': 'Comment ça marche',
    'landing.feature.train.title': 'Départ et arrivée en gare',
    'landing.feature.train.description': 'Chaque itinéraire commence et se termine à une gare SNCF. Prenez le train, randonnez, reprenez le train.',
    'landing.feature.gr.title': 'Sentiers GR & PR balisés',
    'landing.feature.gr.description': 'Tous les itinéraires suivent des sentiers officiels balisés et entretenus : Grandes Randonnées (GR, GRP) et Promenades et Randonnées (PR).',
    'landing.feature.accommodation.title': 'Étapes avec hébergement',
    'landing.feature.accommodation.description': 'Les randonnées de plusieurs jours passent par des gares intermédiaires avec hôtels ou campings à proximité.',
    'landing.feature.gpx.title': 'Traces GPX téléchargeables',
    'landing.feature.gpx.description': 'Téléchargez les traces GPX avec profil altimétrique pour chaque itinéraire.',
    'landing.feature.filters.title': 'Trouvez votre randonnée',
    'landing.feature.filters.description': 'Filtrez par région, type de terrain ou difficulté pour trouver les itinéraires qui vous correspondent.',
    'landing.feature.map.title': 'Carte interactive',
    'landing.feature.map.description': 'Gares, arrêts de bus, hébergements et profil altimétrique synchronisés sur une carte interactive.',

    // Landing - Privacy
    'landing.privacy.title': 'Aucune donnée personnelle',
    'landing.privacy.description': 'TrainRando est un site statique. Aucune donnée utilisateur n\'est collectée, stockée ou partagée. Pas de cookies, pas d\'analytics, pas de compte.',

    // Landing - Mobile
    'landing.mobile.title': 'Bientôt : application mobile',
    'landing.mobile.description': 'Une application compagnon pour consulter les itinéraires hors-ligne, avec navigation GPS et alertes météo.',

    // Footer
    'footer.about': 'À propos',
    'footer.privacy': 'Confidentialité',
    'footer.legal': 'Mentions légales',

    // Filters
    'filters.title': 'Filtres',
    'filters.show': 'Afficher les filtres',
    'filters.hide': 'Masquer les filtres',
    'filters.reset': 'Réinitialiser',
    'filters.maxStep': 'Étape max',
    'filters.steps': "Nombre d'étapes",
    'filters.difficulty': 'Difficulté',
    'filters.accommodation': 'Hébergement à chaque étape',
    'filters.hotel': 'Hôtel',
    'filters.camping': 'Camping',
    'filters.region': 'Région',
    'filters.terrain': 'Terrain',
    'terrain.coastal': 'Littoral',
    'terrain.mountain': 'Montagne',
    'terrain.hills': 'Collines',
    'terrain.forest': 'Forêt',
    'terrain.plains': 'Plaines',
    'filters.noResults': 'Aucune randonnée ne correspond à vos filtres.',
    'filters.resetFilters': 'Réinitialiser les filtres',

    // Tabs
    'tabs.list': 'Liste',
    'tabs.map': 'Carte',
    'map.loading': 'Chargement des sentiers…',

    // Hike count
    'hikes.count.zero': '0 randonnée',
    'hikes.count.one': '1 randonnée',
    'hikes.count.many': '{count} randonnées',

    // Difficulty
    'difficulty.easy': 'Facile',
    'difficulty.moderate': 'Modéré',
    'difficulty.difficult': 'Difficile',
    'difficulty.very_difficult': 'Très difficile',
    'difficulty.tooltip.easy': 'Moins de 15m de dénivelé positif par km (ou moins de 300m au total)',
    'difficulty.tooltip.moderate': 'De 15 à 30m de dénivelé positif par km',
    'difficulty.tooltip.difficult': 'De 30 à 50m de dénivelé positif par km',
    'difficulty.tooltip.very_difficult': '50m ou plus de dénivelé positif par km',

    // Hike types
    'hike.loop': 'Boucle',
    'hike.loopFrom': 'Boucle depuis {station}',

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
    'detail.stations': 'Arrêts',
    'detail.elevationProfile': 'Profil altimétrique',
    'detail.timeDisclaimer': 'Temps estimés : 4 km/h sur le plat, +300 m/h en montée et -450 m/h en descente (pentes \u2265 10 %).',
    'detail.loading': 'Chargement...',
    'detail.sectionTitle': 'Randonner une section',
    'detail.sectionFrom': 'De',
    'detail.sectionTo': "Jusqu'à",
    'detail.sectionReset': "Tout l'itinéraire",
    'detail.sectionDownloadGpx': 'Télécharger GPX section',
    'detail.sectionQrCode': 'QR Code',
    'detail.sectionQrDownload': 'Télécharger le QR code',
    'detail.sectionQrDescription': 'Partagez ce QR code ou scannez-le avec l\'app compagnon pour ajouter cette section hors-ligne.',

    // Rail service
    'rail.weekday': 'Semaine',
    'rail.saturday': 'Samedi',
    'rail.sunday': 'Dimanche',
    'rail.noService': 'Pas de service',
    'rail.departures': '{count} départs',
    'rail.sourceNote': 'Horaires indicatifs : premier et dernier départ et nombre de trains par type de jour, calculés depuis les flux GTFS de transport.data.gouv.fr. Vérifiez les horaires du jour avant de partir.',

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


    // Section filter

    // Disclaimer
    'detail.disclaimer': 'Les informations présentées (tracés, hébergements, gares) sont issues de données ouvertes et peuvent être incomplètes ou obsolètes. Vérifiez la disponibilité des hébergements, campings et horaires de train avant de partir.',

    // Theme
    'theme.toggle': 'Basculer thème sombre',
  },
  en: {
    // Header & navigation
    'site.title': 'TrainRando',
    'site.subtitle': 'Train station-to-station hikes on GR & PR trails',
    'site.description': 'Discover hiking routes on GR and PR trails in France, accessible by train. TrainRando is an open-source project cataloging station-to-station hikes.',
    'nav.back': 'All hikes',
    'nav.language': 'FR',
    'nav.explore': 'Explore',
    'nav.about': 'About',

    // Landing - Hero
    'landing.hero.title': 'Hike from station to station',
    'landing.hero.subtitle': 'Discover hiking routes on GR and PR trails, accessible by train. No car, no shuttle — just the train, your boots and the trail.',
    'landing.hero.cta': 'Explore hikes',

    // Landing - Features
    'landing.features.title': 'How it works',
    'landing.feature.train.title': 'Start and end at a train station',
    'landing.feature.train.description': 'Every route starts and ends at an SNCF train station. Take the train, hike, take the train back.',
    'landing.feature.gr.title': 'Marked GR & PR trails',
    'landing.feature.gr.description': 'All routes follow official waymarked trails: Grande Randonnée (GR, GRP) and Promenade et Randonnée (PR).',
    'landing.feature.accommodation.title': 'Multi-day with accommodation',
    'landing.feature.accommodation.description': 'Multi-day hikes pass through intermediate stations with nearby hotels or campsites.',
    'landing.feature.gpx.title': 'Downloadable GPX tracks',
    'landing.feature.gpx.description': 'Download GPX tracks with elevation profiles for every route.',
    'landing.feature.filters.title': 'Find your hike',
    'landing.feature.filters.description': 'Filter by region, terrain type or difficulty to find routes that match your preferences.',
    'landing.feature.map.title': 'Interactive map',
    'landing.feature.map.description': 'Train stations, bus stops, accommodation and elevation profile synced on an interactive map.',

    // Landing - Privacy
    'landing.privacy.title': 'No tracking, no personal data',
    'landing.privacy.description': 'TrainRando is a static site. No user data is collected, stored or shared. No cookies, no analytics, no accounts.',

    // Landing - Mobile
    'landing.mobile.title': 'Coming soon: mobile app',
    'landing.mobile.description': 'A companion app to browse routes offline, with GPS navigation and weather alerts.',

    // Footer
    'footer.about': 'About',
    'footer.privacy': 'Privacy',
    'footer.legal': 'Legal',

    // Filters
    'filters.title': 'Filters',
    'filters.show': 'Show filters',
    'filters.hide': 'Hide filters',
    'filters.reset': 'Reset',
    'filters.maxStep': 'Max step',
    'filters.steps': 'Number of steps',
    'filters.difficulty': 'Difficulty',
    'filters.accommodation': 'Accommodation at every stop',
    'filters.hotel': 'Hotel',
    'filters.camping': 'Campsite',
    'filters.region': 'Region',
    'filters.terrain': 'Terrain',
    'terrain.coastal': 'Coastal',
    'terrain.mountain': 'Mountain',
    'terrain.hills': 'Hills',
    'terrain.forest': 'Forest',
    'terrain.plains': 'Plains',
    'filters.noResults': 'No hikes match your filters.',
    'filters.resetFilters': 'Reset filters',

    // Tabs
    'tabs.list': 'List',
    'tabs.map': 'Map',
    'map.loading': 'Loading trails…',

    // Hike count
    'hikes.count.zero': '0 hikes',
    'hikes.count.one': '1 hike',
    'hikes.count.many': '{count} hikes',

    // Difficulty
    'difficulty.easy': 'Easy',
    'difficulty.moderate': 'Moderate',
    'difficulty.difficult': 'Difficult',
    'difficulty.very_difficult': 'Very difficult',
    'difficulty.tooltip.easy': 'Under 15m of ascent per km (or under 300m in total)',
    'difficulty.tooltip.moderate': '15 to 30m of ascent per km',
    'difficulty.tooltip.difficult': '30 to 50m of ascent per km',
    'difficulty.tooltip.very_difficult': '50m or more of ascent per km',

    // Hike types
    'hike.loop': 'Loop',
    'hike.loopFrom': 'Loop from {station}',

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
    'detail.stations': 'Stops',
    'detail.elevationProfile': 'Elevation profile',
    'detail.timeDisclaimer': 'Estimated times: 4 km/h on flat terrain, +300 m/h uphill, -450 m/h downhill (slopes \u2265 10%).',
    'detail.loading': 'Loading...',
    'detail.sectionTitle': 'Hike a section',
    'detail.sectionFrom': 'From',
    'detail.sectionTo': 'To',
    'detail.sectionReset': 'Full itinerary',
    'detail.sectionDownloadGpx': 'Download section GPX',
    'detail.sectionQrCode': 'QR Code',
    'detail.sectionQrDownload': 'Download QR code',
    'detail.sectionQrDescription': 'Share this QR code with anyone, or scan it with the companion app to save this section offline.',

    // Rail service
    'rail.weekday': 'Weekdays',
    'rail.saturday': 'Saturday',
    'rail.sunday': 'Sunday',
    'rail.noService': 'No service',
    'rail.departures': '{count} departures',
    'rail.sourceNote': 'Indicative timetable: first and last departure and the number of trains per kind of day, computed from the transport.data.gouv.fr GTFS feeds. Check the timetable of the day before you leave.',

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


    // Section filter

    // Disclaimer
    'detail.disclaimer': 'The information shown (trails, accommodation, stations) is based on open data and may be incomplete or outdated. Please verify accommodation, campsite and train schedule availability before setting out.',

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
    'hike.loop', 'hike.loopFrom',
    'filters.noResults', 'filters.resetFilters',
    'detail.loading',
    'detail.sectionTitle', 'detail.sectionFrom', 'detail.sectionTo',
    'detail.sectionReset', 'detail.sectionDownloadGpx',
    'detail.sectionQrCode', 'detail.sectionQrDownload',
  ];
  const result: Record<string, string> = {};
  for (const key of keys) {
    result[key] = t(locale, key);
  }
  return result;
}
