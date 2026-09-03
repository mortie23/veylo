import * as fs from 'node:fs';
import * as path from 'node:path';
import type { WebTemplateRecord } from '../types.js';
import { readYaml } from './yaml-utils.js';

interface WebTemplateYaml {
  adx_name: string;
  adx_webtemplateid: string;
  adx_source?: string;
}

/**
 * Load all web templates from web-templates/.
 * Returns a Map keyed by GUID (adx_webtemplateid).
 *
 * Each web template directory contains:
 *   <Name>.webtemplate.yml        — metadata (adx_name, adx_webtemplateid)
 *   <Name>.webtemplate.source.html — Liquid template source
 */
export function loadWebTemplates(
  sitePath: string,
): Map<string, WebTemplateRecord> {
  const templatesDir = path.join(sitePath, 'web-templates');
  if (!fs.existsSync(templatesDir)) return new Map();

  const templates = new Map<string, WebTemplateRecord>();
  const dirs = fs.readdirSync(templatesDir, { withFileTypes: true });

  for (const dir of dirs) {
    if (!dir.isDirectory()) continue;

    const dirPath = path.join(templatesDir, dir.name);
    const files = fs.readdirSync(dirPath);

    const ymlFile = files.find((f) => f.endsWith('.webtemplate.yml'));
    const sourceFile = files.find((f) =>
      f.endsWith('.webtemplate.source.html'),
    );

    if (!ymlFile || !sourceFile) continue;

    const ymlData = readYaml<WebTemplateYaml>(path.join(dirPath, ymlFile));
    if (!ymlData) continue;

    templates.set(ymlData.adx_webtemplateid, {
      name: ymlData.adx_name,
      id: ymlData.adx_webtemplateid,
      sourcePath: path.join(dirPath, sourceFile),
    });
  }

  return templates;
}

/**
 * Build a name-based lookup from the GUID-keyed template map.
 * Keys are the display name as-is (e.g. "Header", "Page Copy").
 */
export function buildTemplateNameIndex(
  templates: Map<string, WebTemplateRecord>,
): Map<string, WebTemplateRecord> {
  const index = new Map<string, WebTemplateRecord>();
  for (const template of templates.values()) {
    index.set(template.name, template);
  }
  return index;
}
