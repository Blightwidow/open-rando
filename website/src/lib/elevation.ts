export interface SlopeThreshold {
  minSlope: number;
  color: string;
}

export const DEFAULT_SLOPE_THRESHOLDS: SlopeThreshold[] = [
  { minSlope: 15, color: 'var(--slope-extreme, #dc2626)' },
  { minSlope: 10, color: 'var(--slope-steep, #ea580c)' },
  { minSlope: 5, color: 'var(--slope-moderate, #eab308)' },
  { minSlope: 0, color: 'var(--slope-flat, #22c55e)' },
];

export function getSlopeColor(slopePercent: number, thresholds: SlopeThreshold[] = DEFAULT_SLOPE_THRESHOLDS): string {
  const absoluteSlope = Math.abs(slopePercent);
  for (const threshold of thresholds) {
    if (absoluteSlope >= threshold.minSlope) return threshold.color;
  }
  return thresholds[thresholds.length - 1].color;
}

export function computeSlopePercent(distance1Km: number, elevation1M: number, distance2Km: number, elevation2M: number): number {
  const horizontalDistanceMeters = (distance2Km - distance1Km) * 1000;
  const verticalDelta = elevation2M - elevation1M;
  if (horizontalDistanceMeters <= 0) return 0;
  return (verticalDelta / horizontalDistanceMeters) * 100;
}

export function formatTime(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (hours > 0 && mins > 0) return `${hours}h${String(mins).padStart(2, '0')}`;
  if (hours > 0) return `${hours}h`;
  return `${mins}min`;
}
