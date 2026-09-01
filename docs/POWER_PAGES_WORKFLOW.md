# Power Pages Development & Synchronization Guide

This guide details the development, synchronization, and deployment lifecycle for this Power Pages site using the **Enhanced Data Model (Model Version 2)**.

This repository is designed to be **environment-agnostic** and portable across different Dataverse instances (e.g., Dev, Test, Prod).

---

## 1. Environment Setup (`.env`)

Local environment settings (such as your target Dataverse URL and site GUID) are decoupled from the codebase using a local `.env` file.

1. **Copy the template**:
   ```powershell
   Copy-Item .env.example .env
   ```
2. **Configure your `.env`**:
   ```env
   # Target Dataverse environment URL
   DATAVERSE_ENVIRONMENT_URL=https://your-org.crm.dynamics.com

   # Target Power Pages Website ID (GUID)
   POWERPAGES_WEBSITE_ID=your-website-id-guid

   # Power Pages Model Version (2 for Enhanced Data Model)
   POWERPAGES_MODEL_VERSION=2

   # Path to the site code folder
   POWERPAGES_SITE_PATH=./src/orgfile-manager
   ```
   > **Note**: `.env` is listed in `.gitignore` and is never committed to source control.

---

## 2. Authentication & Status Check

Ensure Microsoft PowerPlatform CLI (`pac`) is installed:

```powershell
# Check CLI version
pac --version

# View active environment and websites
.\status.ps1
```

### Authenticating to Dataverse

To connect to a new Dataverse environment:

```powershell
# Interactive browser login
pac auth create --environment https://your-org.crm.dynamics.com

# Switch between authenticated profiles
pac auth select --index <index-number>
```

---

## 3. Daily Development Workflow

### Step 1: Sync Down Latest Changes from Dataverse (Optional)
If changes were made via the Power Pages Design Studio:

```powershell
.\sync-down.ps1
```
*This reads `POWERPAGES_WEBSITE_ID` from your `.env` file (or can be passed via `.\sync-down.ps1 -WebsiteId <GUID>`).*

### Step 2: Local Code Development
You can edit the following files directly in your IDE:
- **HTML & Liquid Templates**: `src/orgfile-manager/web-pages/**/content-pages/*.copy.html` and `src/orgfile-manager/web-templates/**/*.webtemplate.source.html`
- **JavaScript**: `*.custom_javascript.js`
- **CSS**: `*.custom_css.css` or global theme in `src/orgfile-manager/web-files/theme.css`
- **Site Settings & Snippets**: `sitesetting.yml` and `content-snippets/`

### Step 3: Test Upload Simulation (Dry Run)
Preview what will be uploaded without modifying Dataverse:

```powershell
.\deploy.ps1 -WhatIf
```

### Step 4: Deploy / Upload Changes

```powershell
.\deploy.ps1
```
*Uploads local site code to the active Dataverse instance via `pac powerpages upload` with model version 2.*

### Step 5: Portal Cache Invalidation

Power Pages caches configuration and static assets for high performance. After uploading, invalidate the cache:

1. **Power Pages Studio (Easiest)**:
   - Open Power Pages Design Studio in your browser.
   - Click **Preview** -> **Sync** (or **Browse website**).
2. **Admin Services Route**:
   - Log into your portal as a user with Administrator web role.
   - Navigate to `https://<your-portal-url>/_services/about`
   - Click the **Clear Cache** button.
3. **Hard Refresh in Browser**:
   - `Ctrl + F5` (Windows) to bypass local browser cache.

---

## 4. Architecture & Directory Structure

```text
src/orgfile-manager/
├── .portalconfig/           # PAC CLI manifest & GUID tracking
├── botconsumer.yml          # Copilot / Bot integration record
├── content-snippets/        # Reusable UI strings, localized snippets, titles, logos
├── page-templates/          # Page template mappings (points pages to web templates)
├── publishingstate.yml      # Publishing states (Draft, Published)
├── sitemarker.yml           # Sitemarkers for dynamic page linking
├── sitesetting.yml          # Key-value site configuration & security settings
├── web-files/               # Static assets (stylesheets, images, fonts)
├── web-pages/               # Site pages hierarchy
│   └── <page-name>/
│       ├── <page>.webpage.yml          # Root page metadata
│       └── content-pages/              # Localized content variants
│           ├── <page>.en-US.webpage.copy.html  # HTML/Liquid body
│           ├── <page>.en-US.webpage.custom_css.css
│           ├── <page>.en-US.webpage.custom_javascript.js
│           └── <page>.en-US.webpage.yml        # Localized page metadata
├── web-templates/           # Modular Liquid templates (Header, Footer, Layouts)
├── weblink-sets/            # Navigation menus & profile links
├── webrole.yml              # Security roles (Anonymous, Authenticated, Admin)
└── website.yml              # Root site metadata & header/footer template bindings
```

---

## 5. Best Practices & Rules

1. **Keep `.env` Private**:
   Never commit `.env` containing your private Dataverse URLs or IDs. Use `.env.example` as the shared template.
2. **Preserve GUIDs in YAML**:
   Never manually delete or alter `adx_` IDs in YAML files unless intentionally deleting/recreating records.
3. **Enhanced Data Model Flag**:
   Always use Model Version 2 (`-mv 2`).
4. **Clean Liquid Tags**:
   Use `{% include 'TemplateName' %}` and `{{ snippets['SnippetName'] }}` for maintainable, reusable component markup.
