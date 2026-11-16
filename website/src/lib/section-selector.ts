import qrGenerator from 'qrcode-generator';
import type { RouteElevationProfile } from './catalog';
import { formatTime } from './elevation';
import { buildSectionGpx, sectionGpxFileName } from './section-gpx';
import {
  buildCumulativeDistancesKm,
  collectTrailCoordinates,
  findIndexAtDistance,
  findSectionIndexRange,
  orderSectionBounds,
} from './trail-geometry';

const SITE_ORIGIN = 'https://rando.dammaretz.fr';
const QR_PNG_SCALE = 4;

interface SectionStation {
  name: string;
  distance_km: number;
}

function requireElement(id: string): HTMLElement {
  return document.getElementById(id)!;
}

function dispatchSectionChange(detail: { startKm: number; endKm: number } | null): void {
  document.dispatchEvent(new CustomEvent('section-change', { detail }));
}

function updateUrlParams(fromValue: string, toValue: string): void {
  const url = new URL(window.location.href);
  if (fromValue && toValue) {
    url.searchParams.set('from', fromValue);
    url.searchParams.set('to', toValue);
  } else {
    url.searchParams.delete('from');
    url.searchParams.delete('to');
  }
  window.history.replaceState({}, '', url.toString());
}

function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

/** Section picker on the detail page: stats, GPX download, QR code, URL state, map highlight events. */
export function initSectionSelector(selectorElement: HTMLElement): void {
  const stations: SectionStation[] = JSON.parse(selectorElement.dataset.stations!);
  const elevationPath = selectorElement.dataset.elevationPath!;
  const geojsonPath = selectorElement.dataset.geojsonPath!;
  const routeRef = selectorElement.dataset.routeRef!;

  const fromSelect = requireElement('section-from') as HTMLSelectElement;
  const toSelect = requireElement('section-to') as HTMLSelectElement;
  const statsContainer = requireElement('section-stats');
  const qrPanel = requireElement('section-qr');
  const qrContainer = requireElement('qr-container');

  for (const select of [fromSelect, toSelect]) {
    for (const station of stations) {
      const option = document.createElement('option');
      option.value = String(station.distance_km);
      option.textContent = station.name;
      select.appendChild(option);
    }
  }

  let elevationProfile: RouteElevationProfile | null = null;

  async function loadElevationProfile(): Promise<RouteElevationProfile | null> {
    if (elevationProfile) return elevationProfile;
    try {
      const response = await fetch(`/data/${elevationPath}`);
      if (!response.ok) return null;
      elevationProfile = await response.json();
      return elevationProfile;
    } catch {
      return null;
    }
  }

  function clearSection(): void {
    statsContainer.classList.add('hidden');
    updateUrlParams('', '');
    dispatchSectionChange(null);
  }

  async function updateSection(): Promise<void> {
    const fromValue = fromSelect.value;
    const toValue = toSelect.value;
    if (!fromValue || !toValue || fromValue === toValue) {
      clearSection();
      return;
    }

    const { startKm, endKm } = orderSectionBounds(parseFloat(fromValue), parseFloat(toValue));
    const profile = await loadElevationProfile();
    if (!profile) return;

    const startIndex = findIndexAtDistance(profile.distances_km, startKm);
    const endIndex = findIndexAtDistance(profile.distances_km, endKm);

    let gain = 0;
    let loss = 0;
    for (let index = startIndex; index < endIndex; index++) {
      const delta = profile.elevations_m[index + 1] - profile.elevations_m[index];
      if (delta > 0) gain += delta;
      else loss += Math.abs(delta);
    }
    const durationMinutes = profile.times_min[endIndex] - profile.times_min[startIndex];

    requireElement('section-distance').textContent = `${Math.abs(endKm - startKm).toFixed(1)} km`;
    requireElement('section-gain').textContent = `+${Math.round(gain)}m`;
    requireElement('section-loss').textContent = `-${Math.round(loss)}m`;
    requireElement('section-duration').textContent = formatTime(Math.abs(durationMinutes));

    statsContainer.classList.remove('hidden');
    updateUrlParams(fromValue, toValue);
    qrPanel.classList.add('hidden');
    dispatchSectionChange({ startKm, endKm });
  }

  fromSelect.addEventListener('change', updateSection);
  toSelect.addEventListener('change', updateSection);

  requireElement('section-reset').addEventListener('click', () => {
    fromSelect.value = '';
    toSelect.value = '';
    qrPanel.classList.add('hidden');
    clearSection();
  });

  requireElement('section-qr-toggle').addEventListener('click', () => {
    if (qrPanel.classList.contains('hidden')) {
      const qr = qrGenerator(0, 'M');
      qr.addData(`${SITE_ORIGIN}${window.location.pathname}${window.location.search}`);
      qr.make();
      qrContainer.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0 });
      qrPanel.classList.remove('hidden');
    } else {
      qrPanel.classList.add('hidden');
    }
  });

  requireElement('section-qr-close').addEventListener('click', () => {
    qrPanel.classList.add('hidden');
  });

  requireElement('section-qr-download').addEventListener('click', () => {
    const svgElement = qrContainer.querySelector('svg');
    if (!svgElement) return;

    const svgBlob = new Blob([new XMLSerializer().serializeToString(svgElement)], {
      type: 'image/svg+xml;charset=utf-8',
    });
    const blobUrl = URL.createObjectURL(svgBlob);
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = image.width * QR_PNG_SCALE;
      canvas.height = image.height * QR_PNG_SCALE;
      const context = canvas.getContext('2d')!;
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((pngBlob) => {
        if (pngBlob) downloadBlob(pngBlob, `${routeRef.replace(/\s+/g, '-')}-section-qr.png`);
      }, 'image/png');
      URL.revokeObjectURL(blobUrl);
    };
    image.src = blobUrl;
  });

  requireElement('section-download-gpx').addEventListener('click', async () => {
    const fromValue = fromSelect.value;
    const toValue = toSelect.value;
    if (!fromValue || !toValue) return;

    const { startKm, endKm } = orderSectionBounds(parseFloat(fromValue), parseFloat(toValue));
    const stationName = (value: string) =>
      stations.find((station) => String(station.distance_km) === value)?.name ?? '';
    const fromName = stationName(fromValue);
    const toName = stationName(toValue);

    const geojson = await (await fetch(`/data/${geojsonPath}`)).json();
    const trailFeatures = geojson.features.filter((feature: any) => feature.properties.feature_type === 'trail');
    const coordinates = collectTrailCoordinates(trailFeatures);
    const cumulativeDistances = buildCumulativeDistancesKm(coordinates);
    const { startIndex, endIndex } = findSectionIndexRange(cumulativeDistances, startKm, endKm);

    const gpx = buildSectionGpx({
      routeRef,
      fromName,
      toName,
      sectionCoordinates: coordinates.slice(startIndex, endIndex + 1),
      firstIndex: startIndex,
      cumulativeDistances,
      endKm,
      profile: await loadElevationProfile(),
    });
    downloadBlob(new Blob([gpx], { type: 'application/gpx+xml' }), sectionGpxFileName(routeRef, fromName, toName));
  });

  // Restore a section shared through the URL.
  const urlParams = new URLSearchParams(window.location.search);
  const urlFrom = urlParams.get('from');
  const urlTo = urlParams.get('to');
  if (urlFrom && urlTo) {
    const validValues = new Set(stations.map((station) => String(station.distance_km)));
    if (validValues.has(urlFrom) && validValues.has(urlTo)) {
      fromSelect.value = urlFrom;
      toSelect.value = urlTo;
      updateSection();
    }
  }
}
