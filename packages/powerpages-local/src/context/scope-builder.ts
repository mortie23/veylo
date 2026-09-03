import type { IncomingMessage } from 'node:http';
import type {
  SiteData,
  WebPageRecord,
  RenderScope,
  MockUser,
  UserRole,
} from '../types.js';
import { readPageContent } from '../loaders/web-pages.js';

// ---------------------------------------------------------------------------
// Built-in mock user profiles
// ---------------------------------------------------------------------------

const MOCK_USERS: Record<Exclude<UserRole, 'anonymous'>, MockUser> = {
  authenticated: {
    fullname: 'Test User',
    email: 'test.user@example.com',
    contactid: '00000000-0000-0000-0000-000000000001',
    roles: ['Authenticated Users'],
  },
  admin: {
    fullname: 'Admin User',
    email: 'admin@example.com',
    contactid: '00000000-0000-0000-0000-000000000002',
    roles: ['Authenticated Users', 'Administrators'],
  },
};

// ---------------------------------------------------------------------------
// Default resource strings (resx)
// ---------------------------------------------------------------------------

const DEFAULT_RESX: Record<string, string> = {
  Skip_To_Content: 'Skip to main content',
  Main_Navigation: 'Main Navigation',
  Sign_In: 'Sign in',
  Sign_Out: 'Sign out',
  Profile_Text: 'Profile',
  Default_Profile_name: 'Profile',
  Search_DefaultText: 'Search',
};

// ---------------------------------------------------------------------------
// Scope builder
// ---------------------------------------------------------------------------

/**
 * Build the full Liquid render scope for a specific page request.
 */
export function buildScope(
  siteData: SiteData,
  page: WebPageRecord,
  locale: string,
  role: UserRole,
  req: IncomingMessage,
): RenderScope {
  const content = readPageContent(page, locale);
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);

  const user = role === 'anonymous' ? null : MOCK_USERS[role];

  return {
    settings: siteData.settings,
    snippets: siteData.snippets,
    weblinks: siteData.weblinks,
    website: {
      adx_name: siteData.website.name,
      adx_partialurl: '',
      sign_in_url_substitution: '/signin',
      sign_out_url_substitution: '/signout',
      languages: [{ name: 'English', code: 'en-US' }],
      selected_language: { name: 'English', code: 'en-US' },
    },
    sitemarkers: siteData.siteMarkers,
    user,
    page: {
      id: page.id,
      adx_copy: content.copy,
      adx_title: content.title,
      copy: content.copy,
      title: content.title,
      name: page.name,
      url: page.partialUrl,
      breadcrumbs: [],
    },
    request: {
      path: url.pathname,
      params: Object.fromEntries(url.searchParams),
      url: url.href,
    },
    resx: DEFAULT_RESX,
  };
}

export { MOCK_USERS };
