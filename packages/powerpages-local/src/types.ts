/**
 * Shared type definitions for the powerpages-local package.
 *
 * These types model the Power Pages data structures as they appear
 * in the PAC CLI export format (YAML/HTML files on disk).
 */

// ---------------------------------------------------------------------------
// Site Settings
// ---------------------------------------------------------------------------

/** A single entry from sitesetting.yml */
export interface SiteSettingEntry {
  adx_name: string;
  adx_value?: string;
  adx_description?: string;
  adx_sitesettingid: string;
}

// ---------------------------------------------------------------------------
// Content Snippets
// ---------------------------------------------------------------------------

export interface ContentSnippet {
  name: string;
  value: string;
}

// ---------------------------------------------------------------------------
// Web Templates
// ---------------------------------------------------------------------------

export interface WebTemplateRecord {
  /** Display name from the .yml (e.g. "Header", "Page Copy") */
  name: string;
  /** GUID from adx_webtemplateid */
  id: string;
  /** Absolute path to the .source.html file */
  sourcePath: string;
}

// ---------------------------------------------------------------------------
// Page Templates
// ---------------------------------------------------------------------------

export interface PageTemplateRecord {
  name: string;
  /** GUID from adx_pagetemplateid */
  id: string;
  /** GUID reference to the web template */
  webTemplateId?: string;
  /** Optional rewrite URL for built-in platform pages (e.g. ~/Pages/Profile.aspx) */
  rewriteUrl?: string;
  /** Whether to wrap with Header + Footer */
  useHeaderAndFooter: boolean;
}

// ---------------------------------------------------------------------------
// Web Pages
// ---------------------------------------------------------------------------

export interface WebPageRecord {
  name: string;
  /** GUID from adx_webpageid */
  id: string;
  /** URL path segment (e.g. "/", "/admin", "/profile") */
  partialUrl: string;
  /** GUID reference to the page template */
  pageTemplateId: string;
  /** GUID of the parent page (empty string for root pages) */
  parentPageId: string;
  /** Whether this is the root page of the site */
  isRoot: boolean;
  /** Absolute path to the directory containing this page's files */
  dirPath: string;
  /** Publishing state GUID */
  publishingStateId: string;
}

export interface ResolvedPage extends WebPageRecord {
  /** Resolved URL path (e.g. "/admin") */
  url: string;
  /** Page copy HTML content */
  copy: string;
  /** Page-specific CSS */
  customCss: string;
  /** Page-specific JavaScript */
  customJs: string;
  /** Page summary HTML */
  summary: string;
  /** Page title */
  title: string;
}

// ---------------------------------------------------------------------------
// Weblink Sets
// ---------------------------------------------------------------------------

export interface Weblink {
  name: string;
  url: string;
  displayOrder: number;
  tooltip?: string;
  openInNewWindow: boolean;
  pageId?: string;
}

export interface WeblinkSet {
  name: string;
  weblinks: Weblink[];
}

// ---------------------------------------------------------------------------
// Site Markers
// ---------------------------------------------------------------------------

export interface SiteMarker {
  name: string;
  id: string;
  url: string;
  pageId: string;
}

// ---------------------------------------------------------------------------
// Website
// ---------------------------------------------------------------------------

export interface WebsiteConfig {
  name: string;
  id: string;
  headerWebTemplateId: string;
  footerWebTemplateId: string;
  defaultLanguageId: string;
  languageCode: number;
}

// ---------------------------------------------------------------------------
// Web Roles
// ---------------------------------------------------------------------------

export interface WebRole {
  name: string;
  id: string;
  isAnonymous: boolean;
  isAuthenticated: boolean;
}

// ---------------------------------------------------------------------------
// Mock User
// ---------------------------------------------------------------------------

export type UserRole = 'anonymous' | 'authenticated' | 'admin';

export interface MockUser {
  fullname: string;
  email: string;
  contactid: string;
  roles: string[];
}

// ---------------------------------------------------------------------------
// Liquid Render Scope
// ---------------------------------------------------------------------------

export interface RenderScope {
  settings: Record<string, string>;
  snippets: Record<string, string>;
  weblinks: Record<string, WeblinkSet>;
  website: Record<string, unknown>;
  sitemarkers: Record<string, { id: string; url: string }>;
  user: MockUser | null;
  page: Record<string, unknown>;
  request: { path: string; params: Record<string, string>; url: string };
  resx: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Loaded Site Data (all loaders combined)
// ---------------------------------------------------------------------------

export interface SiteData {
  settings: Record<string, string>;
  snippets: Record<string, string>;
  weblinks: Record<string, WeblinkSet>;
  website: WebsiteConfig;
  webTemplates: Map<string, WebTemplateRecord>;
  pageTemplates: Map<string, PageTemplateRecord>;
  pages: Map<string, WebPageRecord>;
  routeTable: Map<string, WebPageRecord>;
  siteMarkers: Record<string, SiteMarker>;
  webRoles: WebRole[];
}
