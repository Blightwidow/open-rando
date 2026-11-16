import { describe, expect, test } from 'bun:test';
import { OVERLAY_SOURCE_LAYERS, defaultVisibleGroups, getOverlayGroups } from './overlay';

const allLayers = (isDark: boolean) => getOverlayGroups(isDark).flatMap((group) => group.layers);

describe('overlay groups', () => {
  test('every layer reads a source layer the tiles carry', () => {
    const known = new Set<string>(OVERLAY_SOURCE_LAYERS);
    const unknown = allLayers(false).filter((layer) => !known.has((layer as { 'source-layer': string })['source-layer']));
    expect(unknown.map((layer) => layer.id)).toEqual([]);
  });

  test('layer ids are unique', () => {
    const ids = allLayers(false).map((layer) => layer.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test('light and dark themes define the same layers', () => {
    expect(allLayers(true).map((layer) => layer.id)).toEqual(allLayers(false).map((layer) => layer.id));
  });

  test('streams are not drawn', () => {
    expect(allLayers(false).some((layer) => (layer as { 'source-layer': string })['source-layer'] === 'stream')).toBe(false);
  });

  test('dense layers start hidden', () => {
    const visible = defaultVisibleGroups();
    expect([visible.has('guidepost'), visible.has('power')]).toEqual([false, false]);
  });

  test('peaks and water start visible', () => {
    const visible = defaultVisibleGroups();
    expect([visible.has('peak'), visible.has('water')]).toEqual([true, true]);
  });
});
