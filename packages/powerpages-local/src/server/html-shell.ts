import * as fs from 'node:fs';
import type { Liquid } from 'liquidjs';
import type { SiteData, WebPageRecord, RenderScope } from '../types.js';
import { readPageContent } from '../loaders/web-pages.js';

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
): Promise<string> {
  // Step 1: Resolve page template
  const pageTemplate = siteData.pageTemplates.get(page.pageTemplateId);
  if (!pageTemplate) {
    return errorPage(
      `Page template not found for page "${page.name}" (pagetemplateid: ${page.pageTemplateId})`,
    );
  }

  // Step 2: Resolve web template
  const webTemplate = siteData.webTemplates.get(pageTemplate.webTemplateId);
  if (!webTemplate) {
    return errorPage(
      `Web template not found for page template "${pageTemplate.name}" (webtemplateid: ${pageTemplate.webTemplateId})`,
    );
  }

  // Step 3: Render the body web template through Liquid
  const bodySource = fs.readFileSync(webTemplate.sourcePath, 'utf-8');
  let bodyHtml: string;
  try {
    bodyHtml = await engine.parseAndRender(bodySource, scope);
  } catch (err) {
    return errorPage(`Liquid render error in "${webTemplate.name}": ${err}`);
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
  return assembleHtml({
    title: content.title || page.name,
    siteName: siteData.website.name,
    headerHtml,
    bodyHtml,
    footerHtml,
    customCss: content.customCss,
    customJs: content.customJs,
  });
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
}

function assembleHtml(parts: HtmlParts): string {
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
  <link rel="stylesheet" href="/bootstrap.min.css">
  <link rel="stylesheet" href="/theme.css">
  <link rel="stylesheet" href="/portalbasictheme.css">
  ${customCssBlock}
</head>
<body>
${parts.headerHtml}
${parts.bodyHtml}
${parts.footerHtml}
${customJsBlock}
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
