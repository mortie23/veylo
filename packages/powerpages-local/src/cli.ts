import pc from 'picocolors';
import { loadConfigFile, resolveConfig } from './config.js';
import { createDevServer } from './server/dev-server.js';
import type { PowerPagesLocalConfig, ResolvedConfig } from './config.js';
import type { UserRole } from './types.js';

// ---------------------------------------------------------------------------
// CLI argument parsing (minimal — no external dependency)
// ---------------------------------------------------------------------------

function parseArgs(argv: string[]): Partial<PowerPagesLocalConfig> {
  const args: Partial<PowerPagesLocalConfig> = {};

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    const next = argv[i + 1];

    if ((arg === '--site' || arg === '-s') && next) {
      args.sitePath = next;
      i++;
    } else if ((arg === '--port' || arg === '-p') && next) {
      args.port = parseInt(next, 10);
      i++;
    } else if ((arg === '--role' || arg === '-r') && next) {
      args.defaultRole = next as UserRole;
      i++;
    } else if ((arg === '--locale' || arg === '-l') && next) {
      args.locale = next;
      i++;
    } else if (arg === '--help' || arg === '-h') {
      printHelp();
      process.exit(0);
    } else if (arg === '--version' || arg === '-v') {
      console.log('0.1.0');
      process.exit(0);
    }
  }

  return args;
}

function printHelp(): void {
  console.log(`
${pc.bold('powerpages-local')} — Local development server for Power Pages

${pc.dim('Usage:')}
  powerpages-local [options]

${pc.dim('Options:')}
  -s, --site <path>    Path to the PAC CLI-exported site directory
  -p, --port <number>  Dev server port (default: 3000)
  -r, --role <role>    Initial user role: anonymous, authenticated, admin
  -l, --locale <code>  Content locale (default: en-US)
  -h, --help           Show this help message
  -v, --version        Show version

${pc.dim('Config file:')}
  Auto-discovered from cwd upwards: powerpages-local.config.js
`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('');
  console.log(`  ${pc.bold(pc.cyan('powerpages-local'))} ${pc.dim('v0.1.0')}`);
  console.log('');

  // Parse CLI args
  const cliArgs = parseArgs(process.argv);

  // Load config file (if present)
  const fileConfig = await loadConfigFile();

  // Merge: CLI args override config file
  const mergedConfig: PowerPagesLocalConfig = {
    ...(fileConfig ?? {}),
    ...cliArgs,
  } as PowerPagesLocalConfig;

  if (!mergedConfig.sitePath) {
    console.error(
      pc.red('  ✗ No site path specified.'),
      'Use --site <path> or create a powerpages-local.config.js',
    );
    process.exit(1);
  }

  // Resolve and validate
  let resolved: ResolvedConfig;
  try {
    resolved = resolveConfig(mergedConfig);
  } catch (err) {
    console.error(pc.red(`  ✗ ${(err as Error).message}`));
    process.exit(1);
  }

  // Create and start the server
  const server = createDevServer(resolved);

  // Graceful shutdown
  const shutdown = async () => {
    console.log(pc.dim('\n  Shutting down...'));
    await server.stop();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  await server.start();
}

main().catch((err) => {
  console.error(pc.red('Fatal error:'), err);
  process.exit(1);
});
