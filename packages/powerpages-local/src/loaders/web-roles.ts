import * as path from 'node:path';
import type { WebRole } from '../types.js';
import { readYaml } from './yaml-utils.js';

interface WebRoleYaml {
  adx_name: string;
  adx_webroleid: string;
  adx_anonymoususersrole: boolean;
  adx_authenticatedusersrole: boolean;
}

/**
 * Load web roles from webrole.yml.
 */
export function loadWebRoles(sitePath: string): WebRole[] {
  const filePath = path.join(sitePath, 'webrole.yml');
  const entries = readYaml<WebRoleYaml[]>(filePath) ?? [];

  return entries.map((entry) => ({
    name: entry.adx_name,
    id: entry.adx_webroleid,
    isAnonymous: entry.adx_anonymoususersrole,
    isAuthenticated: entry.adx_authenticatedusersrole,
  }));
}
