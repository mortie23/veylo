import * as path from 'node:path';
import type { WebsiteConfig } from '../types.js';
import { readYaml } from './yaml-utils.js';

interface WebsiteYaml {
  adx_name: string;
  adx_websiteid: string;
  adx_headerwebtemplateid: string;
  adx_footerwebtemplateid: string;
  adx_defaultlanguage: string;
  adx_website_language: number;
}

/**
 * Load the website.yml root site record.
 */
export function loadWebsite(sitePath: string): WebsiteConfig {
  const filePath = path.join(sitePath, 'website.yml');
  const data = readYaml<WebsiteYaml>(filePath);

  if (!data) {
    throw new Error(`website.yml not found at ${filePath}`);
  }

  return {
    name: data.adx_name,
    id: data.adx_websiteid,
    headerWebTemplateId: data.adx_headerwebtemplateid,
    footerWebTemplateId: data.adx_footerwebtemplateid,
    defaultLanguageId: data.adx_defaultlanguage,
    languageCode: data.adx_website_language,
  };
}
