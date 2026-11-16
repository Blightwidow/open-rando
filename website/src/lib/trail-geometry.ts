/** [latitude, longitude] */
export type LatLon = [number, number];

interface TrailFeatureLike {
  geometry: { type: string; coordinates: any };
}

const EARTH_RADIUS_KM = 6371;

export function haversineKm(
  latitudeA: number,
  longitudeA: number,
  latitudeB: number,
  longitudeB: number,
): number {
  const deltaLatitude = ((latitudeB - latitudeA) * Math.PI) / 180;
  const deltaLongitude = ((longitudeB - longitudeA) * Math.PI) / 180;
  const halfChordSquared =
    Math.sin(deltaLatitude / 2) ** 2 +
    Math.cos((latitudeA * Math.PI) / 180) *
      Math.cos((latitudeB * Math.PI) / 180) *
      Math.sin(deltaLongitude / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(halfChordSquared), Math.sqrt(1 - halfChordSquared));
}

/** Flatten trail features (LineString or MultiLineString, GeoJSON [lon, lat]) into [lat, lon] points. */
export function collectTrailCoordinates(features: TrailFeatureLike[]): LatLon[] {
  const coordinates: LatLon[] = [];
  for (const feature of features) {
    const geometry = feature.geometry;
    const lines = geometry.type === 'MultiLineString' ? geometry.coordinates : [geometry.coordinates];
    for (const line of lines) {
      for (const [longitude, latitude] of line) {
        coordinates.push([latitude, longitude]);
      }
    }
  }
  return coordinates;
}

/** Walked distance in km at each coordinate; the first entry is 0. */
export function buildCumulativeDistancesKm(coordinates: LatLon[]): number[] {
  const cumulativeDistances: number[] = [0];
  for (let index = 1; index < coordinates.length; index++) {
    const [previousLatitude, previousLongitude] = coordinates[index - 1];
    const [latitude, longitude] = coordinates[index];
    cumulativeDistances.push(
      cumulativeDistances[index - 1] + haversineKm(previousLatitude, previousLongitude, latitude, longitude),
    );
  }
  return cumulativeDistances;
}

/** Index of the last entry at or below `targetKm` in an ascending distance list. */
export function findIndexAtDistance(distances: number[], targetKm: number): number {
  let low = 0;
  let high = distances.length - 1;
  while (low < high - 1) {
    const middle = (low + high) >> 1;
    if (distances[middle] <= targetKm) low = middle;
    else high = middle;
  }
  return low;
}

/** Order a pair of distances so the section always runs from the smaller to the larger. */
export function orderSectionBounds(firstKm: number, secondKm: number): { startKm: number; endKm: number } {
  return firstKm > secondKm ? { startKm: secondKm, endKm: firstKm } : { startKm: firstKm, endKm: secondKm };
}

/** Coordinate indices covering a section: from the point at `startKm` to one past the point at `endKm`. */
export function findSectionIndexRange(
  cumulativeDistances: number[],
  startKm: number,
  endKm: number,
): { startIndex: number; endIndex: number } {
  const startIndex = findIndexAtDistance(cumulativeDistances, startKm);
  const endIndex = Math.min(findIndexAtDistance(cumulativeDistances, endKm) + 1, cumulativeDistances.length - 1);
  return { startIndex, endIndex };
}

/** Point on the trail at `distanceKm` along it, interpolated between the two surrounding coordinates. */
export function interpolateAtDistance(
  coordinates: LatLon[],
  cumulativeDistances: number[],
  distanceKm: number,
): LatLon {
  const high = Math.min(findIndexAtDistance(cumulativeDistances, distanceKm) + 1, cumulativeDistances.length - 1);
  const low = Math.max(high - 1, 0);
  const segmentLength = cumulativeDistances[high] - cumulativeDistances[low];
  const fraction = segmentLength > 0 ? (distanceKm - cumulativeDistances[low]) / segmentLength : 0;
  return [
    coordinates[low][0] + (coordinates[high][0] - coordinates[low][0]) * fraction,
    coordinates[low][1] + (coordinates[high][1] - coordinates[low][1]) * fraction,
  ];
}
