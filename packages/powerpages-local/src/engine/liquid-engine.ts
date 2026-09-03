import * as fs from 'node:fs';
import * as path from 'node:path';
import { Liquid } from 'liquidjs';
import type { WebTemplateRecord } from '../types.js';
import { EditableTag } from './tags/editable.js';
import { SubstitutionTag } from './tags/substitution.js';
import { booleanFilter, xmlEscapeFilter, hFilter } from './filters/power-pages.js';

/**
 * Custom LiquidJS file system that resolves {% include 'Template Name' %}
 * to local web template source files.
 *
 * Power Pages uses display names (e.g. "Header", "Page Copy") rather than
 * file paths in its include tags.
 */
class PowerPagesFileSystem {
  private nameIndex: Map<string, WebTemplateRecord>;

  constructor(nameIndex: Map<string, WebTemplateRecord>) {
    this.nameIndex = nameIndex;
  }

  sep = path.sep;

  dirname(filepath: string): string {
    return path.dirname(filepath);
  }

  resolve(root: string, file: string, ext: string): string {
    // LiquidJS calls resolve(root, file, ext).
    // The 'file' argument contains the evaluated template name (e.g. 'Page Copy').
    // First try the name index (display name lookup).
    const record = this.nameIndex.get(file);
    if (record) return record.sourcePath;

    // If the file is already an absolute path (from a previous resolve), return it
    if (path.isAbsolute(file) && fs.existsSync(file)) return file;

    throw new Error(`Web template not found: '${file}'`);
  }

  existsSync(filepath: string): boolean {
    return fs.existsSync(filepath);
  }

  readFileSync(filepath: string): string {
    return fs.readFileSync(filepath, 'utf-8');
  }

  async exists(filepath: string): Promise<boolean> {
    return this.existsSync(filepath);
  }

  async readFile(filepath: string): Promise<string> {
    return this.readFileSync(filepath);
  }

  contains(_root: string, _filepath: string): boolean {
    return true;
  }
}

/**
 * Create a configured LiquidJS engine with Power Pages extensions.
 *
 * @param templateNameIndex - Map of template display names to records
 *   (built by buildTemplateNameIndex from the web-templates loader)
 */
export function createLiquidEngine(
  templateNameIndex: Map<string, WebTemplateRecord>,
): Liquid {
  const ppFs = new PowerPagesFileSystem(templateNameIndex);

  const engine = new Liquid({
    fs: ppFs as any,
    dynamicPartials: true,
    strictFilters: false,
    strictVariables: false,
    lenientIf: true,
    jsTruthy: true,
  });

  // Register Power Pages custom tags
  engine.registerTag('editable', EditableTag as any);
  engine.registerTag('substitution', SubstitutionTag as any);

  // Register Power Pages custom filters
  engine.registerFilter('boolean', booleanFilter);
  engine.registerFilter('xml_escape', xmlEscapeFilter);
  engine.registerFilter('h', hFilter);

  return engine;
}
