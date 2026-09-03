# `powerpages-local` — Local Development Server for Power Pages

> **Goal**: A distributable npm package that eliminates the 45-second "deploy → clear cache → refresh" feedback loop by providing a local, mock-driven Power Pages preview server with instant hot reload (<50 ms).

---

## 1. The Problem

In Power Pages, every change follows a painful loop:

1. Edit a template or CSS file locally in VS Code.
2. Run `.\deploy.ps1` (invokes `pac powerpages upload`).
3. Wait 5–15 s for PAC CLI to push files to Dataverse.
4. Clear the server cache via Design Studio or `/_services/about`.
5. Hard-refresh the browser (`Ctrl+F5`).
6. **Total: 30–60+ seconds per change.**

Microsoft provides **no** local preview tool. Their VS Code integration is strictly a cloud-sync mechanism; previewing always redirects to an Azure-hosted URL.

---

## 2. Package Strategy

### 2.1 Location & Lifecycle

| Stage | Location | Notes |
|:------|:---------|:------|
| **Now** | `packages/powerpages-local/` inside this repo | Monorepo sibling. Uses `../../src/orgfile-manager` as the test site via a `powerpages-local.config.js` at the repo root. |
| **Later** | Own git repo, published to npm as `powerpages-local` | Zero code changes required — the package never imports anything from the parent repo; the site path is always supplied by config or CLI arg. |

### 2.2 Design Constraints for Standalone Extraction

1. **No imports from the parent repo.** The package must only read the Power Pages site directory (the `orgfile-manager/` folder structure) via its public configuration.
2. **No hard-coded paths.** The site directory path is always provided by config file, CLI argument, or programmatic API.
3. **Self-contained `package.json`.** All dependencies are declared in `packages/powerpages-local/package.json`, not hoisted to a workspace root.
4. **Own README, LICENSE, CHANGELOG.** Ready for `npm publish` at any time.

---

## 3. Feasibility Analysis

Deconstructing the files in a PAC CLI-exported site directory reveals that Power Pages is a deterministic MVC template pipeline. Everything required to render ~95% of the portal UI is present as static files:

```
src/orgfile-manager/                   ← "Site Directory"
├── website.yml                        ← Root site record (header/footer template IDs)
├── sitesetting.yml                    ← Key/value site settings
├── sitemarker.yml                     ← Named page references (Home, Profile, Search, etc.)
├── webrole.yml                        ← Role definitions (Anonymous, Authenticated, Administrators)
├── webpagerule.yml                    ← Page access control rules
├── publishingstate.yml                ← Publishing states
├── websitelanguage.yml                ← Language config (LCID 1033 = English)
├── content-snippets/                  ← Reusable HTML/text snippets
│   └── <name>/<Name>.en-US.contentsnippet.value.html
├── page-templates/                    ← Map pagetemplateid → webtemplateid
│   └── <Name>.pagetemplate.yml
├── web-templates/                     ← Liquid source templates
│   └── <name>/<Name>.webtemplate.source.html + .yml
├── web-pages/                         ← Page content (two-tier: root + content-pages/)
│   └── <name>/
│       ├── <Name>.webpage.yml                           ← Root page metadata (partialurl, pagetemplateid)
│       ├── <Name>.webpage.copy.html                     ← Root page body
│       ├── <Name>.webpage.custom_css.css                ← Page-specific CSS
│       ├── <Name>.webpage.custom_javascript.js          ← Page-specific JS
│       └── content-pages/
│           ├── <Name>.en-US.webpage.yml                 ← Localized metadata
│           ├── <Name>.en-US.webpage.copy.html           ← Localized body
│           ├── <Name>.en-US.webpage.custom_css.css
│           └── <Name>.en-US.webpage.custom_javascript.js
├── web-files/                         ← Static assets (CSS, images) + .webfile.yml
├── weblink-sets/                      ← Navigation menus
│   └── <name>/
│       ├── <Name>.en-US.weblinkset.yml
│       └── <Name>.en-US.weblinkset.weblink.yml
└── .portalconfig/                     ← PAC CLI environment config (ignored by us)
```

---

## 4. Architecture

### 4.1 Package Directory Structure

```
packages/powerpages-local/
├── package.json
├── tsconfig.json
├── README.md
├── LICENSE
├── CHANGELOG.md
├── bin/
│   └── powerpages-local.js          # CLI entry point (#!/usr/bin/env node)
├── src/
│   ├── index.ts                     # Public API: createServer(config) → { start, stop }
│   ├── cli.ts                       # CLI argument parsing (uses src/index.ts)
│   ├── config.ts                    # Config schema, defaults, resolution
│   ├── server/
│   │   ├── dev-server.ts            # Vite dev server setup + custom middleware
│   │   ├── middleware/
│   │   │   ├── page-router.ts       # Resolves URL → web-page → template chain
│   │   │   ├── web-files.ts         # Serves static assets from web-files/
│   │   │   ├── api-mock.ts          # Stubs /_api/ Dataverse Web API endpoints
│   │   │   └── hmr-inject.ts        # Injects HMR client + dev toolbar
│   │   └── html-shell.ts            # Wraps rendered content in <!DOCTYPE html> shell
│   ├── engine/
│   │   ├── liquid-engine.ts         # LiquidJS engine factory with PP extensions
│   │   ├── tags/
│   │   │   ├── editable.ts          # {% editable snippets|page ... %}
│   │   │   ├── include-template.ts  # Override {% include 'Template Name' %}
│   │   │   ├── fetchxml.ts          # {% fetchxml var %} ... {% endfetchxml %}
│   │   │   ├── substitution.ts      # {% substitution %} ... {% endsubstitution %}
│   │   │   └── block.ts             # {% block %} ... {% endblock %} (if encountered)
│   │   └── filters/
│   │       └── power-pages.ts       # | boolean, | xml_escape, etc.
│   ├── loaders/
│   │   ├── site-settings.ts         # Parse sitesetting.yml → settings[key] = value
│   │   ├── content-snippets.ts      # Parse content-snippets/**/*.value.html → snippets[name]
│   │   ├── weblink-sets.ts          # Parse weblink-sets/**/*.weblinkset.weblink.yml → weblinks[name]
│   │   ├── web-pages.ts             # Crawl web-pages/ → route table with template chain
│   │   ├── web-templates.ts         # Index web-templates/ by name and by GUID
│   │   ├── page-templates.ts        # Parse page-templates/*.yml → pagetemplateid→webtemplateid map
│   │   ├── site-markers.ts          # Parse sitemarker.yml → sitemarkers[name]
│   │   ├── web-roles.ts             # Parse webrole.yml → role definitions
│   │   └── website.ts               # Parse website.yml → website object
│   ├── context/
│   │   └── scope-builder.ts         # Assembles the full Liquid render scope per request
│   ├── mock-data/
│   │   ├── users.ts                 # Built-in mock user profiles (anonymous, authenticated, admin)
│   │   └── api-store.ts             # In-memory JSON store for /_api/ mock endpoints
│   └── overlay/
│       ├── toolbar.html             # Dev toolbar HTML (injected at bottom of page)
│       ├── toolbar.css              # Dev toolbar styles
│       └── toolbar.js               # Role switcher, page navigator, deploy trigger
├── test/
│   ├── fixtures/                    # Minimal synthetic Power Pages site for unit tests
│   ├── engine/                      # Liquid engine unit tests
│   ├── loaders/                     # Loader unit tests
│   └── integration/                 # Full server integration tests
└── dist/                            # Built output (ESM + CJS + types)
```

### 4.2 Rendering Pipeline

```
┌──────────────────────────────────────────────────────────┐
│                   HTTP GET /some-page                     │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│              1. Page Router Middleware                     │
│  • Match URL against route table built from web-pages/    │
│  • Resolve: webpage.yml → adx_pagetemplateid              │
│           → pagetemplate.yml → adx_webtemplateid          │
│           → web-template .source.html                     │
│  • Fallback: sitemarkers['Page Not Found'] for 404        │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│              2. Scope Builder                             │
│  Constructs Liquid context:                               │
│  • settings     — from sitesetting.yml                    │
│  • snippets     — from content-snippets/*/.value.html     │
│  • weblinks     — from weblink-sets/*/.weblink.yml        │
│  • website      — from website.yml + synthetic fields     │
│  • sitemarkers  — from sitemarker.yml (name → {id, url})  │
│  • user         — current mock user (null = anonymous)    │
│  • page         — current page metadata + copy content    │
│  • request      — { path, params, url }                   │
│  • resx         — resource strings (hardcoded defaults)   │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│              3. Liquid Render                              │
│  • Render web template through LiquidJS                   │
│  • {% include 'Name' %} resolves to web-templates/        │
│  • {% editable snippets 'X' %} → snippets[X]             │
│  • {% editable page 'adx_copy' %} → page copy HTML       │
│    (with nested Liquid evaluation when liquid: true)      │
│  • {% substitution %} blocks rendered with page context   │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│              4. HTML Shell Assembly                        │
│  If pagetemplate.adx_usewebsiteheaderandfooter:           │
│  • <!DOCTYPE html> + <head> (CSS, meta)                   │
│  • Header web template (website.yml → adx_headerwebtemplateid) │
│  • Rendered body content                                  │
│  • Footer web template (website.yml → adx_footerwebtemplateid) │
│  • Page custom_css.css in <style>                         │
│  • Page custom_javascript.js in <script>                  │
│  • Vite HMR client + Dev toolbar injection                │
│  • </body></html>                                         │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Technical Implementation Details

### 5.A The Liquid Engine

Use [`liquidjs`](https://liquidjs.com/) (MIT, actively maintained, 3k+ GitHub stars) configured with Power Pages-specific extensions.

#### 5.A.1 Template Resolution ({% include %})

Power Pages uses `{% include 'Template Name' %}` where the name is a **display name**, not a file path. The engine must resolve this to the corresponding `.webtemplate.source.html` file.

**Resolution strategy:**
1. On startup, index all `web-templates/*/` directories.
2. Parse each `<Name>.webtemplate.yml` to extract `adx_name` and `adx_webtemplateid`.
3. Build two lookup maps: `byName[displayName] → filePath` and `byGuid[guid] → filePath`.
4. Register a custom LiquidJS file system that resolves template names through these maps.

```typescript
// Pseudocode for the custom file system
class PowerPagesFileSystem {
  private templateMap: Map<string, string>; // normalized name → absolute path

  resolve(name: string): string {
    const normalized = name.toLowerCase().replace(/\s+/g, '-');
    const path = this.templateMap.get(normalized);
    if (!path) throw new Error(`Web template not found: '${name}'`);
    return path;
  }
}
```

#### 5.A.2 Custom Tags

**`{% editable %}`**

Handles two forms observed in the codebase:

```liquid
{% editable snippets 'Footer' type: 'html' %}
{% editable page 'adx_copy' type: 'html', liquid: true %}
{% editable page 'adx_title' type: 'html', liquid: true %}
```

Implementation:
```typescript
// Simplified — actual implementation handles edge cases
engine.registerTag('editable', {
  parse(tagToken) {
    this.args = tagToken.args.trim();
  },
  async render(ctx) {
    if (this.args.startsWith('snippets')) {
      const name = this.args.match(/'([^']+)'/)?.[1];
      return name ? (ctx.get(['snippets', name]) ?? '') : '';
    }
    if (this.args.startsWith('page')) {
      const field = this.args.match(/'([^']+)'/)?.[1];
      const content = ctx.get(['page', field]) ?? '';
      // If liquid: true, re-render the content through the engine
      if (this.args.includes('liquid: true') && content) {
        return engine.parseAndRender(content, ctx.getAll());
      }
      return content;
    }
    return '';
  }
});
```

**`{% fetchxml variable %} ... {% endfetchxml %}`**

Parse the FetchXML body, extract the target entity name, query the local mock data store, and assign results:

```typescript
engine.registerTag('fetchxml', {
  parse(tagToken, remainTokens) {
    this.variableName = tagToken.args.trim();
    this.fetchXmlBody = '';
    // Collect tokens until {% endfetchxml %}
    // ...
  },
  async render(ctx) {
    const entityName = extractEntityFromFetchXml(this.fetchXmlBody);
    const results = mockDataStore.query(entityName, this.fetchXmlBody);
    ctx.bottom()[this.variableName] = {
      results: { entities: results }
    };
    return '';
  }
});
```

**`{% substitution %} ... {% endsubstitution %}`**

In Power Pages, `{% substitution %}` marks a block that is rendered at request time (not cached). Locally we have no caching, so this simply renders the content normally:

```typescript
engine.registerTag('substitution', {
  parse(tagToken, remainTokens) {
    this.templates = [];
    // Collect tokens until {% endsubstitution %}
  },
  async render(ctx) {
    return this.liquid.renderer.renderTemplates(this.templates, ctx);
  }
});
```

#### 5.A.3 Custom Filters

Filters observed in the codebase templates:

```typescript
engine.registerFilter('boolean', (v) =>
  v === true || v === 'true' || v === 'True' || v === '1'
);
engine.registerFilter('xml_escape', (v) =>
  String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
);
engine.registerFilter('h', (v) => /* same as escape, alias used in templates */);
// liquidjs already provides: default, escape, truncate, size, upcase, downcase, etc.
```

### 5.B Context & State Provider (Scope Builder)

Before rendering any page, construct the global Liquid scope:

```typescript
interface RenderScope {
  settings: Record<string, string>;      // sitesetting.yml → settings['Key/Path'] = value
  snippets: Record<string, string>;      // content-snippets/ → snippets['Name'] = html
  weblinks: Record<string, WeblinkSet>;  // weblink-sets/ → weblinks['Default'] = { weblinks: [...] }
  website: WebsiteContext;               // website.yml + synthetic fields
  sitemarkers: Record<string, SiteMarker>; // sitemarker.yml → sitemarkers['Home'] = { id, url }
  user: UserContext | null;              // null = anonymous, or mock user object
  page: PageContext;                     // Current page metadata + copy content
  request: RequestContext;               // { path, params, url }
  resx: Record<string, string>;          // Resource strings (defaults)
}
```

#### Loader Details

**Site Settings** (`sitesetting.yml`):
```typescript
// YAML is an array of objects: [{ adx_name, adx_value, ... }]
// Transform to: settings['Authentication/Registration/Enabled'] = 'true'
function loadSiteSettings(yamlPath: string): Record<string, string> {
  const entries = parseYaml(yamlPath) as Array<{ adx_name: string; adx_value?: string }>;
  const settings: Record<string, string> = {};
  for (const entry of entries) {
    if (entry.adx_value !== undefined) {
      settings[entry.adx_name] = String(entry.adx_value);
    }
  }
  return settings;
}
```

**Content Snippets** (`content-snippets/`):
```typescript
// Each snippet: content-snippets/<dir-name>/<Name>.en-US.contentsnippet.value.html
// The adx_name from the .yml file is the lookup key
// Transform to: snippets['Footer'] = '<p>© 2026...</p>'
```

**Weblink Sets** (`weblink-sets/`):
```typescript
// Each set: weblink-sets/<dir-name>/<Name>.en-US.weblinkset.yml + .weblink.yml
// The weblink.yml contains an array of link objects with adx_name, adx_pageid, adx_displayorder
// Must resolve adx_pageid → adx_partialurl from web-pages for the url property
// Transform to: weblinks['Default'] = {
//   weblinks: [{ name: 'Home', url: '/', tooltip: '...', ... }, ...]
// }
```

**Site Markers** (`sitemarker.yml`):
```typescript
// Array: [{ adx_name, adx_pageid, adx_sitemarkerid }]
// Must resolve adx_pageid → { id, url } from web-pages
// Transform to: sitemarkers['Home'] = { id: '51d3...', url: '/' }
```

### 5.C Page Resolution Chain

This is the most critical part and where the original plan had gaps. The resolution chain follows GUIDs through three files:

```
URL "/admin"
  → web-pages/admin/Admin.webpage.yml
    → adx_pagetemplateid: "775b9117-..."
      → page-templates/Default-studio-template.pagetemplate.yml
        → adx_webtemplateid: "f61daa7b-..."
          → web-templates/default-studio-template/Default-studio-template.webtemplate.source.html
            → {% include 'Page Copy' %}
              → web-templates/page-copy/Page-Copy.webtemplate.source.html
                → {% editable page 'adx_copy' type: 'html', liquid: true %}
                  → web-pages/admin/content-pages/Admin.en-US.webpage.copy.html
```

**If `adx_usewebsiteheaderandfooter: true` on the page template:**
- Wrap with Header template (`website.yml → adx_headerwebtemplateid`)
- Wrap with Footer template (`website.yml → adx_footerwebtemplateid`)

**Route table construction** (on startup):
1. Crawl `web-pages/*/` directories.
2. For each, read `<Name>.webpage.yml` → extract `adx_partialurl` and `adx_pagetemplateid`.
3. Build parent→child relationships via `adx_parentpageid` for nested routes.
4. Map each route to its full template chain.

### 5.D Static Asset Serving

Serve files from `web-files/` at their original paths. The `.webfile.yml` files contain `adx_partialurl` which defines the URL path:

```yaml
# bootstrap.min.css.webfile.yml
adx_partialurl: /bootstrap.min.css
```

The middleware serves: `/bootstrap.min.css` → `web-files/bootstrap.min.css`

### 5.E Mock Web API (`/_api/`)

The admin page makes real `fetch()` calls to `/_api/contacts` and `/_api/accounts`. Provide stub endpoints:

| Endpoint | Methods | Mock Behaviour |
|:---------|:--------|:---------------|
| `/_api/contacts` | GET | Return mock contacts from `mock-data/contacts.json` |
| `/_api/contacts(id)` | PATCH | Update in-memory store, return 204 |
| `/_api/accounts` | GET | Return mock accounts from `mock-data/accounts.json` |

The mock store is loaded from JSON files in a `mock-data/` directory within the site (or alongside the config). Supports `$select`, `$orderby`, and `$filter` query parameters at a basic level.

### 5.F Developer Toolbar Overlay

Injected at the bottom of every rendered page:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ PowerPages Local  │ Role: [ Authenticated (Admin) ▼ ] │ Language: [en-US]│
│                      │ Page: [ Home (/)              ▼ ] │ [🚀 Deploy]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

Features:
- **Role Switcher**: Toggle between Anonymous, Authenticated, Administrator. Changes `user` in the Liquid scope and re-renders the current page.
- **Page Navigator**: Dropdown listing all routes from the route table.
- **Deploy Button**: Calls `deploy.ps1` (or a configurable deploy command) via the server and streams stdout/stderr to a browser drawer.

---

## 6. Configuration

### 6.1 Config File: `powerpages-local.config.js`

```javascript
// powerpages-local.config.js (at project root or CWD)
export default {
  // Required: path to the PAC CLI-exported site directory
  sitePath: './src/orgfile-manager',

  // Optional: locale to use for content-pages (default: 'en-US')
  locale: 'en-US',

  // Optional: dev server port (default: 3000)
  port: 3000,

  // Optional: mock data directory for /_api/ stubs
  mockDataPath: './mock-data',

  // Optional: deploy command for the toolbar button
  deployCommand: 'powershell.exe -File ./deploy.ps1',

  // Optional: initial user profile ('anonymous' | 'authenticated' | 'admin')
  defaultRole: 'anonymous',
};
```

### 6.2 CLI Usage

```bash
# Using config file (auto-discovered)
npx powerpages-local

# With explicit site path
npx powerpages-local --site ./src/orgfile-manager --port 3000

# With role preset
npx powerpages-local --role admin
```

### 6.3 Programmatic API

```typescript
import { createServer } from 'powerpages-local';

const server = await createServer({
  sitePath: './src/orgfile-manager',
  port: 3000,
});

await server.start();
// server.stop() to shut down
```

---

## 7. Technology Choices

| Concern | Choice | Rationale |
|:--------|:-------|:----------|
| **Dev server + HMR** | [Vite](https://vitejs.dev/) (middleware mode) | Vite's middleware mode integrates into any Node.js HTTP server. Provides file watching, HMR WebSocket, and CSS hot injection out of the box. No need for a separate Express layer — Vite's `createServer()` returns a Connect-compatible middleware stack. |
| **HTTP framework** | Vite's built-in Connect server | Vite middleware mode already provides a full HTTP server. We add custom Connect middleware for page routing, API mocking, and static file serving. Avoids adding Express as a dependency. |
| **Liquid engine** | [LiquidJS](https://liquidjs.com/) | MIT licensed, Shopify-compatible, extensible tag/filter system, async rendering, TypeScript types. |
| **YAML parsing** | [js-yaml](https://github.com/nodeca/js-yaml) | Standard, zero-dep YAML parser. |
| **CLI framework** | [cac](https://github.com/cacjs/cac) or plain `process.argv` | Lightweight. The CLI surface is small (3-4 flags). |
| **Build** | [tsup](https://tsup.egoist.dev/) | Zero-config TypeScript bundler. Outputs ESM + CJS + `.d.ts`. |
| **Testing** | [Vitest](https://vitest.dev/) | Fast, Vite-native, TypeScript-first. |

---

## 8. Phased Implementation Roadmap

### Phase 1: Core Rendering Engine

**Goal**: Render the Home page with Header + Body + Footer in a browser at `localhost:3000`.

**Deliverables**:
1. Package scaffolding (`package.json`, `tsconfig.json`, build config)
2. All loaders: site-settings, content-snippets, weblink-sets, web-templates, page-templates, web-pages, site-markers, website
3. Liquid engine with custom tags: `{% editable %}`, `{% include %}` override, `{% substitution %}`
4. Liquid filters: `| boolean`, `| default`, `| xml_escape`, `| h`
5. Page resolution chain (URL → webpage → pagetemplate → webtemplate)
6. HTML shell assembly (DOCTYPE, head, header template, body, footer template)
7. Serve `web-files/` as static assets

**Acceptance Criteria**:
- `http://localhost:3000/` renders the Home page with correct Header, body content, Footer, and all CSS applied
- Navigation links in the header are populated from `weblinks.Default`
- Content snippets render (e.g., Mobile Header, Footer)
- Site settings are accessible in templates (e.g., `settings['Search/Enabled']`)

### Phase 2: Full Routing + Hot Reload

**Goal**: Navigate between all pages. File changes trigger instant browser updates.

**Deliverables**:
1. Automatic route table from `web-pages/` crawl (including parent/child nesting)
2. Vite HMR integration — watch `sitePath/**/*` for changes to HTML, CSS, JS, YAML
3. Page-specific `custom_css.css` and `custom_javascript.js` injection
4. 404 page handling via `sitemarkers['Page Not Found']`
5. Access Denied page handling

**Acceptance Criteria**:
- All 6 pages navigable: `/`, `/admin`, `/profile`, `/search`, `/access-denied`, `/page-not-found`
- Editing any `.source.html`, `.copy.html`, `.css` file triggers a browser refresh within 100 ms
- Editing `sitesetting.yml` or `content-snippets/` files reloads correctly

### Phase 3: Mock Data & Web API

**Goal**: Admin panel is functional with mock data. User role switching works.

**Deliverables**:
1. `/_api/` mock endpoints (contacts, accounts) with GET, PATCH support
2. Mock user profiles (anonymous, authenticated user, admin) with role switcher
3. `{% fetchxml %}` tag implementation (if any pages use it)
4. Mock data JSON fixtures for contacts and accounts
5. Developer toolbar overlay (role switcher, page navigator, deploy button)
6. `{% if user %}` renders correctly per selected role

**Acceptance Criteria**:
- Admin page loads, displays mock contacts/accounts tables
- Assigning a user to an org via the admin panel updates mock data and re-renders
- Switching to "Anonymous" hides authenticated-only UI elements
- Switching to "Admin" shows admin-only content

### Phase 4: Polish, CLI & Publish Preparation

**Goal**: Package is ready for standalone extraction and npm publication.

**Deliverables**:
1. CLI entry point (`npx powerpages-local`) with config file auto-discovery
2. Programmatic API (`createServer()`)
3. Config file schema with validation and helpful error messages
4. Comprehensive README with usage examples
5. Unit + integration test suite
6. CI build configuration
7. Error handling: missing files, malformed YAML, unresolvable template references
8. `CHANGELOG.md` and `LICENSE`

**Acceptance Criteria**:
- `npx powerpages-local --site ./src/orgfile-manager` starts the server with zero additional config
- All tests pass
- Package can be extracted to a standalone directory, `npm install && npm run build` succeeds
- `npm pack` produces a valid tarball

---

## 9. What Works Locally vs. What Requires Cloud

| Capability | Local Preview | Cloud Dataverse |
|:-----------|:------------:|:---------------:|
| CSS, Styling & Responsive Layouts | ✅ Instant (<50ms) | ⚠️ Slow (30–60s) |
| HTML & Liquid Templates | ✅ Instant | ⚠️ Slow |
| Client-side JavaScript | ✅ Instant | ⚠️ Slow |
| Content Snippets & Site Settings | ✅ Supported | ✅ Supported |
| Role-based UI (`{% if user %}`) | ✅ Instant toggle | ⚠️ Requires real logins |
| Navigation (weblink-sets) | ✅ Supported | ✅ Supported |
| Client-side Web API (`/_api/`) | ✅ Mocked with JSON | ✅ Real Dataverse |
| FetchXML server-side queries | ✅ Mocked with JSON | ✅ Real Dataverse |
| OOB Basic / Multi-step Forms | ⚠️ Placeholder stub | ✅ Native Dataverse |
| Security Rules (row-level perms) | ⚠️ Simulated | ✅ Full engine |
| Power Virtual Agents widget | ⚠️ Rendered but non-functional | ✅ Full Copilot |

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|:-----|:-------|:-----------|
| LiquidJS doesn't support a Power Pages tag variant | Rendering errors on specific templates | Implement as custom tags/filters. The tag surface area is small and well-understood from codebase analysis. |
| Microsoft changes the PAC CLI export format | Loaders break | Loaders are isolated modules with tests. The format has been stable for years. Version-detect via `.portalconfig/manifest.yml`. |
| Template resolution by display name is ambiguous | Wrong template rendered | Use the `adx_name` field from `.webtemplate.yml` (authoritative) rather than folder/file naming conventions. Log warnings on conflicts. |
| GUID-based resolution chain has broken references | Page fails to render | Validate the full chain on startup. Report clear errors: "Page 'Admin' references pagetemplate GUID X which was not found in page-templates/". |

---

## 11. Next Step

Begin **Phase 1** by scaffolding the package at `packages/powerpages-local/` and implementing the loaders and Liquid engine core, using the Veylo site (`src/orgfile-manager/`) as the test fixture.
