import { describe, expect, test } from 'bun:test';
import { OVERLAY_SOURCE_LAYERS, defaultVisibleGroups, getOverlayGroups } from './overlay';
import { OVERLAY_ICON_NAMES, overlayIconImageId } from './overlay-icons';

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

  test('bridges, churches and toilets are drawn', () => {
    const sourceLayers = new Set(allLayers(false).map((layer) => (layer as { 'source-layer': string })['source-layer']));
    expect(['bridge', 'church', 'toilets', 'pass', 'waterfall', 'aerialway'].filter((name) => !sourceLayers.has(name))).toEqual([]);
  });

  test('every source layer the tiles carry is drawn, except streams', () => {
    const drawn = new Set(allLayers(false).map((layer) => (layer as { 'source-layer': string })['source-layer']));
    expect(OVERLAY_SOURCE_LAYERS.filter((name) => !drawn.has(name))).toEqual([]);
  });

  test('every icon a layer draws is one the icon module registers', () => {
    const registered = new Set(OVERLAY_ICON_NAMES.map(overlayIconImageId));
    const drawn = allLayers(false).flatMap((layer) => {
      const iconImage = (layer.layout as { 'icon-image'?: string } | undefined)?.['icon-image'];
      return iconImage ? [iconImage] : [];
    });
    expect(drawn.filter((imageId) => !registered.has(imageId))).toEqual([]);
  });

  test('every icon is drawn by at least one layer', () => {
    const drawn = new Set(allLayers(false).map((layer) => (layer.layout as { 'icon-image'?: string } | undefined)?.['icon-image']));
    expect(OVERLAY_ICON_NAMES.filter((name) => !drawn.has(overlayIconImageId(name)))).toEqual([]);
  });

  test('a group with an icon swatch names its icon', () => {
    const missing = getOverlayGroups(false).filter((group) => group.swatch === 'icon' && !group.icon);
    expect(missing.map((group) => group.key)).toEqual([]);
  });
});
