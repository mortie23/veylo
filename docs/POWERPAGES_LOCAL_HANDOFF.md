# Power Pages Local Development - Handoff Notes

## Current State

The `powerpages-local` package has been successfully scaffolded at `packages/powerpages-local/`. The foundation is solidly built and architecture strictly adheres to the Power Pages local folder structure logic. The development server currently boots, parses the site configuration, and accurately renders the templates locally.

**Implemented and Tested:**
1. **Full Scaffolding & Tooling**: Configured a modern npm package with ESM/CJS dual-build via `tsup`, strict TypeScript definitions modeling the Power Pages Dataverse scheme, and an auto-discovering config file (`powerpages-local.config.cjs`).
2. **YAML Data Loaders**: Implemented robust loaders for `website.yml`, `sitesetting.yml`, `content-snippets`, `page-templates`, `web-templates`, `web-pages`, `weblink-sets`, `sitemarker`, and `webrole`.
3. **LiquidJS Engine with Extensions**: Created a custom `liquidjs` environment (`src/engine/liquid-engine.ts`) that:
   - Evaluates CMS-specific tags like `{% editable %}` (resolving both snippet fields and page content variables, including nested Liquid parsing).
   - Handles `{% substitution %}` wrappers.
   - Includes custom Power Pages filters (`boolean`, `xml_escape`, `h`).
   - Uses a custom FileSystem resolver that maps Power Pages' display name `{% include 'Page Copy' %}` syntax directly to the correct `webtemplate.source.html` disk path using GUID chains.
4. **Dev Server Routing**: A Node HTTP server (`src/server/dev-server.ts`) that resolves paths against the Dataverse partial URLs, renders the multi-stage MVC template chain (Page Metadata $\rightarrow$ Page Template $\rightarrow$ Web Template $\rightarrow$ Body HTML), wraps it in the Header/Footer, serves static `web-files/` correctly (images, CSS), and injects page-specific CSS/JS.

*Verification:* The server successfully returns the fully rendered DOM of the Veylo Home page, completely side-stepping the cloud deployment loop.

---

## Next Steps for the Next Session

To bring this package to 100% completion based on the `LOCAL_DEV_ENVIRONMENT_PLAN.md`, the next agent/developer should focus on:

### 1. Vite / HMR Integration
- **Task**: Refactor the plain HTTP server in `dev-server.ts` to wrap around Vite's `createServer` (in middleware mode).
- **Details**: Use Vite to handle static file serving and HMR WebSocket connections. You can use `chokidar` to watch the site directory and stream DOM/CSS updates to the client when `.source.html`, `.css`, or YAML files are changed.

### 2. Developer Toolbar Injection
- **Task**: Inject an HTML overlay toolbar at the bottom of the rendered shell.
- **Details**: Modify `src/server/html-shell.ts` to append the developer toolbar. The toolbar should provide:
  - A Role Switcher (Anonymous, Authenticated, Admin) wired to the existing `/__powerpages/role` server endpoint.
  - A one-click deployment button that executes the repo's deploy script.
  - A fast-navigation page switcher.

### 3. Mock Web API Stubbing (`/_api/`)
- **Task**: Add route middleware to catch `/_api/*` requests.
- **Details**: The Veylo Admin panel (`Admin.webpage.custom_javascript.js`) relies on Dataverse Web API calls for `contacts` and `accounts`. Stub out `/_api/contacts` and `/_api/accounts` to return mock JSON data (either from memory or a `/mock-data` directory) so client-side JavaScript functions seamlessly.

### 4. FetchXML Implementation (Optional/Future)
- **Task**: Register a `{% fetchxml %}` liquid tag.
- **Details**: If any pages utilize server-side FetchXML queries in the future, implement this tag to query the same mock JSON store used by the Web API.
