import * as path from 'node:path';
import type { SiteSettingEntry } from '../types.js';
import { readYaml } from './yaml-utils.js';

/**
 * Load site settings from sitesetting.yml.
 * Returns a flat key→value map: settings['Key/Path'] = 'value'
 */
export function loadSiteSettings(sitePath: string): Record<string, string> {
  const filePath = path.join(sitePath, 'sitesetting.yml');
  const entries = readYaml<SiteSettingEntry[]>(filePath) ?? [];
  const settings: Record<string, string> = {};

  for (const entry of entries) {
    if (entry.adx_name && entry.adx_value !== undefined) {
      settings[entry.adx_name] = String(entry.adx_value);
    }
  }

  return settings;
}
