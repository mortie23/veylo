# Veylo - Power Pages Portal

Source code for the **Veylo** Power Pages portal, managed using the Microsoft PowerPlatform CLI (`pac`) and the **Enhanced Data Model** (`-mv 2`).

This repository is **environment-agnostic** and can be deployed to any Dataverse instance.

## Javascript

⚠️ Important Admin Prerequisite: By default, Dataverse environments block .js files from being uploaded as attachments. 
To unblock this, navigate to 

- Power Platform Admin Center > Your Environment > Settings > Product > Privacy + Security 
  - remove js from the Blocked Attachments list

---

## 🚀 Quick Start

1. **Configure your local environment**:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env` with your target Dataverse URL and Website ID.

2. **Check PAC CLI connection**:
   ```powershell
   .\status.ps1
   ```

3. **Deploy to Dataverse**:
   ```powershell
   # Dry-run preview
   .\deploy.ps1 -WhatIf

   # Upload to Dataverse
   .\deploy.ps1
   ```

4. **Sync down latest changes from Dataverse (Optional)**:
   ```powershell
   # Sync Power Pages portal code
   .\sync-down.ps1

   # Sync Dataverse tables & solution schema
   .\solution-sync.ps1
   ```

5. **Deploy Dataverse schema changes**:
   ```powershell
   # Dry-run preview
   .\solution-deploy.ps1 -WhatIf

   # Deploy schema to Dataverse
   .\solution-deploy.ps1
   ```

---

## 📁 Repository Structure

```text
├── .env.example             # Template for local environment config
├── deploy.ps1               # Deploy Power Pages portal code (reads .env)
├── sync-down.ps1            # Download Power Pages portal code (reads .env)
├── solution-deploy.ps1      # Pack and deploy Dataverse solution schema (reads .env)
├── solution-sync.ps1        # Export and unpack Dataverse solution schema (reads .env)
├── status.ps1               # Check active PAC auth & sites
├── solutions/               # Version-controlled Dataverse solution source
│   └── VeyloCore/           # Entities, attributes, relationships, keys, choices
├── src/orgfile-manager/     # Power Pages site code
│   ├── .portalconfig/       # Manifest and site metadata
│   ├── content-snippets/    # Localized text snippets & site name
│   ├── page-templates/      # Page template mappings
│   ├── web-files/           # Static stylesheets, images, fonts
│   ├── web-pages/           # Web page content and custom JS/CSS
│   ├── web-templates/       # Master Liquid templates (Header, Footer)
│   └── weblink-sets/        # Top navigation menu
├── scripts/                 # Core PowerShell modules & dotenv loader
└── docs/
    └── POWER_PAGES_WORKFLOW.md # Full architecture & development guide
```

---

## 📖 Documentation

For detailed information on the local development workflow, Liquid templating, portal caching, and security roles, see:
- [Power Pages Development & Sync Guide](docs/POWER_PAGES_WORKFLOW.md)
- [Local Development & Preview Environment Plan](docs/LOCAL_DEV_ENVIRONMENT_PLAN.md)
