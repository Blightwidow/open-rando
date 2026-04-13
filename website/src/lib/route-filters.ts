export interface RouteFilterState {
  regions: Set<string>;
  terrains: Set<string>;
}

export interface RouteFilterData {
  region: string;
  terrainTags: string[];
}

export function defaultRouteFilterState(): RouteFilterState {
  return {
    regions: new Set(),
    terrains: new Set(),
  };
}

export function matchesRouteFilters(route: RouteFilterData, filters: RouteFilterState): boolean {
  if (filters.regions.size > 0 && !filters.regions.has(route.region)) return false;
  if (filters.terrains.size > 0 && !route.terrainTags.some((tag) => filters.terrains.has(tag))) return false;
  return true;
}

export function isFilterActive(filters: RouteFilterState): boolean {
  return filters.regions.size > 0 || filters.terrains.size > 0;
}
