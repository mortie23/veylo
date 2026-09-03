export { createDevServer } from './server/dev-server.js';
export type { DevServer } from './server/dev-server.js';
export { resolveConfig, loadConfigFile } from './config.js';
export type { PowerPagesLocalConfig, ResolvedConfig } from './config.js';
export type * from './types.js';

/**
 * Convenience function to create and start a dev server.
 *
 * @example
 * ```ts
 * import { createServer } from 'powerpages-local';
 * const server = await createServer({ sitePath: './src/orgfile-manager' });
 * await server.start();
 * ```
 */
export async function createServer(
  config: import('./config.js').PowerPagesLocalConfig,
) {
  const { resolveConfig } = await import('./config.js');
  const { createDevServer } = await import('./server/dev-server.js');
  const resolved = resolveConfig(config);
  return createDevServer(resolved);
}
