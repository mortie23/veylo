import * as http from 'node:http';
import * as fs from 'node:fs';
import * as path from 'node:path';
import pc from 'picocolors';
import type { Liquid } from 'liquidjs';
import { createServer as createViteServer, type ViteDevServer } from 'vite';
import chokidar from 'chokidar';
import type { ResolvedConfig } from '../config.js';
import type { SiteData, UserRole } from '../types.js';
import {
  loadSiteSettings,
  loadContentSnippets,
  loadWebsite,
  loadWebTemplates,
  buildTemplateNameIndex,
  loadPageTemplates,
  loadWebPages,
  buildRouteTable,
  loadWeblinkSets,
  loadSiteMarkers,
  loadWebRoles,
} from '../loaders/index.js';
import { createLiquidEngine } from '../engine/liquid-engine.js';
import { buildScope } from '../context/scope-builder.js';
import { renderPage } from './html-shell.js';

// ---------------------------------------------------------------------------
// MIME type lookup for static file serving
// ---------------------------------------------------------------------------

const MIME_TYPES: Record<string, string> = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
};

// ---------------------------------------------------------------------------
// Dev Server
// ---------------------------------------------------------------------------

export interface DevServer {
  start(): Promise<void>;
  stop(): Promise<void>;
}

export function createDevServer(config: ResolvedConfig): DevServer {
  let httpServer: http.Server | null = null;
  let vite: ViteDevServer | null = null;
  let watcher: any | null = null; // using any to bypass chokidar type issue
  let siteData: SiteData;
  let engine: Liquid;
  let currentRole: UserRole = config.defaultRole;

  /** Load (or reload) all site data from disk. */
  function loadAllSiteData(): SiteData {
    const { sitePath, locale } = config;

    const website = loadWebsite(sitePath);
    const settings = loadSiteSettings(sitePath);
    const webTemplates = loadWebTemplates(sitePath);
    const pageTemplates = loadPageTemplates(sitePath);
    const pages = loadWebPages(sitePath);
    const routeTable = buildRouteTable(pages);
    const snippets = loadContentSnippets(sitePath, locale);
    const weblinks = loadWeblinkSets(sitePath, pages, locale);
    const siteMarkers = loadSiteMarkers(sitePath, pages);
    const webRoles = loadWebRoles(sitePath);

    return {
      settings,
      snippets,
      weblinks,
      website,
      webTemplates,
      pageTemplates,
      pages,
      routeTable,
      siteMarkers,
      webRoles,
    };
  }

  /** Try to serve a static file from web-files/. Returns true if served. */
  function tryServeStaticFile(
    req: http.IncomingMessage,
    res: http.ServerResponse,
  ): boolean {
    const urlPath = req.url?.split('?')[0] ?? '/';
    const fileName = urlPath.startsWith('/') ? urlPath.slice(1) : urlPath;
    const filePath = path.join(config.sitePath, 'web-files', fileName);

    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      return false;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] ?? 'application/octet-stream';

    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath).pipe(res);
    return true;
  }

  /** Handle an incoming HTTP request. */
  async function handleRequest(
    req: http.IncomingMessage,
    res: http.ServerResponse,
  ): Promise<void> {
    const urlPath = (req.url?.split('?')[0] ?? '/').replace(/\/+$/, '') || '/';
    const method = req.method ?? 'GET';

    // --- Static files ---
    if (tryServeStaticFile(req, res)) return;

    // --- Favicon fallback ---
    if (urlPath === '/favicon.ico') {
      res.writeHead(204);
      res.end();
      return;
    }

    // --- Role switcher API (for future toolbar) ---
    if (urlPath === '/__powerpages/role' && method === 'POST') {
      const body = await readBody(req);
      try {
        const { role } = JSON.parse(body);
        if (['anonymous', 'authenticated', 'admin'].includes(role)) {
          currentRole = role as UserRole;
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ role: currentRole }));
          return;
        }
      } catch { /* fall through */ }
      res.writeHead(400);
      res.end('Invalid role');
      return;
    }

    // --- Deploy API ---
    if (urlPath === '/__powerpages/deploy' && method === 'POST') {
      import('node:child_process').then(({ exec }) => {
        exec('npm run deploy', { cwd: path.join(config.sitePath, '..') }, (error, stdout, stderr) => {
          if (error) {
            console.error(`Deploy error: ${error.message}`);
          }
        });
      });
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true, message: 'Deployment started' }));
      return;
    }

    // --- Reload site data API ---
    if (urlPath === '/__powerpages/reload' && method === 'POST') {
      siteData = loadAllSiteData();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true }));
      return;
    }

    // --- Mock Web API Stubbing ---
    if (urlPath.startsWith('/_api/')) {
      const entity = urlPath.replace('/_api/', '').split('?')[0].replace(/\/$/, '');
      let mockData: any = { value: [] };
      if (entity === 'contacts') {
        mockData = { value: [{ contactid: 'mock-1', fullname: 'Mock Contact', emailaddress1: 'mock@example.com', _parentcustomerid_value: 'mock-1' }] };
      } else if (entity === 'accounts') {
        mockData = { value: [{ accountid: 'mock-1', name: 'Mock Account' }] };
      } else if (entity === 'vey_filesubmissions') {
        mockData = {
          value: [
            {
              vey_filesubmissionid: 'sub-001',
              vey_name: 'Q3-2026-Admissions-Summary',
              vey_submissionreference: 'Q3-2026-Admissions-Summary',
              vey_filename: 'admissions_q3_2026.csv',
              vey_filesizebytes: 1458290,
              vey_filehash: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
              vey_schemaversion: 'v1.0',
              vey_submissionstatus: 948740002, // Processed
              vey_reportingperiodstart: '2026-07-01T00:00:00Z',
              vey_reportingperiodend: '2026-09-30T00:00:00Z',
              createdon: '2026-09-08T10:30:00Z',
              _vey_submittedby_value: 'mock-1',
              _vey_organization_value: 'mock-1',
              vey_storageuri: 'https://stveyportaldev01.blob.core.windows.net/submissions/raw/sub-001/admissions_q3_2026.csv'
            },
            {
              vey_filesubmissionid: 'sub-002',
              vey_name: 'Monthly-Discharge-Aug2026',
              vey_submissionreference: 'Monthly-Discharge-Aug2026',
              vey_filename: 'discharges_august.csv',
              vey_filesizebytes: 3847291,
              vey_filehash: 'b2c3d4e5f6a10718293a4b5c6d7e8f90123456789abcdef0123456789abcdef1',
              vey_schemaversion: 'v2.1',
              vey_submissionstatus: 948740003, // Partial Success
              vey_reportingperiodstart: '2026-08-01T00:00:00Z',
              vey_reportingperiodend: '2026-08-31T00:00:00Z',
              createdon: '2026-09-09T14:15:00Z',
              _vey_submittedby_value: 'mock-1',
              _vey_organization_value: 'mock-1',
              vey_storageuri: 'https://stveyportaldev01.blob.core.windows.net/submissions/raw/sub-002/discharges_august.csv'
            }
          ]
        };
      } else if (entity === 'vey_fileingestionerrors') {
        mockData = {
          value: [
            {
              vey_fileingestionerrorid: 'err-001',
              vey_rownumber: 142,
              vey_errorcode: 'ERR_INVALID_DATE_FORMAT',
              vey_errormessage: "Value '31/02/2026' in column 'AdmissionDate' is not a valid ISO-8601 date.",
              vey_errorreference: 'SCHEMA_FIELD_VALIDATION',
              vey_rawpayload: '142,P104928,31/02/2026,DISCHARGED,DEPT_A',
              createdon: '2026-09-09T14:16:00Z',
              _vey_filesubmission_value: 'sub-002'
            },
            {
              vey_fileingestionerrorid: 'err-002',
              vey_rownumber: 389,
              vey_errorcode: 'ERR_REQUIRED_FIELD_MISSING',
              vey_errormessage: "Mandatory column 'PatientIdentifier' was null or empty.",
              vey_errorreference: 'SCHEMA_NOT_NULL',
              vey_rawpayload: '389,,2026-08-15,ADMITTED,DEPT_C',
              createdon: '2026-09-09T14:16:00Z',
              _vey_filesubmission_value: 'sub-002'
            }
          ]
        };
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(mockData));
      return;
    }

    // --- Page routing ---
    let page = siteData.routeTable.get(urlPath);
    if (!page) {
      for (const [route, p] of siteData.routeTable.entries()) {
        if (route.toLowerCase() === urlPath.toLowerCase()) {
          page = p;
          break;
        }
      }
    }
    if (!page && urlPath.toLowerCase().startsWith('/account/login/')) {
      const subPath = '/' + urlPath.slice('/account/login/'.length);
      page = siteData.routeTable.get(subPath);
      if (!page) {
        for (const [route, p] of siteData.routeTable.entries()) {
          if (route.toLowerCase() === subPath.toLowerCase()) {
            page = p;
            break;
          }
        }
      }
    }
    if (!page) {
      // Don't render full 404 HTML page for missing assets, well-known requests, or non-HTML clients
      const hasExt = path.extname(urlPath).length > 0;
      const isWellKnown = urlPath.startsWith('/.well-known/');
      const acceptsNonHtml = req.headers.accept && !req.headers.accept.includes('text/html') && !req.headers.accept.includes('*/*');

      if (hasExt || isWellKnown || acceptsNonHtml) {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end(`404 Not Found: ${urlPath}`);
        return;
      }

      // Try the 404 page
      const notFoundMarker = siteData.siteMarkers['Page Not Found'];
      const notFoundPage = notFoundMarker
        ? siteData.pages.get(notFoundMarker.id)
        : undefined;

      if (notFoundPage) {
        const scope = buildScope(siteData, notFoundPage, config.locale, currentRole, req);
        let html = await renderPage(engine, siteData, notFoundPage, scope, config.locale, config.sitePath, config.mockTemplatesPath);
        if (vite) {
          html = await vite.transformIndexHtml('/404', html);
        }
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
      } else {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end(`404 Not Found: ${urlPath}`);
      }
      return;
    }

    // Render the matched page
    try {
      const scope = buildScope(siteData, page, config.locale, currentRole, req);
      let html = await renderPage(engine, siteData, page, scope, config.locale, config.sitePath, config.mockTemplatesPath);
      if (vite) {
        html = await vite.transformIndexHtml(req.url || '/', html);
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
    } catch (err) {
      console.error(pc.red(`  ✗ Error rendering ${urlPath}:`), err);
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end(`500 Internal Server Error: ${err}`);
    }
  }

  return {
    async start() {
      // Load all site data
      console.log(pc.cyan('  Loading site data...'));
      siteData = loadAllSiteData();

      // Log summary
      console.log(pc.dim(`    Settings:  ${Object.keys(siteData.settings).length} entries`));
      console.log(pc.dim(`    Snippets:  ${Object.keys(siteData.snippets).length} entries`));
      console.log(pc.dim(`    Templates: ${siteData.webTemplates.size} web templates`));
      console.log(pc.dim(`    Pages:     ${siteData.pages.size} pages`));
      console.log(pc.dim(`    Routes:    ${siteData.routeTable.size} routes`));

      // Create Liquid engine
      const templateNameIndex = buildTemplateNameIndex(siteData.webTemplates);
      engine = createLiquidEngine(templateNameIndex);

      // Create HTTP server first
      httpServer = http.createServer();

      // Create Vite server
      vite = await createViteServer({
        server: { 
          middlewareMode: true,
          hmr: { server: httpServer }
        },
        appType: 'custom',
        root: config.sitePath,
        publicDir: 'web-files',
      });

      // Add request handler to httpServer
      httpServer.on('request', (req, res) => {
        vite!.middlewares(req, res, () => {
          handleRequest(req, res).catch((err) => {
            console.error(pc.red('  Unhandled error:'), err);
            if (!res.headersSent) {
              res.writeHead(500);
              res.end('Internal Server Error');
            }
          });
        });
      });

      // Setup watcher
      watcher = chokidar.watch(config.sitePath, {
        ignored: ['**/node_modules/**', '**/.git/**', '**/.vite/**'],
        ignoreInitial: true,
      });

      watcher.on('all', (event: string, filePath: string) => {
        console.log(pc.yellow(`  [Watcher] ${event}: ${filePath}`));
        try {
          siteData = loadAllSiteData();
          const newTemplateIndex = buildTemplateNameIndex(siteData.webTemplates);
          engine = createLiquidEngine(newTemplateIndex);
          vite?.ws.send({ type: 'full-reload' });
        } catch (err) {
          console.error(pc.red('  Error reloading site data:'), err);
        }
      });

      // Start listening
      return new Promise<void>((resolve) => {
        httpServer!.listen(config.port, () => {
          console.log('');
          console.log(
            `  ${pc.green('⚡')} ${pc.bold('powerpages-local')} dev server running at:`,
          );
          console.log(
            `     ${pc.cyan(`http://localhost:${config.port}/`)}`,
          );
          console.log('');
          console.log(pc.dim(`  Site: ${config.sitePath}`));
          console.log(pc.dim(`  Role: ${currentRole}`));
          console.log('');
          resolve();
        });
      });
    },

    async stop() {
      if (watcher) await watcher.close();
      if (vite) await vite.close();
      return new Promise<void>((resolve) => {
        if (httpServer) {
          httpServer.close(() => resolve());
        } else {
          resolve();
        }
      });
    },
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}
