# Power Pages Local Development Environment: Architecture & Plan

> **Goal**: Eliminate the 45-second "deploy $\rightarrow$ clear cache $\rightarrow$ refresh" feedback loop by building a local, mock-driven Power Pages preview server with instant hot reload (<50ms).

---

## 1. The Problem: Why Power Pages DX Is Painful

In standard modern web development (Next.js, Vite, Vue, Svelte), developers enjoy **instant Hot Module Replacement (HMR)**: save a CSS or HTML file, and the browser updates in milliseconds.

In Power Pages:
1. You edit a template or CSS file locally in VS Code.
2. You run `.\deploy.ps1` (which invokes `pac powerpages upload`).
3. You wait 5–15 seconds for PAC CLI to authenticate and push files to Dataverse tables.
4. You navigate to Power Pages Studio or `/_services/about` to click **Clear Cache**.
5. You hard-refresh the browser (`Ctrl+F5`).
6. **Total elapsed time per change: 30 to 60+ seconds.**

### Does Microsoft Provide a Local Preview Solution?
**No.** Microsoft provides no offline runtime, emulator, or local preview tool for Power Pages. 
* Power Pages' Liquid engine runs inside Azure App Services as part of a proprietary ASP.NET rendering pipeline tied to Dataverse via internal RPC/Web APIs.
* Microsoft's "VS Code integration" is strictly a cloud-sync tool; previewing always redirects to an Azure-hosted URL.

---

## 2. Feasibility: Can We Build Our Own Local Environment?

**Yes.** Deconstructing the files in `src/orgfile-manager/` reveals that Power Pages is actually a deterministic MVC template pipeline:

```
                  ┌─────────────────────────────────────┐
                  │          HTTP GET /page-url         │
                  └──────────────────┬──────────────────┘
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
┌──────────────────────────┐                   ┌──────────────────────────┐
│     Metadata Context     │                   │     Layout & Content     │
├──────────────────────────┤                   ├──────────────────────────┤
│ • sitesetting.yml        │                   │ • website.yml (Header)   │
│ • content-snippets/      │                   │ • page-template.yml      │
│ • weblink-sets/          │                   │ • web-page.copy.html     │
│ • Mock User (Contact)    │                   │ • website.yml (Footer)   │
└────────────┬─────────────┘                   └─────────────┬────────────┘
             │                                               │
             └───────────────────────┬───────────────────────┘
                                     ▼
                      ┌─────────────────────────────┐
                      │    Liquid Execution Engine  │
                      │       (Node.js + liquidjs)  │
                      └──────────────┬──────────────┘
                                     ▼
                      ┌─────────────────────────────┐
                      │    Rendered HTML + Assets   │
                      │  (Bootstrap, CSS, JS, HMR)  │
                      └─────────────────────────────┘
```

Everything required to render 95% of the portal UI is already present as static text and YAML files on your local machine:
* **Layouts**: `src/orgfile-manager/web-templates/`
* **Pages**: `src/orgfile-manager/web-pages/**/content-pages/*.copy.html`
* **Snippets**: `src/orgfile-manager/content-snippets/`
* **Settings**: `src/orgfile-manager/sitesetting.yml`
* **Menus**: `src/orgfile-manager/weblink-sets/`
* **Styles & Scripts**: `src/orgfile-manager/web-files/`

---

## 3. Architecture of `powerpages-local`

We can create a lightweight development server inside this repository (e.g., `tools/local-preview/`) powered by **Node.js, Vite, and LiquidJS**.

### Core Architecture Components

```
tools/local-preview/
├── server.js               # Express + Vite development server
├── liquid-engine.js        # LiquidJS engine configured with Power Pages tags & filters
├── context-loader.js       # Reads YAML files (sitesettings, snippets, weblinks, pages)
├── template-resolver.js    # Resolves {% include 'Web Template' %} to local files
├── mock-data/
│   ├── user.json           # Mock Contact / Web Role profiles (Admin vs Anonymous)
│   ├── tables/             # Mock Dataverse entity tables (JSON)
│   └── web-api.js          # Stubs /_api/ Dataverse Web API endpoints
└── overlay/
    └── devtools-toolbar.js # Injected UI overlay for fast switching & one-click deploy
```

---

## 4. Technical Implementation Details

### A. The Liquid Engine (`liquidjs`)
Power Pages uses a variant of Shopify Liquid with custom tags. Using the open-source [`liquidjs`](https://liquidjs.com/) library, we implement Power Pages extensions:

#### 1. Custom Tags
* **`{% include 'Template Name' %}`**:
  Map template names (e.g. `'Header'`, `'Page Copy'`) to matching folders in `src/orgfile-manager/web-templates/**/<Name>.webtemplate.source.html`.
* **`{% editable snippets 'Snippet Name' type: 'html' %}`**:
  Render the snippet content directly without the CMS edit wrapper:
  ```javascript
  engine.registerTag('editable', {
    parse(tagToken) { this.args = tagToken.args; },
    render(ctx) {
      // e.g. {% editable snippets 'Mobile Header' type: 'html' %}
      if (this.args.includes('snippets')) {
        const snippetName = this.args.match(/'([^']+)'/)[1];
        return ctx.get(['snippets', snippetName]) || '';
      }
      if (this.args.includes('page')) {
        return ctx.get(['page', 'copy']) || '';
      }
      return '';
    }
  });
  ```
* **`{% fetchxml variable_name %} ... {% endfetchxml %}`**:
  Parse the FetchXML query, extract the target table (e.g. `incident`, `account`, or custom entities), query the local `mock-data/tables/<table_name>.json`, and assign the result array to `variable_name.results.entities`.

#### 2. Custom Filters
Power Pages introduces filters like `| boolean`, `| default: ...`, `| xml_escape`.
```javascript
engine.registerFilter('boolean', v => v === true || v === 'true' || v === '1');
```

---

### B. Context & State Provider
Before rendering any page, `context-loader.js` constructs the global Liquid scope:

```javascript
const scope = {
  // 1. Site Settings (loaded from sitesetting.yml)
  settings: loadSiteSettings(),

  // 2. Content Snippets (loaded from content-snippets/)
  snippets: loadContentSnippets(),

  // 3. Navigation Links (loaded from weblink-sets/)
  weblinks: loadWeblinkSets(),

  // 4. Current Website metadata
  website: {
    adx_partialurl: '',
    sign_in_url_substitution: '/signin'
  },

  // 5. Current Mock User (switchable in DevTools toolbar)
  user: activeUser, // null for anonymous, or { fullname: "Chris", email: "chris@health.gov.au", roles: ["Admin"] }

  // 6. Request Context
  request: {
    path: req.path,
    params: req.query
  },

  // 7. Resource Strings (resx)
  resx: {
    Skip_To_Content: 'Skip to main content',
    Main_Navigation: 'Main Navigation'
  }
};
```

---

### C. Page & Asset Pipeline
For any requested URL (e.g. `http://localhost:3000/` or `/profile`):
1. **Find Page**: Look up the directory in `src/orgfile-manager/web-pages/`.
2. **Read Layout**:
   * Header: `web-templates/header/Header.webtemplate.source.html`
   * Body: `web-pages/<name>/content-pages/<name>.en-US.webpage.copy.html`
   * Footer: `web-templates/footer/Footer.webtemplate.source.html`
3. **Inject Stylesheets & Scripts**:
   * Global: `/web-files/bootstrap.min.css`, `/web-files/theme.css`, `/web-files/portalbasictheme.css`
   * Page-specific: `<style>${page.custom_css}</style>` and `<script>${page.custom_javascript}</script>`
4. **Vite / HMR Client**:
   Inject the Vite HMR script into `<head>` so file changes reload instantly.

---

### D. The Developer Toolbar Overlay
To make local development intuitive, the server injects a floating toolbar at the bottom of the page:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ PowerPages Local  │ Role: [ Authenticated (Admin) ▼ ] │ Language: [ en-US ]│
│                      │ Page: [ Home (/)              ▼ ] │ [🚀 Deploy to Cloud]│
└─────────────────────────────────────────────────────────────────────────────┘
```

* **Role Switcher**: Click to instantly toggle between `Anonymous`, `Standard User`, and `System Administrator` without logging in/out.
* **Page Switcher**: Jump to any page defined in `web-pages/`.
* **Deploy to Cloud Button**: Executes `powershell.exe -File ./deploy.ps1` in the background and displays the deployment logs directly in a browser drawer.

---

## 5. Phased Implementation Roadmap

| Phase | Deliverable | Scope |
| :--- | :--- | :--- |
| **Phase 1** | **Liquid Preview Core** | Set up `tools/local-preview` with Node.js, `liquidjs`, and Express. Parse `sitesetting.yml` and render `Header` + `Home` copy + `Footer`. |
| **Phase 2** | **Static Assets & Hot Reload** | Integrate Vite / LiveReload to watch `src/orgfile-manager/**/*` and stream CSS/HTML updates instantly. Serve `web-files/` (Bootstrap, images). |
| **Phase 3** | **Page Routing & Dynamic Templates** | Automatically crawl `web-pages/` and `page-templates/` to build a local router matching Power Pages URL paths. |
| **Phase 4** | **Mock Dataverse & FetchXML** | Implement `{% fetchxml %}` mocking from `mock-data/tables/` and stub `/_api/` for client-side JavaScript calls. |
| **Phase 5** | **Cloud Bridge** | Add the floating DevTools toolbar with user switching and one-click `deploy.ps1` execution. |

---

## 6. What Works Locally vs. What Requires Cloud Testing

| Capability | Local Preview Engine | Cloud Dataverse |
| :--- | :---: | :---: |
| **CSS, Styling & Responsive Layouts** | ✅ Instant (<50ms) | ⚠️ Slow (30–60s deploy) |
| **HTML & Liquid Templates** | ✅ Instant | ⚠️ Slow |
| **Client-side JavaScript** | ✅ Instant | ⚠️ Slow |
| **Content Snippets & Site Settings** | ✅ Supported | ✅ Supported |
| **Role-based UI Visibility (`{% if user %}`)** | ✅ Instant toggle | ⚠️ Requires real logins |
| **Client-side Web API calls (`/_api/`)** | ✅ Mockable with JSON | ✅ Real Dataverse records |
| **Out-of-the-Box Basic Forms / Multi-step Forms** | ⚠️ Placeholder stub | ✅ Native Dataverse forms |
| **Power Pages Security Rules (Row-level / Table Perms)** | ⚠️ Simulated | ✅ Full Dataverse engine |

---

## 7. Next Step

When you are ready to build this, we can scaffold `tools/local-preview/` directly into this repo with a `package.json` (`npm run dev`), letting you edit HTML/CSS with immediate local feedback and deploy to Dataverse only when you are satisfied with your changes.
