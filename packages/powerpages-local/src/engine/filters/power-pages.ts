/**
 * Power Pages-specific Liquid filters.
 *
 * These augment the built-in LiquidJS filter set with filters used
 * by Power Pages templates.
 */

/**
 * The `| boolean` filter. Coerces a value to a JavaScript boolean.
 * Power Pages treats 'true', 'True', '1', and boolean true as truthy.
 */
export function booleanFilter(v: unknown): boolean {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') {
    return v.toLowerCase() === 'true' || v === '1';
  }
  return Boolean(v);
}

/**
 * The `| xml_escape` filter. HTML/XML-escapes a string.
 */
export function xmlEscapeFilter(v: unknown): string {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * The `| h` filter. Alias for HTML escape (same as Liquid's built-in
 * `escape` but used explicitly in some Power Pages templates).
 */
export function hFilter(v: unknown): string {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
