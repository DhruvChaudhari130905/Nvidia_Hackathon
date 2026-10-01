// Generates TypeScript types from the backend's JSON Schemas (packages/schema/generated) into src/types/generated
import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const schemaDir = fileURLToPath(new URL('../../packages/schema/generated/', import.meta.url));
const outDir = fileURLToPath(new URL('../src/types/generated/', import.meta.url));

const schemas = readdirSync(schemaDir).filter(f => f.endsWith('.json'));
if (!schemas.length) {
  console.error(`No JSON Schemas in ${schemaDir}.\nExport them from the backend first: cd mux/server && python scripts/export_schema.py`);
  process.exit(1);
}

const { status } = spawnSync('npx', ['json2ts', '-i', `${schemaDir}*.json`, '-o', outDir], { stdio: 'inherit' });
process.exit(status ?? 1);
