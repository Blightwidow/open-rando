import type { Hike } from './catalog';

export interface StationEntry {
  name: string;
  code: string;
}

export interface HikeStepEntry {
  duration: number;
  distance: number;
  startCode: string;
  endCode: string;
}

export interface HikeIndexEntry {
  hikeId: string;
  stepCount: number;
  steps: HikeStepEntry[];
  stationPositions: Record<string, number[]>;
}

export interface Suggestion {
  hikeId: string;
  fromStep: number;
  toStep: number;
  totalDuration: number;
  totalDistance: number;
  startsHere: boolean;
}

export function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

export function extractStations(hikes: Hike[]): StationEntry[] {
  const stationMap = new Map<string, StationEntry>();
  for (const hike of hikes) {
    for (const step of hike.steps) {
      if (!stationMap.has(step.start_station.code)) {
        stationMap.set(step.start_station.code, {
          name: step.start_station.name,
          code: step.start_station.code,
        });
      }
      if (!stationMap.has(step.end_station.code)) {
        stationMap.set(step.end_station.code, {
          name: step.end_station.name,
          code: step.end_station.code,
        });
      }
    }
  }
  return Array.from(stationMap.values()).sort((stationA, stationB) =>
    stationA.name.localeCompare(stationB.name, 'fr')
  );
}

export function buildHikeStationIndex(hikes: Hike[]): HikeIndexEntry[] {
  return hikes.map((hike) => {
    const allStations = [
      ...hike.steps.map((step) => step.start_station),
      hike.steps[hike.steps.length - 1].end_station,
    ];
    const stationPositions: Record<string, number[]> = {};
    allStations.forEach((station, index) => {
      if (!stationPositions[station.code]) stationPositions[station.code] = [];
      stationPositions[station.code].push(index);
    });
    return {
      hikeId: hike.id,
      stepCount: hike.step_count,
      steps: hike.steps.map((step) => ({
        duration: step.estimated_duration_min,
        distance: step.distance_km,
        startCode: step.start_station.code,
        endCode: step.end_station.code,
      })),
      stationPositions,
    };
  });
}

export function findSuggestions(hikeIndex: HikeIndexEntry[], stationCode: string, maxMinutes: number): Suggestion[] {
  const results: Suggestion[] = [];

  for (const hike of hikeIndex) {
    const positions = hike.stationPositions[stationCode];
    if (!positions) continue;

    for (const position of positions) {
      // Sections departing FROM this station (forward expansion)
      if (position < hike.steps.length) {
        let duration = 0;
        let distance = 0;
        for (let endIndex = position; endIndex < hike.steps.length; endIndex++) {
          duration += hike.steps[endIndex].duration;
          distance += hike.steps[endIndex].distance;
          if (duration > maxMinutes) break;
          results.push({
            hikeId: hike.hikeId,
            fromStep: position,
            toStep: endIndex + 1,
            totalDuration: duration,
            totalDistance: distance,
            startsHere: true,
          });
        }
      }

      // Sections arriving AT this station (backward expansion)
      if (position > 0) {
        let duration = 0;
        let distance = 0;
        for (let startIndex = position - 1; startIndex >= 0; startIndex--) {
          duration += hike.steps[startIndex].duration;
          distance += hike.steps[startIndex].distance;
          if (duration > maxMinutes) break;
          // Skip if the start station is already covered as a "departs from" result
          if (positions.includes(startIndex)) continue;
          results.push({
            hikeId: hike.hikeId,
            fromStep: startIndex,
            toStep: position,
            totalDuration: duration,
            totalDistance: distance,
            startsHere: false,
          });
        }
      }
    }
  }

  // Sort: departures first, then by time utilization (higher = closer to budget)
  results.sort((resultA, resultB) => {
    if (resultA.startsHere !== resultB.startsHere) return resultA.startsHere ? -1 : 1;
    const utilizationA = resultA.totalDuration / maxMinutes;
    const utilizationB = resultB.totalDuration / maxMinutes;
    return utilizationB - utilizationA;
  });

  // Deduplicate: keep only the best suggestion per hike
  const seen = new Set<string>();
  return results.filter((result) => {
    if (seen.has(result.hikeId)) return false;
    seen.add(result.hikeId);
    return true;
  });
}
