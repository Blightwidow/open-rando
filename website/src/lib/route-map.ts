import maplibregl from 'maplibre-gl';
import { createMap, resolvePmtilesUrl, switchTheme, TRAIL_COLOR, POI_COLORS, POI_RADII } from './map';
import {
  OVERLAY_PMTILES_PATH,
  addOverlay,
  defaultVisibleGroups,
  getOverlayGroups,
  setOverlayGroupVisibility,
} from './overlay';
import { buildPoiPopupHtml, escapeHtml } from './poi-popup';
import { buildRailServiceRows, type RailServiceLabels } from './rail';
import {
  buildCumulativeDistancesKm,
  collectTrailCoordinates,
  findSectionIndexRange,
  interpolateAtDistance,
  orderSectionBounds,
  type LatLon,
} from './trail-geometry';

/** Copy the page renders into `data-labels`, so one script serves every locale. */
export interface RouteMapLabels {
  popup: { website: string; timetable: string };
  rail: RailServiceLabels;
  poiLayers: Record<string, string>;
  /** Overlay legend: `title` plus one label per overlay group key. */
  overlay: Record<string, string>;
}

const POI_TYPES = ['train_station', 'bus_stop', 'hotel', 'camping'] as const;
const EMPTY_COLLECTION = { type: 'FeatureCollection', features: [] } as const;

/** Detail-page map: trail, POI layers, elevation-chart hover marker, section highlight, layer toggles. */
export function initRouteMap(mapElement: HTMLElement): void {
  const routeData = JSON.parse(mapElement.dataset.route!);
  const labels: RouteMapLabels = JSON.parse(mapElement.dataset.labels!);
  const map = createMap(mapElement);

  const visibleOverlayGroups = defaultVisibleGroups();
  let trailCoordinates: LatLon[] = [];
  let cumulativeDistances: number[] = [0];

  function buildPoiFeatures(): Record<string, any[]> {
    const featuresByType: Record<string, any[]> = Object.fromEntries(POI_TYPES.map((type) => [type, []]));
    for (const poi of routeData.pois ?? []) {
      if (!featuresByType[poi.poi_type]) continue;
      let popupHtml = buildPoiPopupHtml(poi, labels.popup);

      const railRows = buildRailServiceRows(poi.rail_service, labels.rail);
      if (railRows.length > 0) {
        const rowsHtml = railRows
          .map((row) => `<div><span class="font-medium">${escapeHtml(row.label)}</span> ${escapeHtml(row.text)}</div>`)
          .join('');
        popupHtml += `<div class="mt-1 text-xs text-stone-600 dark:text-stone-300">${rowsHtml}</div>`;
      }

      featuresByType[poi.poi_type].push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [poi.lon, poi.lat] },
        properties: { name: poi.name, popupHtml },
      });
    }
    return featuresByType;
  }

  function addPoiLayers(): void {
    for (const [poiType, features] of Object.entries(buildPoiFeatures())) {
      map.addSource(`poi-${poiType}`, { type: 'geojson', data: { type: 'FeatureCollection', features } });
      map.addLayer({
        id: `poi-${poiType}`,
        type: 'circle',
        source: `poi-${poiType}`,
        paint: {
          'circle-radius': POI_RADII[poiType] ?? 5,
          'circle-color': POI_COLORS[poiType] ?? '#888',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
          'circle-opacity': 0.9,
        },
      });

      map.on('click', `poi-${poiType}`, (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const coordinates = (feature.geometry as any).coordinates.slice();
        new maplibregl.Popup().setLngLat(coordinates).setHTML(feature.properties.popupHtml).addTo(map);
      });
      map.on('mouseenter', `poi-${poiType}`, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', `poi-${poiType}`, () => {
        map.getCanvas().style.cursor = '';
      });
    }
  }

  function addHoverMarkerLayer(): void {
    map.addSource('hover-marker', { type: 'geojson', data: EMPTY_COLLECTION as any });
    map.addLayer({
      id: 'hover-marker',
      type: 'circle',
      source: 'hover-marker',
      paint: {
        'circle-radius': 7,
        'circle-color': TRAIL_COLOR,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
      },
    });
  }

  function addSectionHighlightLayer(): void {
    map.addSource('section-highlight', { type: 'geojson', data: EMPTY_COLLECTION as any });
    map.addLayer({
      id: 'section-highlight',
      type: 'line',
      source: 'section-highlight',
      paint: { 'line-color': '#2563eb', 'line-width': 5, 'line-opacity': 0.9 },
    });
  }

  async function loadRoute(waitForLoad = true): Promise<void> {
    // The first call waits for the map's one-time `load`. After a theme switch (setStyle) the caller
    // is already inside `style.load` and `load` never fires again, so it skips the wait.
    if (waitForLoad) {
      await new Promise<void>((resolve) => {
        if (map.isStyleLoaded()) resolve();
        else map.on('load', () => resolve());
      });
    }

    // First, so the trail and POIs draw above it.
    addOverlay(
      map,
      resolvePmtilesUrl(OVERLAY_PMTILES_PATH),
      document.documentElement.classList.contains('dark'),
      visibleOverlayGroups,
    );

    try {
      const response = await fetch(`/data/${routeData.geojson_path}`);
      const geojson = await response.json();
      const trailFeatures = geojson.features.filter((feature: any) => feature.properties.feature_type === 'trail');

      map.addSource('trail', { type: 'geojson', data: { type: 'FeatureCollection', features: trailFeatures } });
      map.addLayer({
        id: 'trail-line',
        type: 'line',
        source: 'trail',
        paint: { 'line-color': TRAIL_COLOR, 'line-width': 3, 'line-opacity': 0.8 },
      });

      addPoiLayers();

      trailCoordinates = collectTrailCoordinates(trailFeatures);
      cumulativeDistances = buildCumulativeDistancesKm(trailCoordinates);

      const bounds = new maplibregl.LngLatBounds();
      for (const [latitude, longitude] of trailCoordinates) bounds.extend([longitude, latitude]);
      map.fitBounds(bounds, { padding: 30 });

      addHoverMarkerLayer();
      addSectionHighlightLayer();
      reapplySelectedSection();
    } catch (error) {
      console.error('Failed to load route GeoJSON:', error);
    }
  }

  /** After a style reload the highlight source is empty: redraw a section picked earlier. */
  function reapplySelectedSection(): void {
    const fromSelect = document.getElementById('section-from') as HTMLSelectElement | null;
    const toSelect = document.getElementById('section-to') as HTMLSelectElement | null;
    if (fromSelect?.value && toSelect?.value && fromSelect.value !== toSelect.value) {
      const bounds = orderSectionBounds(parseFloat(fromSelect.value), parseFloat(toSelect.value));
      document.dispatchEvent(new CustomEvent('section-change', { detail: bounds }));
    }
  }

  // Listeners are registered once: they read the current trail, which each (re)load replaces.
  document.addEventListener('elevation-hover', ((event: CustomEvent) => {
    const source = map.getSource('hover-marker') as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    const totalTrailDistance = cumulativeDistances[cumulativeDistances.length - 1];
    const distanceKm = event.detail.distanceKm;

    if (distanceKm === null || totalTrailDistance === 0) {
      source.setData(EMPTY_COLLECTION as any);
      return;
    }

    const targetDistance = Math.min(distanceKm / totalTrailDistance, 1) * totalTrailDistance;
    const [latitude, longitude] = interpolateAtDistance(trailCoordinates, cumulativeDistances, targetDistance);
    source.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [longitude, latitude] }, properties: {} }],
    });
  }) as EventListener);

  document.addEventListener('section-change', ((event: CustomEvent) => {
    const sectionSource = map.getSource('section-highlight') as maplibregl.GeoJSONSource | undefined;
    if (!sectionSource) return;

    map.setPaintProperty('trail-line', 'line-opacity', 0.8);

    const detail = event.detail;
    if (!detail || detail.startKm == null || detail.endKm == null) {
      sectionSource.setData(EMPTY_COLLECTION as any);
      return;
    }

    map.setPaintProperty('trail-line', 'line-opacity', 0.25);

    const { startIndex, endIndex } = findSectionIndexRange(cumulativeDistances, detail.startKm, detail.endKm);
    const lineCoordinates = trailCoordinates
      .slice(startIndex, endIndex + 1)
      .map(([latitude, longitude]) => [longitude, latitude]);
    if (lineCoordinates.length < 2) return;

    sectionSource.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: lineCoordinates }, properties: {} }],
    });
    const sectionBounds = new maplibregl.LngLatBounds();
    for (const coordinate of lineCoordinates) sectionBounds.extend(coordinate as [number, number]);
    map.fitBounds(sectionBounds, { padding: 30 });
  }) as EventListener);

  // MapLibre has no built-in layer control.
  const layerControl = document.createElement('div');
  layerControl.className =
    'absolute top-2 right-2 z-10 max-h-[calc(100%-1rem)] overflow-y-auto bg-white dark:bg-neutral-800 rounded-md shadow-md p-2 text-sm space-y-1';
  for (const poiType of POI_TYPES) {
    const row = document.createElement('label');
    row.className = 'flex items-center gap-2 cursor-pointer';
    row.innerHTML = `
      <input type="checkbox" checked class="rounded" data-poi-type="${poiType}" />
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${POI_COLORS[poiType]};"></span>
      ${labels.poiLayers[poiType]}
    `;
    const checkbox = row.querySelector('input')!;
    checkbox.addEventListener('change', () => {
      if (map.getLayer(`poi-${poiType}`)) {
        map.setLayoutProperty(`poi-${poiType}`, 'visibility', checkbox.checked ? 'visible' : 'none');
      }
    });
    layerControl.appendChild(row);
  }

  const overlayTitle = document.createElement('div');
  overlayTitle.className = 'pt-1 mt-1 border-t border-stone-200 dark:border-neutral-700 text-xs text-stone-500 dark:text-stone-400';
  overlayTitle.textContent = labels.overlay.title;
  layerControl.appendChild(overlayTitle);

  for (const group of getOverlayGroups(false)) {
    const row = document.createElement('label');
    row.className = 'flex items-center gap-2 cursor-pointer';
    const swatch =
      group.swatch === 'dot'
        ? `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${group.color};"></span>`
        : `<span style="display:inline-block;width:10px;height:0;border-top:2px solid ${group.color};"></span>`;
    row.innerHTML = `<input type="checkbox" class="rounded" data-overlay-group="${group.key}" /> ${swatch} ${escapeHtml(labels.overlay[group.key])}`;
    const checkbox = row.querySelector('input')!;
    checkbox.checked = visibleOverlayGroups.has(group.key);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) visibleOverlayGroups.add(group.key);
      else visibleOverlayGroups.delete(group.key);
      const currentGroup = getOverlayGroups(document.documentElement.classList.contains('dark')).find(
        (candidate) => candidate.key === group.key,
      )!;
      setOverlayGroupVisibility(map, currentGroup, checkbox.checked);
    });
    layerControl.appendChild(row);
  }

  mapElement.style.position = 'relative';
  mapElement.appendChild(layerControl);

  document.addEventListener('theme-change', () => {
    switchTheme(map);
    map.once('style.load', () => {
      loadRoute(false);
    });
  });

  loadRoute();
}
