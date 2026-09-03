import * as fs from 'node:fs';
import * as path from 'node:path';
import type { PageTemplateRecord } from '../types.js';
import { readYaml } from './yaml-utils.js';

interface PageTemplateYaml {
  adx_name: string;
  adx_pagetemplateid: string;
  adx_webtemplateid: string;
  adx_usewebsiteheaderandfooter: boolean;
  adx_type?: number;
}

/**
 * Load all page templates from page-templates/.
 * Returns a Map keyed by adx_pagetemplateid (GUID).
 *
 * Page templates map a page to its rendering web template and control
 * whether the site header/footer are included.
 */
export function loadPageTemplates(
  sitePath: string,
): Map<string, PageTemplateRecord> {
  const dir = path.join(sitePath, 'page-templates');
  if (!fs.existsSync(dir)) return new Map();

  const templates = new Map<string, PageTemplateRecord>();
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.pagetemplate.yml'));

  for (const file of files) {
    const data = readYaml<PageTemplateYaml>(path.join(dir, file));
    if (!data) continue;

    templates.set(data.adx_pagetemplateid, {
      name: data.adx_name,
      id: data.adx_pagetemplateid,
      webTemplateId: data.adx_webtemplateid,
      useHeaderAndFooter: data.adx_usewebsiteheaderandfooter ?? true,
    });
  }

  return templates;
}
