export type Locale = 'fr' | 'en';

const translations: Record<Locale, Record<string, string>> = {
  fr: {
    // Header & navigation
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
    'landing.mobile.title': 'Application mobile',
    'landing.mobile.description': "L'application compagnon pour randonner sans réseau : enregistrez un itinéraire ou une section (depuis le QR code du site), importez un fichier GPX et suivez votre position GPS sur la carte.",
    'landing.mobile.cta': 'Télécharger pour Android',
    'landing.mobile.note': 'APK à installer à la main, F-Droid et AltStore sont prévus. Ni compte, ni analytics.',
    'landing.mobile.screenshotExplore': "Liste des itinéraires de l'application mobile, avec distance, dénivelé et difficulté",
    'landing.mobile.screenshotOffline': "Page d'un itinéraire enregistré pour le hors-ligne : carte, arrêts de bus et profil d'altitude",
    'landing.mobile.screenshotNavigation': "Suivi en cours : position GPS sur la carte, distance restante et avance sur le profil d'altitude",

    // Footer
    'footer.about': 'À propos',
    'footer.privacy': 'Confidentialité',
    'footer.legal': 'Mentions légales',

    // Filters
    'filters.title': 'Filtres',
    'filters.reset': 'Réinitialiser',
    'filters.region': 'Région',
    'filters.terrain': 'Terrain',
    'terrain.coastal': 'Littoral',
    'terrain.mountain': 'Montagne',
    'terrain.hills': 'Collines',
    'terrain.forest': 'Forêt',
    'terrain.plains': 'Plaines',
    'filters.noResults': 'Aucune randonnée ne correspond à vos filtres.',

    // Tabs
    'tabs.list': 'Liste',
    'tabs.map': 'Carte',
    'map.loading': 'Chargement des sentiers…',
    'explore.trails': 'sentiers',
    'detail.pageDescription': '{name} — {distance} km, {count} gares',
    'detail.imageAlt': 'Illustration aquarelle de {name}',
    'detail.stationCount': '{count} gares',
    'detail.busStopCount': '{count} arrêts bus',
    'detail.hotelCount': '{count} hôtels',
    'detail.campingCount': '{count} campings',
    'detail.shopCount': '{count} commerces',
    'detail.eateryCount': '{count} cafés et restaurants',
    'poi.website': 'Site web',
    'poi.timetable': 'Horaires',
    'poi.layer.train_station': 'Gares',
    'poi.layer.bus_stop': 'Bus',
    'poi.layer.hotel': 'Hôtels',
    'poi.layer.camping': 'Campings',
    'poi.openingHours': 'Ouverture :',
    'poi.layer.shop': 'Commerces',
    'poi.layer.eatery': 'Cafés et restaurants',
    'poi.category.supermarket': "Supermarché",
    'poi.category.convenience': "Supérette",
    'poi.category.bakery': "Boulangerie",
    'poi.category.butcher': "Boucherie",
    'poi.category.greengrocer': "Primeur",
    'poi.category.general': "Épicerie générale",
    'poi.category.farm': "Vente à la ferme",
    'poi.category.deli': "Traiteur",
    'poi.category.cheese': "Fromagerie",
    'poi.category.restaurant': "Restaurant",
    'poi.category.cafe': "Café",
    'poi.category.bar': "Bar",
    'overlay.title': 'Sur la carte',
    'overlay.river': "Cours d'eau (sens du courant)",
    'overlay.water': 'Eau potable, fontaines et sources',
    'overlay.shelter': 'Abris et refuges',
    'overlay.peak': 'Sommets et cols',
    'overlay.viewpoint': 'Points de vue',
    'overlay.nature': 'Cascades et grottes',
    'overlay.crossing': 'Ponts et gués',
    'overlay.landmark': 'Églises et cimetières',
    'overlay.toilets': 'Toilettes',
    'overlay.aerialway': 'Remontées mécaniques',
    'overlay.guidepost': 'Poteaux de balisage',
    'overlay.power': 'Lignes électriques',

    // Difficulty
    'difficulty.easy': 'Facile',
    'difficulty.moderate': 'Modéré',
    'difficulty.difficult': 'Difficile',
    'difficulty.very_difficult': 'Très difficile',

    // Detail page
    'detail.summary': 'Résumé',
    'detail.distance': 'Distance',
    'detail.estimatedDuration': 'Durée estimée',
    'detail.trail': 'Sentier',
    'detail.elevationGain': 'Dénivelé positif',
    'detail.elevationLoss': 'Dénivelé négatif',
    'detail.maxAltitude': 'Altitude max',
    'detail.downloadGpx': 'Télécharger GPX',
    'detail.elevationProfile': 'Profil altimétrique',
    'detail.timeDisclaimer': 'Temps estimés : 4 km/h sur le plat, +300 m/h en montée et -450 m/h en descente (pentes \u2265 10 %).',
    'detail.loading': 'Chargement...',
    'detail.trailGapNote': "Tracé en {count} tronçons : environ {gap} km non cartographiés entre eux, non comptés dans la distance. Prévoyez de rejoindre le tronçon suivant par vos propres moyens.",
    'detail.trailGapLegend': 'Interruption du tracé',
    'detail.trailGapMarker': 'Interruption du tracé (tronçon non cartographié)',
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

    // Footer
    'footer.data': 'Données',

    // Disclaimer
    'detail.disclaimer': 'Les informations présentées (tracés, hébergements, gares) sont issues de données ouvertes et peuvent être incomplètes ou obsolètes. Vérifiez la disponibilité des hébergements, campings et horaires de train avant de partir.',

    // Theme
    'theme.toggle': 'Basculer thème sombre',
  },
  en: {
    // Header & navigation
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
    'landing.mobile.title': 'Mobile app',
    'landing.mobile.description': "The companion app for hiking without a signal: save a route or a section (from the website's QR code), import a GPX file and follow your GPS position on the map.",
    'landing.mobile.cta': 'Download for Android',
    'landing.mobile.note': 'APK to install by hand; F-Droid and AltStore are planned. No account, no analytics.',
    'landing.mobile.screenshotExplore': 'Route list in the mobile app, with distance, elevation gain and difficulty',
    'landing.mobile.screenshotOffline': 'A route saved for offline use: map, bus stops and elevation profile',
    'landing.mobile.screenshotNavigation': 'Live following: GPS position on the map, remaining distance and time ahead on the elevation profile',

    // Footer
    'footer.about': 'About',
    'footer.privacy': 'Privacy',
    'footer.legal': 'Legal',

    // Filters
    'filters.title': 'Filters',
    'filters.reset': 'Reset',
    'filters.region': 'Region',
    'filters.terrain': 'Terrain',
    'terrain.coastal': 'Coastal',
    'terrain.mountain': 'Mountain',
    'terrain.hills': 'Hills',
    'terrain.forest': 'Forest',
    'terrain.plains': 'Plains',
    'filters.noResults': 'No hikes match your filters.',

    // Tabs
    'tabs.list': 'List',
    'tabs.map': 'Map',
    'map.loading': 'Loading trails…',
    'explore.trails': 'trails',
    'detail.pageDescription': '{name} — {distance} km, {count} stations',
    'detail.imageAlt': 'Watercolor illustration of {name}',
    'detail.stationCount': '{count} stations',
    'detail.busStopCount': '{count} bus stops',
    'detail.hotelCount': '{count} hotels',
    'detail.campingCount': '{count} campsites',
    'detail.shopCount': '{count} food shops',
    'detail.eateryCount': '{count} cafes and restaurants',
    'poi.website': 'Website',
    'poi.timetable': 'Timetable',
    'poi.layer.train_station': 'Stations',
    'poi.layer.bus_stop': 'Bus stops',
    'poi.layer.hotel': 'Hotels',
    'poi.layer.camping': 'Campsites',
    'poi.openingHours': 'Hours:',
    'poi.layer.shop': 'Food shops',
    'poi.layer.eatery': 'Cafes and restaurants',
    'poi.category.supermarket': "Supermarket",
    'poi.category.convenience': "Convenience store",
    'poi.category.bakery': "Bakery",
    'poi.category.butcher': "Butcher",
    'poi.category.greengrocer': "Greengrocer",
    'poi.category.general': "General store",
    'poi.category.farm': "Farm shop",
    'poi.category.deli': "Delicatessen",
    'poi.category.cheese': "Cheese shop",
    'poi.category.restaurant': "Restaurant",
    'poi.category.cafe': "Cafe",
    'poi.category.bar': "Bar",
    'overlay.title': 'On the map',
    'overlay.river': 'Rivers (flow direction)',
    'overlay.water': 'Drinking water, taps and springs',
    'overlay.shelter': 'Shelters and huts',
    'overlay.peak': 'Peaks and passes',
    'overlay.viewpoint': 'Viewpoints',
    'overlay.nature': 'Waterfalls and caves',
    'overlay.crossing': 'Bridges and fords',
    'overlay.landmark': 'Churches and cemeteries',
    'overlay.toilets': 'Toilets',
    'overlay.aerialway': 'Cable cars and lifts',
    'overlay.guidepost': 'Guideposts',
    'overlay.power': 'Power lines',

    // Difficulty
    'difficulty.easy': 'Easy',
    'difficulty.moderate': 'Moderate',
    'difficulty.difficult': 'Difficult',
    'difficulty.very_difficult': 'Very difficult',

    // Detail page
    'detail.summary': 'Summary',
    'detail.distance': 'Distance',
    'detail.estimatedDuration': 'Estimated duration',
    'detail.trail': 'Trail',
    'detail.elevationGain': 'Elevation gain',
    'detail.elevationLoss': 'Elevation loss',
    'detail.maxAltitude': 'Max altitude',
    'detail.downloadGpx': 'Download GPX',
    'detail.elevationProfile': 'Elevation profile',
    'detail.timeDisclaimer': 'Estimated times: 4 km/h on flat terrain, +300 m/h uphill, -450 m/h downhill (slopes \u2265 10%).',
    'detail.loading': 'Loading...',
    'detail.trailGapNote': "Trail mapped in {count} segments: about {gap} km unmapped between them, not counted in the distance. Plan your own way to the next segment.",
    'detail.trailGapLegend': 'Trail break',
    'detail.trailGapMarker': 'Trail break (unmapped stretch)',
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

    // Footer
    'footer.data': 'Data',

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

/** URL path for a page in a locale: French lives at the root, English under /en. */
export function localePath(locale: Locale, path: string): string {
  if (locale === 'fr') return path;
  return path === '/' ? '/en' : `/en${path}`;
}

/** `getStaticPaths` entries for a page that exists once per locale (`pages/[...locale]/`). */
export function getLocaleStaticPaths(): { params: { locale: string | undefined }; props: { locale: Locale } }[] {
  return [
    { params: { locale: undefined }, props: { locale: 'fr' } },
    { params: { locale: 'en' }, props: { locale: 'en' } },
  ];
}

/** Every key of a locale, for tests that guard the dictionary. */
export function getTranslationKeys(locale: Locale): string[] {
  return Object.keys(translations[locale]);
}
