import * as fs from 'node:fs';
import * as path from 'node:path';
import { createRequire } from 'node:module';
import type { UserRole } from './types.js';

// ---------------------------------------------------------------------------
// Configuration schema
// ---------------------------------------------------------------------------

export interface PowerPagesLocalConfig {
  /** Path to the PAC CLI-exported site directory (contains website.yml, web-pages/, etc.) */
  sitePath: string;
  /** Locale for content page resolution (default: 'en-US') */
  locale?: string;
  /** Dev server port (default: 3000) */
  port?: number;
  /** Directory containing mock JSON data for /_api/ stubs */
  mockDataPath?: string;
  /** Directory containing mock HTML templates for built-in platform pages */
  mockTemplatesPath?: string;
  /** Shell command to execute when the Deploy button is pressed */
  deployCommand?: string;
  /** Initial user role preset (default: 'anonymous') */
  defaultRole?: UserRole;
}

export interface ResolvedConfig {
  sitePath: string;
  locale: string;
  port: number;
  mockDataPath: string | null;
  mockTemplatesPath: string | null;
  deployCommand: string | null;
  defaultRole: UserRole;
}

const DEFAULTS: Omit<ResolvedConfig, 'sitePath'> = {
  locale: 'en-US',
  port: 3000,
  mockDataPath: null,
  mockTemplatesPath: null,
  deployCommand: null,
  defaultRole: 'anonymous',
};

// ---------------------------------------------------------------------------
// Config resolution
// ---------------------------------------------------------------------------

/**
 * Resolve a partial user config into a fully-populated ResolvedConfig.
 * Resolves `sitePath` to an absolute path relative to `cwd`.
 */
export function resolveConfig(
  userConfig: PowerPagesLocalConfig,
  cwd: string = process.cwd(),
): ResolvedConfig {
  const sitePath = path.resolve(cwd, userConfig.sitePath);

  if (!fs.existsSync(sitePath)) {
    throw new Error(`Site path does not exist: ${sitePath}`);
  }
  if (!fs.existsSync(path.join(sitePath, 'website.yml'))) {
    throw new Error(
      `Site path does not appear to be a Power Pages site directory (missing website.yml): ${sitePath}`,
    );
  }

  return {
    ...DEFAULTS,
    ...userConfig,
    sitePath,
    mockDataPath: userConfig.mockDataPath
      ? path.resolve(cwd, userConfig.mockDataPath)
      : null,
    mockTemplatesPath: userConfig.mockTemplatesPath
      ? path.resolve(cwd, userConfig.mockTemplatesPath)
      : null,
  };
}

// ---------------------------------------------------------------------------
// Config file discovery
// ---------------------------------------------------------------------------

const CONFIG_FILENAMES = [
  'powerpages-local.config.cjs',
  'powerpages-local.config.js',
  'powerpages-local.config.mjs',
];

/**
 * Search for a config file starting from `cwd` and walking up.
 * Returns the resolved config, or null if no config file is found.
 */
export async function loadConfigFile(
  cwd: string = process.cwd(),
): Promise<PowerPagesLocalConfig | null> {
  let dir = cwd;
  while (true) {
    for (const filename of CONFIG_FILENAMES) {
      const candidate = path.join(dir, filename);
      if (fs.existsSync(candidate)) {
        if (filename.endsWith('.cjs')) {
          // Use require() for CommonJS config files to avoid ESM cycle issues
          const require = createRequire(import.meta.url);
          return require(candidate) as PowerPagesLocalConfig;
        }
        // Use dynamic import for ESM config files
        const fileUrl = new URL(`file://${candidate.replace(/\\/g, '/')}`);
        const mod = await import(fileUrl.href);
        return (mod.default ?? mod) as PowerPagesLocalConfig;
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) break; // reached filesystem root
    dir = parent;
  }
  return null;
}
