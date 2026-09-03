import * as fs from 'node:fs';
import * as path from 'node:path';
import type { Weblink, WeblinkSet, WebPageRecord } from '../types.js';
import { readYaml } from './yaml-utils.js';

interface WeblinkYaml {
  adx_name: string;
  adx_pageid?: string;
  adx_displayorder: number;
  adx_openinnewwindow?: boolean;
  adx_weblinkid: string;
  adx_url?: string;
}

interface WeblinkSetYaml {
  adx_name: string;
  adx_weblinksetid: string;
}

/**
 * Load all weblink sets from weblink-sets/.
 *
 * Each set directory contains:
 *   <Name>.<locale>.weblinkset.yml          — set metadata (adx_name)
 *   <Name>.<locale>.weblinkset.weblink.yml  — array of link objects
 *
 * Links reference pages by adx_pageid which must be resolved to URLs
 * using the pages map.
 */
export function loadWeblinkSets(
  sitePath: string,
  pages: Map<string, WebPageRecord>,
  locale: string = 'en-US',
): Record<string, WeblinkSet> {
  const setsDir = path.join(sitePath, 'weblink-sets');
  if (!fs.existsSync(setsDir)) return {};

  // Build a page-ID-to-URL lookup for resolving link targets
  const pageUrlMap = new Map<string, string>();
  for (const page of pages.values()) {
    let url = page.partialUrl;
    if (!url.startsWith('/')) url = '/' + url;
    pageUrlMap.set(page.id, url);
  }

  const result: Record<string, WeblinkSet> = {};
  const dirs = fs.readdirSync(setsDir, { withFileTypes: true });

  for (const dir of dirs) {
    if (!dir.isDirectory()) continue;

    const dirPath = path.join(setsDir, dir.name);
    const files = fs.readdirSync(dirPath);

    // Read the set metadata
    const setYmlFile = files.find(
      (f) => f.endsWith(`.${locale}.weblinkset.yml`) && !f.includes('.weblink.'),
    );
    if (!setYmlFile) continue;

    const setData = readYaml<WeblinkSetYaml>(path.join(dirPath, setYmlFile));
    if (!setData) continue;

    // Read the weblinks array
    const linkYmlFile = files.find((f) =>
      f.endsWith(`.${locale}.weblinkset.weblink.yml`),
    );
    const links = linkYmlFile
      ? (readYaml<WeblinkYaml[]>(path.join(dirPath, linkYmlFile)) ?? [])
      : [];

    const weblinks: Weblink[] = links
      .sort((a, b) => a.adx_displayorder - b.adx_displayorder)
      .map((link) => ({
        name: link.adx_name,
        url: link.adx_url ?? pageUrlMap.get(link.adx_pageid ?? '') ?? '#',
        displayOrder: link.adx_displayorder,
        openInNewWindow: link.adx_openinnewwindow ?? false,
        pageId: link.adx_pageid,
      }));

    result[setData.adx_name] = {
      name: setData.adx_name,
      weblinks,
    };
  }

  return result;
}
