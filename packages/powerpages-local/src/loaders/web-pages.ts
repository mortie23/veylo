import * as fs from 'node:fs';
import * as path from 'node:path';
import type { WebPageRecord } from '../types.js';
import { readTextFile, readYaml } from './yaml-utils.js';

interface WebPageYaml {
  adx_name: string;
  adx_webpageid: string;
  adx_partialurl: string;
  adx_pagetemplateid: string;
  adx_parentpageid?: string;
  adx_isroot?: boolean;
  adx_title?: string;
  adx_publishingstateid?: string;
}

/**
 * Load all web pages from web-pages/.
 * Returns a Map keyed by adx_webpageid (GUID).
 *
 * Each web page directory contains:
 *   <Name>.webpage.yml                          — root page metadata
 *   <Name>.webpage.copy.html                    — root page body (fallback)
 *   content-pages/<Name>.<locale>.webpage.yml   — localized metadata
 *   content-pages/<Name>.<locale>.webpage.copy.html — localized body
 */
export function loadWebPages(sitePath: string): Map<string, WebPageRecord> {
  const pagesDir = path.join(sitePath, 'web-pages');
  if (!fs.existsSync(pagesDir)) return new Map();

  const pages = new Map<string, WebPageRecord>();
  const dirs = fs.readdirSync(pagesDir, { withFileTypes: true });

  for (const dir of dirs) {
    if (!dir.isDirectory()) continue;

    const dirPath = path.join(pagesDir, dir.name);
    const files = fs.readdirSync(dirPath);

    // Read root-level webpage.yml
    const ymlFile = files.find((f) => f.endsWith('.webpage.yml'));
    if (!ymlFile) continue;

    const data = readYaml<WebPageYaml>(path.join(dirPath, ymlFile));
    if (!data) continue;

    pages.set(data.adx_webpageid, {
      name: data.adx_name,
      id: data.adx_webpageid,
      partialUrl: data.adx_partialurl,
      pageTemplateId: data.adx_pagetemplateid,
      parentPageId: data.adx_parentpageid ?? '',
      isRoot: data.adx_isroot ?? false,
      dirPath,
      publishingStateId: data.adx_publishingstateid ?? '',
    });
  }

  return pages;
}

/**
 * Build a URL→WebPageRecord route table from loaded pages.
 *
 * For root pages (isRoot=true), the URL is '/'.
 * For child pages, the URL is the partialUrl (which in this site is
 * already an absolute path like '/admin').
 */
export function buildRouteTable(
  pages: Map<string, WebPageRecord>,
): Map<string, WebPageRecord> {
  const routes = new Map<string, WebPageRecord>();

  for (const page of pages.values()) {
    // Normalise URL: ensure leading slash, no trailing slash (except root)
    let url = page.partialUrl;
    if (!url.startsWith('/')) url = '/' + url;
    if (url !== '/' && url.endsWith('/')) url = url.slice(0, -1);

    routes.set(url, page);
  }

  return routes;
}

/**
 * Read the content files (copy, CSS, JS) for a specific page,
 * preferring the locale-specific content-pages/ version.
 */
export function readPageContent(
  page: WebPageRecord,
  locale: string = 'en-US',
): {
  copy: string;
  customCss: string;
  customJs: string;
  summary: string;
  title: string;
} {
  const contentDir = path.join(page.dirPath, 'content-pages');
  const baseName = page.name;

  // Try locale-specific files first (content-pages/), fall back to root-level
  const localePrefix = `${baseName}.${locale}.webpage`;
  const rootPrefix = `${baseName}.webpage`;

  function resolve(suffix: string): string {
    if (fs.existsSync(contentDir)) {
      const localePath = path.join(contentDir, `${localePrefix}.${suffix}`);
      if (fs.existsSync(localePath)) return readTextFile(localePath);
    }
    const rootPath = path.join(page.dirPath, `${rootPrefix}.${suffix}`);
    return readTextFile(rootPath);
  }

  return {
    copy: resolve('copy.html'),
    customCss: resolve('custom_css.css'),
    customJs: resolve('custom_javascript.js'),
    summary: resolve('summary.html'),
    title: page.name,
  };
}
