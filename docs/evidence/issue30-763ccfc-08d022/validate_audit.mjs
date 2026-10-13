import { readFile, writeFile } from 'node:fs/promises';
import { createSchemaRegistry, loadReleaseDirectory } from '/workspace/schemas/tooling/lib/schema-validation.mjs';
const version = process.env.SRE_AGENT_CONTRACT_VERSION || '2.7.0';
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Invalid contract release');
const { schemas } = await loadReleaseDirectory(`/workspace/schemas/releases/${version}`, 'all');
const validate = createSchemaRegistry(schemas).getSchema(`urn:sre-agent:schema:audit-event:${version}`);
const input = (await readFile('/capture/audit-events-full.jsonl', 'utf8')).trim();
const events = input ? input.split('\n').map(line => JSON.parse(line)) : [];
const results = events.map(event => {
  const valid = validate(event);
  return { event_id: event.event_id, request_id: event.correlation.request_id,
    response_status: event.response_status, stage: event.stage,
    validation: valid ? 'passed' : 'failed', errors: valid ? [] : structuredClone(validate.errors) };
});
await writeFile('/capture/audit-ajv-schema-results.jsonl', results.map(result => JSON.stringify(result)).join('\n') + '\n');
console.log(JSON.stringify({ validator: 'repository Ajv2020 + formats', rows: results.length,
  passed: results.filter(result => result.validation === 'passed').length,
  failed: results.filter(result => result.validation === 'failed').length,
  evidence_missing: events.length === 0 }));
if (!events.length || results.some(result => result.validation === 'failed')) process.exitCode = 1;
