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
  hotelAllStops: boolean;
  campingAllStops: boolean;
  difficulty: string;
  routeType: string;
  region: string;
  terrainTags: string[];
  suggestHidden: boolean;
}

export function matchesFilters(hike: HikeFilterData, filters: FilterState): boolean {
  if (hike.suggestHidden) return false;
  if (hike.maxStepDistance > filters.maxStepDistance) return false;
  if (hike.stepCount < filters.stepsMin || hike.stepCount > filters.stepsMax) return false;
  if (filters.requireHotel && !hike.hotelAllStops) return false;
  if (filters.requireCamping && !hike.campingAllStops) return false;
  if (filters.difficulties.size > 0 && !filters.difficulties.has(hike.difficulty)) return false;
  if (filters.routeTypes.size > 0 && !filters.routeTypes.has(hike.routeType)) return false;
  if (filters.regions.size > 0 && !filters.regions.has(hike.region)) return false;
  if (filters.terrains.size > 0 && !hike.terrainTags.some((tag) => filters.terrains.has(tag))) return false;
  return true;
}
