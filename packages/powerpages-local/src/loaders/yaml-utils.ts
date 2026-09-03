import * as fs from 'node:fs';
import * as yaml from 'js-yaml';

/**
 * Read and parse a YAML file. Returns the parsed value or `null` if the file
 * does not exist.
 */
export function readYaml<T = unknown>(filePath: string): T | null {
  if (!fs.existsSync(filePath)) return null;
  const content = fs.readFileSync(filePath, 'utf-8');
  return yaml.load(content) as T;
}

/**
 * Safely read a file as UTF-8 text. Returns empty string if the file
 * does not exist.
 */
export function readTextFile(filePath: string): string {
  if (!fs.existsSync(filePath)) return '';
  return fs.readFileSync(filePath, 'utf-8');
}
