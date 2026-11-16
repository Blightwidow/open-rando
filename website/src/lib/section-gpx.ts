import type { RouteElevationProfile } from './catalog';
import { findIndexAtDistance, type LatLon } from './trail-geometry';

interface SectionGpxInput {
  routeRef: string;
  fromName: string;
  toName: string;
  /** Coordinates of the section only, [lat, lon]. */
  sectionCoordinates: LatLon[];
  /** Index of the first section coordinate in the full trail. */
  firstIndex: number;
  /** Walked km at each coordinate of the full trail. */
  cumulativeDistances: number[];
  /** Used for coordinates past the end of `cumulativeDistances`. */
  endKm: number;
  profile: Pick<RouteElevationProfile, 'distances_km' | 'elevations_m'> | null;
}

/** GPX 1.1 track for one section of a route, with elevation looked up from the profile when known. */
export function buildSectionGpx(input: SectionGpxInput): string {
  const { routeRef, fromName, toName, sectionCoordinates, firstIndex, cumulativeDistances, endKm, profile } = input;

  let trackPoints = '';
  for (let offset = 0; offset < sectionCoordinates.length; offset++) {
    const [latitude, longitude] = sectionCoordinates[offset];
    let elevation = '';
    if (profile) {
      const absoluteIndex = firstIndex + offset;
      const coordinateDistanceKm =
        absoluteIndex < cumulativeDistances.length ? cumulativeDistances[absoluteIndex] : endKm;
      const profileIndex = findIndexAtDistance(profile.distances_km, coordinateDistanceKm);
      if (profileIndex < profile.elevations_m.length) {
        elevation = `<ele>${profile.elevations_m[profileIndex].toFixed(1)}</ele>`;
      }
    }
    trackPoints += `      <trkpt lat="${latitude.toFixed(6)}" lon="${longitude.toFixed(6)}">${elevation}</trkpt>\n`;
  }

  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="TrainRando" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>${routeRef} — ${fromName} → ${toName}</name>
    <trkseg>
${trackPoints}    </trkseg>
  </trk>
</gpx>`;
}

export function sectionGpxFileName(routeRef: string, fromName: string, toName: string): string {
  const dashed = (text: string) => text.replace(/\s+/g, '-');
  return `${dashed(routeRef)}_${dashed(fromName)}_${dashed(toName)}.gpx`;
}
