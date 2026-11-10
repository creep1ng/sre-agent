'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { run, validate } = require('../.github/governance/pr-evidence.cjs');

const sha = 'a'.repeat(40);
const tested = 'c'.repeat(40);
const screenshot = 'https://github.com/creep1ng/sre-agent/issues/183';
const noVideo = 'Not recorded; screenshot evidence is mandatory.';
const legacyNoVideo = 'Deferred: media storage unavailable; screenshot evidence is mandatory.';
const attachment = 'https://github.com/user-attachments/assets/5f3c1a2e-8b7d-4c6a-9e1f-0a2b3c4d5e6f';
const pasted = `<img width="1280" height="800" alt="Inbox at night" src="${attachment}" />`;

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
    Video: noVideo,
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
const crlf = data();
crlf.pr.body = crlf.pr.body.replace(/\n/g, '\r\n');
assert.deepEqual(validate(crlf), []);
assert.match(errors(data({ fields: { Video: 'Video pending.' } })), /Video must be an HTTPS reference/);
assert.match(errors(data({ fields: { Screenshot: 'Screenshot pending.' } })), /Screenshot requires a non-placeholder HTTPS reference/);
assert.deepEqual(validate(data({ fields: { 'Tested SHA': tested } })), []);
assert.deepEqual(validate(data({
  additions: 401,
})), []);
assert.match(errors(data({ additions: -1 })), /Size metadata is unavailable/);

// What GitHub inserts when a file is attached: an <img> tag for an image, a bare URL for a video.
assert.deepEqual(validate(data({ fields: { Screenshot: pasted, Video: attachment } })), []);
assert.deepEqual(validate(data({ fields: { Screenshot: `<img src="${attachment}">` } })), []);
assert.deepEqual(validate(data({ fields: { 'Acceptance evidence': `CA1: the inbox.\n\n${pasted}` } })), []);
assert.deepEqual(validate(data({ fields: { Video: legacyNoVideo } })), []);
for (const Screenshot of [
  '<your capture>',
  pasted.replace('https://', 'http://'),
  pasted.replace('github.com', 'example.org'),
  pasted.replace('github.com', 'github.com.example.org'),
  `<img src="https://github.com/creep1ng/sre-agent/blob/${sha}/shot.png">`,
  `${pasted} <your capture>`,
]) {
  assert.match(errors(data({ fields: { Screenshot } })), /Complete section: Screenshot/, Screenshot);
}
assert.match(errors(data({ fields: { Summary: 'Stamp <stamp> seeded.' } })), /Complete section: Summary/);
assert.deepEqual(validate(data({ fields: { 'Actual result': '<details>\n<summary>SQL</summary>\n\n1 row\n</details>' } })), []);
assert.match(errors(data({ fields: { 'Actual result': '<details open>\n1 row\n</details>' } })), /Complete section: Actual result/);
assert.match(errors(data({ fields: { 'Actual result': '<details>\n<the rows>\n</details>' } })), /Complete section: Actual result/);
assert.match(errors(data({ fields: { Summary: '<details>\n<summary></summary>\n</details>' } })), /Complete section: Summary/);

function context() {
  return {
    repo: { owner: 'owner', repo: 'repo' },
    serverUrl: 'https://github.com',
    runId: 42,
  };
}

function summary(headings = []) {
  return {
    addHeading(heading) { headings.push(heading); return this; },
    addRaw() { return this; },
    addList() { return this; },
    async write() {},
  };
}

function githubFor(pr, { snapshotError = null } = {}) {
  const statuses = [];
  let snapshots = 0;
  return {
    statuses,
    github: {
      paginate: async () => [{ number: pr.number, head: { sha: pr.head.sha } }],
      rest: {
        pulls: {
          get: async () => {
            snapshots++;
            if (snapshotError && snapshots === 1) throw snapshotError;
            return { data: pr };
          },
        },
        repos: {
          getCombinedStatusForRef: async () => ({ data: { statuses: [] } }),
          createCommitStatus: async status => {
            statuses.push(status);
            return { data: status };
          },
        },
      },
    },
  };
}

test('policy-invalid candidates publish failure without failing reconciliation', async () => {
  const candidate = data({ fields: { Video: 'Video pending.' } }).pr;
  const { github, statuses } = githubFor(candidate);
  const aggregateFailures = [];
  const headings = [];
  const core = {
    summary: summary(headings),
    setFailed: message => aggregateFailures.push(message),
    error: () => {},
  };

  await run({ github, context: context(), core });

  assert.deepEqual(aggregateFailures, []);
  assert.equal(statuses.length, 1);
  assert.equal(statuses[0].state, 'failure');
  assert.deepEqual(headings, ['PR #1: failure']);
});

test('operational errors fail reconciliation and publish an error status', async () => {
  const candidate = data().pr;
  const { github, statuses } = githubFor(candidate, { snapshotError: new Error('API unavailable') });
  const aggregateFailures = [];
  const core = {
    summary: summary(),
    setFailed: message => aggregateFailures.push(message),
    error: () => {},
  };

  await run({ github, context: context(), core });

  assert.equal(aggregateFailures.length, 1);
  assert.equal(statuses.length, 1);
  assert.equal(statuses[0].state, 'error');
});
