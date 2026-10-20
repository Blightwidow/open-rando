export interface ServiceWindow {
  first_departure_minutes: number;
  last_departure_minutes: number;
  departure_count: number;
  /** Calendar date the pipeline counted these departures on. */
  sample_date?: string | null;
}

export interface RailService {
  weekday: ServiceWindow | null;
  saturday: ServiceWindow | null;
  sunday: ServiceWindow | null;
}

export type DayType = keyof RailService;

export const DAY_TYPES: DayType[] = ['weekday', 'saturday', 'sunday'];

const MINUTES_PER_DAY = 24 * 60;

export interface RailServiceLabels {
  weekday: string;
  saturday: string;
  sunday: string;
  noService: string;
  departures: string;
}

/**
 * Clock time of a GTFS departure. Times past midnight are stored beyond 24h
 * (a 25:10 departure belongs to the previous service day), so they wrap.
 */
export function formatDepartureTime(minutes: number): string {
  const wrapped = ((minutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const hours = Math.floor(wrapped / 60);
  const remainingMinutes = wrapped % 60;
  return `${String(hours).padStart(2, '0')}:${String(remainingMinutes).padStart(2, '0')}`;
}

export interface RailServiceRow {
  dayType: DayType;
  label: string;
  /** null when the feeds report no departure on that kind of day. */
  window: ServiceWindow | null;
  text: string;
}

/** One row per kind of day: first train, last train, and how many run. */
export function buildRailServiceRows(
  railService: RailService | null | undefined,
  labels: RailServiceLabels,
): RailServiceRow[] {
  if (!railService) return [];

  return DAY_TYPES.map((dayType) => {
    const window = railService[dayType] ?? null;
    const text = window
      ? `${formatDepartureTime(window.first_departure_minutes)} → ${formatDepartureTime(window.last_departure_minutes)} · ${labels.departures.replace('{count}', String(window.departure_count))}`
      : labels.noService;
    return { dayType, label: labels[dayType], window, text };
  });
}
