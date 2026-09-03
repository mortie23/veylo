import * as fs from 'node:fs';
import * as path from 'node:path';
import { readTextFile, readYaml } from './yaml-utils.js';

/**
 * Load all content snippets from the content-snippets/ directory.
 * Returns a map: snippets['Snippet Name'] = 'html content'
 *
 * File structure:
 *   content-snippets/<dir-name>/<Name>.<locale>.contentsnippet.value.html
 *   content-snippets/<dir-name>/<Name>.<locale>.contentsnippet.yml
 *
 * The snippet name comes from the .yml file's adx_name field.
 */
export function loadContentSnippets(
  sitePath: string,
  locale: string = 'en-US',
): Record<string, string> {
  const snippetsDir = path.join(sitePath, 'content-snippets');
  if (!fs.existsSync(snippetsDir)) return {};

  const snippets: Record<string, string> = {};
  const dirs = fs.readdirSync(snippetsDir, { withFileTypes: true });

  for (const dir of dirs) {
    if (!dir.isDirectory()) continue;

    const dirPath = path.join(snippetsDir, dir.name);
    const files = fs.readdirSync(dirPath);

    // Find the locale-specific .yml to get the canonical name
    const ymlFile = files.find((f) =>
      f.endsWith(`.${locale}.contentsnippet.yml`),
    );
    if (!ymlFile) continue;

    const ymlData = readYaml<Record<string, unknown>>(
      path.join(dirPath, ymlFile),
    );
    const snippetName = String(ymlData?.adx_name ?? dir.name);

    // Find the corresponding .value.html
    const htmlFile = files.find((f) =>
      f.endsWith(`.${locale}.contentsnippet.value.html`),
    );
    if (!htmlFile) continue;

    snippets[snippetName] = readTextFile(path.join(dirPath, htmlFile));
  }

  return snippets;
}
