import * as path from 'node:path';
import type { SiteMarker, WebPageRecord } from '../types.js';
import { readYaml } from './yaml-utils.js';

interface SiteMarkerYaml {
  adx_name: string;
  adx_pageid: string;
  adx_sitemarkerid: string;
}

/**
 * Load site markers from sitemarker.yml.
 * Resolves page GUIDs to URLs using the pages map.
 * Returns: sitemarkers['Home'] = { name, id, url, pageId }
 */
export function loadSiteMarkers(
  sitePath: string,
  pages: Map<string, WebPageRecord>,
): Record<string, SiteMarker> {
  const filePath = path.join(sitePath, 'sitemarker.yml');
  const entries = readYaml<SiteMarkerYaml[]>(filePath) ?? [];

  // Build page-ID-to-URL lookup
  const pageUrlMap = new Map<string, string>();
  for (const page of pages.values()) {
    let url = page.partialUrl;
    if (!url.startsWith('/')) url = '/' + url;
    pageUrlMap.set(page.id, url);
  }

  const markers: Record<string, SiteMarker> = {};

  for (const entry of entries) {
    markers[entry.adx_name] = {
      name: entry.adx_name,
      id: entry.adx_pageid,
      url: pageUrlMap.get(entry.adx_pageid) ?? '#',
      pageId: entry.adx_pageid,
    };
  }

  return markers;
}
