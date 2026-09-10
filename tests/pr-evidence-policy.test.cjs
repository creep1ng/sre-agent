'use strict';

const assert = require('node:assert/strict');
const { validate } = require('../.github/governance/pr-evidence.cjs');

const sha = 'a'.repeat(40);
const tested = 'c'.repeat(40);
const screenshot = 'https://github.com/creep1ng/sre-agent/issues/183';
const deferredVideo = 'Deferred: media storage unavailable; screenshot evidence is mandatory.';

function body(overrides = {}) {
  const fields = {
    'Related issues': 'Refs #183',
    Summary: 'Temporary evidence policy fixture.',
    'Delivery route': 'direct',
    'Acceptance evidence': screenshot,
    'Pending criteria': 'None; this fixture validates only metadata.',
    Environment: 'Docker with synthetic local configuration.',
    'Tested SHA': sha,
    'Base SHA': sha,
    'Reproduction commands': '```sh\ndocker run --rm alpine:3.21 true\n```',
    'Expected result': 'The fixture passes structural validation.',
    'Actual result': 'The fixture passed structural validation.',
    Video: deferredVideo,
    Screenshot: screenshot,
    'Evidence kind': 'rendered artifact',
    'Evidence freshness': 'Tested SHA is the candidate SHA.',
    'Risks and rollback': 'Remove the temporary fixture.',
    Security: 'Sanitized: yes',
    ...overrides,
  };
  return Object.entries(fields).map(([name, value]) => `## ${name}\n${value}`).join('\n\n');
}

function data({ additions = 1, deletions = 1, fields = {} } = {}) {
  return {
    pr: {
      number: 1, body: body(fields), head: { sha }, base: { sha, ref: 'main' },
      additions, deletions, draft: false,
    },
  };
}

function errors(input) {
  return validate(input).join('\n');
}

assert.deepEqual(validate(data()), []);
assert.match(errors(data({ fields: { Video: 'Video pending.' } })), /Video must be an HTTPS reference/);
assert.match(errors(data({ fields: { Screenshot: 'Screenshot pending.' } })), /Screenshot requires a non-placeholder HTTPS reference/);
assert.deepEqual(validate(data({ fields: { 'Tested SHA': tested } })), []);
assert.deepEqual(validate(data({
  additions: 401,
})), []);
assert.match(errors(data({ additions: -1 })), /Size metadata is unavailable/);
