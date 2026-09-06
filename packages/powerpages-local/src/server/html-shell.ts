import * as fs from 'node:fs';
import * as path from 'node:path';
import type { Liquid } from 'liquidjs';
import type { SiteData, WebPageRecord, RenderScope } from '../types.js';
import { readPageContent } from '../loaders/web-pages.js';

import { DEFAULT_MOCKS } from '../mocks/default-mocks.js';

/**
 * Render a full HTML page by assembling the template chain.
 *
 * Resolution chain:
 *   webpage → pagetemplate → webtemplate → render with Liquid
 *   If pagetemplate.useHeaderAndFooter → wrap with header + footer templates
 */
export async function renderPage(
  engine: Liquid,
  siteData: SiteData,
  page: WebPageRecord,
  scope: RenderScope,
  locale: string,
  sitePath?: string,
  mockTemplatesPath?: string | null,
): Promise<string> {
  // Step 1: Resolve page template
  const pageTemplate = siteData.pageTemplates.get(page.pageTemplateId);
  if (!pageTemplate) {
    return errorPage(
      `Page template not found for page "${page.name}" (pagetemplateid: ${page.pageTemplateId})`,
    );
  }

  // Step 2: Resolve web template (or fallback for ASPX rewrite routes)
  let bodySource = '';
  if (pageTemplate.webTemplateId) {
    const webTemplate = siteData.webTemplates.get(pageTemplate.webTemplateId);
    if (!webTemplate) {
      return errorPage(
        `Web template not found for page template "${pageTemplate.name}" (webtemplateid: ${pageTemplate.webTemplateId})`,
      );
    }
    bodySource = fs.readFileSync(webTemplate.sourcePath, 'utf-8');
  } else if (pageTemplate.rewriteUrl) {
    // Resolution Waterfall for ASPX built-in pages
    // Step A: Check user-provided mock-templates folder
    let resolvedMock = false;
    if (mockTemplatesPath) {
      // e.g. ~/Pages/Profile.aspx -> Profile.html
      const fileName = path.basename(pageTemplate.rewriteUrl).replace('.aspx', '.html');
      const userMockPath = path.join(mockTemplatesPath, fileName);
      if (fs.existsSync(userMockPath)) {
        bodySource = fs.readFileSync(userMockPath, 'utf-8');
        resolvedMock = true;
      }
    }

    // Step B: Check package built-in defaults
    if (!resolvedMock && DEFAULT_MOCKS[pageTemplate.rewriteUrl]) {
      bodySource = DEFAULT_MOCKS[pageTemplate.rewriteUrl];
      resolvedMock = true;
    }

    // Step C: Minimal raw fallback
    if (!resolvedMock) {
      bodySource = `
        <div class="wrapper-body" role="main">
          <div class="container" style="padding-top: 2rem; padding-bottom: 2rem;">
            <h1>{{ page.title | escape }}</h1>
            {{ page.copy }}
            <div class="alert alert-info" style="margin-top: 2rem;">
              <strong>Local Dev Note:</strong> This is a built-in platform page (<code>${pageTemplate.rewriteUrl}</code>).
              Server-side ASP.NET components are not rendered locally.
            </div>
          </div>
        </div>
      `;
    }
  } else {
    return errorPage(`Page template "${pageTemplate.name}" has no Web Template and no Rewrite URL.`);
  }

  // Step 3: Render the body web template through Liquid
  let bodyHtml: string;
  try {
    bodyHtml = await engine.parseAndRender(bodySource, scope);
  } catch (err) {
    return errorPage(`Liquid render error in page template "${pageTemplate.name}": ${err}`);
  }

  // Step 4: Optionally wrap with header + footer
  let headerHtml = '';
  let footerHtml = '';

  if (pageTemplate.useHeaderAndFooter) {
    const headerTemplate = siteData.webTemplates.get(
      siteData.website.headerWebTemplateId,
    );
    const footerTemplate = siteData.webTemplates.get(
      siteData.website.footerWebTemplateId,
    );

    if (headerTemplate) {
      try {
        const src = fs.readFileSync(headerTemplate.sourcePath, 'utf-8');
        headerHtml = await engine.parseAndRender(src, scope);
      } catch (err) {
        headerHtml = `<!-- Header render error: ${err} -->`;
      }
    }

    if (footerTemplate) {
      try {
        const src = fs.readFileSync(footerTemplate.sourcePath, 'utf-8');
        footerHtml = await engine.parseAndRender(src, scope);
      } catch (err) {
        footerHtml = `<!-- Footer render error: ${err} -->`;
      }
    }
  }

  // Step 5: Read page-specific CSS and JS
  const content = readPageContent(page, locale);

  // Step 6: Assemble full HTML document
  const toolbarHtml = generateToolbar(siteData, scope);
  return assembleHtml({
    title: content.title || page.name,
    siteName: siteData.website.name,
    headerHtml,
    bodyHtml,
    footerHtml,
    customCss: content.customCss,
    customJs: content.customJs,
    toolbarHtml,
  }, sitePath);
}

// ---------------------------------------------------------------------------
// HTML document assembly
// ---------------------------------------------------------------------------

interface HtmlParts {
  title: string;
  siteName: string;
  headerHtml: string;
  bodyHtml: string;
  footerHtml: string;
  customCss: string;
  customJs: string;
  toolbarHtml: string;
}

function assembleHtml(parts: HtmlParts, sitePath?: string): string {
  const customCssBlock = parts.customCss.trim()
    ? `<style>${parts.customCss}</style>`
    : '';
  const customJsBlock = parts.customJs.trim()
    ? `<script>${parts.customJs}</script>`
    : '';

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(parts.title)} - ${escapeHtml(parts.siteName)}</title>
  ${customCssBlock}
</head>
<body>
${parts.headerHtml}
${parts.bodyHtml}
${parts.footerHtml}
${customJsBlock}
${parts.toolbarHtml}
</body>
</html>`;
}

function errorPage(message: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Error - powerpages-local</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    .error { background: #fee; border: 1px solid #c00; padding: 1rem; border-radius: 4px; }
    code { background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 2px; }
  </style>
</head>
<body>
  <div class="error">
    <h1>⚠️ powerpages-local: Render Error</h1>
    <p>${escapeHtml(message)}</p>
  </div>
</body>
</html>`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function generateToolbar(siteData: SiteData, scope: RenderScope): string {
  const currentRole = scope.user?.roles?.[0] || 'anonymous';
  let optionsHtml = '';
  for (const [url, page] of siteData.routeTable.entries()) {
    optionsHtml += `<option value="${url}">${escapeHtml(page.name)} (${url})</option>`;
  }

  return `
    <style>
      #pp-local-toolbar {
        position: fixed;
        bottom: 0; left: 0; right: 0;
        background: #333; color: white;
        padding: 8px 16px;
        display: flex; gap: 16px; align-items: center;
        font-family: system-ui, sans-serif;
        font-size: 14px;
        z-index: 999999;
      }
      #pp-local-toolbar select, #pp-local-toolbar button {
        padding: 4px 8px;
        font-size: 14px;
      }
    </style>
    <div id="pp-local-toolbar">
      <div>
        <label>Role:</label>
        <select id="pp-role-switcher" onchange="
          fetch('/__powerpages/role', {
            method: 'POST',
            body: JSON.stringify({ role: this.value })
          }).then(() => window.location.reload())
        ">
          <option value="anonymous" ${currentRole === 'anonymous' ? 'selected' : ''}>Anonymous</option>
          <option value="authenticated" ${currentRole === 'authenticated' ? 'selected' : ''}>Authenticated</option>
          <option value="admin" ${currentRole === 'admin' ? 'selected' : ''}>Admin</option>
        </select>
      </div>
      <div>
        <label>Page:</label>
        <select id="pp-page-switcher" onchange="if(this.value) window.location.href = this.value;">
          <option value="">-- Jump to page --</option>
          ${optionsHtml}
        </select>
      </div>
      <button onclick="
        this.disabled = true;
        this.textContent = 'Deploying...';
        fetch('/__powerpages/deploy', { method: 'POST' })
          .then(res => res.json())
          .then(data => {
            alert(data.message);
            this.textContent = 'Deploy';
            this.disabled = false;
          })
      ">Deploy</button>
    </div>
  `;
}
