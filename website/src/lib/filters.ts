export interface FilterState {
  maxStepDistance: number;
  stepsMin: number;
  stepsMax: number;
  requireHotel: boolean;
  requireCamping: boolean;
  difficulties: Set<string>;
  routeTypes: Set<string>;
  regions: Set<string>;
  terrains: Set<string>;
}

export interface HikeFilterData {
  maxStepDistance: number;
  stepCount: number;
  stepDistances: number[];
  hotelAllStops: boolean;
  campingAllStops: boolean;
  difficulty: string;
  routeType: string;
  region: string;
  terrainTags: string[];
  suggestHidden: boolean;
}

export interface SectionMatch {
  from: number;
  to: number;
  length: number;
}

export interface FilterResult {
  visible: boolean;
  sectionMatch: SectionMatch | null;
}

export function findLongestMatchingSection(
  stepDistances: number[],
  maxDistance: number,
): SectionMatch | null {
  let bestFrom = -1;
  let bestLength = 0;
  let currentFrom = -1;
  let currentLength = 0;

  for (let index = 0; index < stepDistances.length; index++) {
    if (stepDistances[index] <= maxDistance) {
      if (currentFrom === -1) currentFrom = index;
      currentLength++;
      if (currentLength > bestLength) {
        bestFrom = currentFrom;
        bestLength = currentLength;
      }
    } else {
      currentFrom = -1;
      currentLength = 0;
    }
  }

  if (bestLength === 0) return null;
  return { from: bestFrom, to: bestFrom + bestLength, length: bestLength };
}

export function matchesFilters(hike: HikeFilterData, filters: FilterState): FilterResult {
  const reject: FilterResult = { visible: false, sectionMatch: null };

  if (hike.suggestHidden) return reject;

  // Check distance + step count together (section-aware)
  const allStepsFit = hike.maxStepDistance <= filters.maxStepDistance;
  if (allStepsFit) {
    // Full hike fits distance — check step count against full hike
    if (hike.stepCount < filters.stepsMin || hike.stepCount > filters.stepsMax) return reject;
  } else {
    // Some steps exceed limit — find longest matching section
    const section = findLongestMatchingSection(hike.stepDistances, filters.maxStepDistance);
    if (!section) return reject;
    // Check step count against section length
    if (section.length < filters.stepsMin || section.length > filters.stepsMax) return reject;
    // Non-distance filters still apply to the full hike
    if (filters.requireHotel && !hike.hotelAllStops) return reject;
    if (filters.requireCamping && !hike.campingAllStops) return reject;
    if (filters.difficulties.size > 0 && !filters.difficulties.has(hike.difficulty)) return reject;
    if (filters.routeTypes.size > 0 && !filters.routeTypes.has(hike.routeType)) return reject;
    if (filters.regions.size > 0 && !filters.regions.has(hike.region)) return reject;
    if (filters.terrains.size > 0 && !hike.terrainTags.some((tag) => filters.terrains.has(tag))) return reject;
    return { visible: true, sectionMatch: section };
  }

  if (filters.requireHotel && !hike.hotelAllStops) return reject;
  if (filters.requireCamping && !hike.campingAllStops) return reject;
  if (filters.difficulties.size > 0 && !filters.difficulties.has(hike.difficulty)) return reject;
  if (filters.routeTypes.size > 0 && !filters.routeTypes.has(hike.routeType)) return reject;
  if (filters.regions.size > 0 && !filters.regions.has(hike.region)) return reject;
  if (filters.terrains.size > 0 && !hike.terrainTags.some((tag) => filters.terrains.has(tag))) return reject;
  return { visible: true, sectionMatch: null };
}
