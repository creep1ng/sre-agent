'use strict';

const assert = require('node:assert/strict');
const { validate } = require('../.github/governance/pr-evidence.cjs');

const sha = 'a'.repeat(40);
const tested = 'c'.repeat(40);
const screenshot = 'https://github.com/creep1ng/sre-agent/issues/183';
const deferredVideo = 'Deferred: media storage unavailable; screenshot evidence is mandatory.';
const repo = { owner: 'creep1ng', repo: 'sre-agent' };
const commentUrl = id => `https://github.com/${repo.owner}/${repo.repo}/issues/1#issuecomment-${id}`;

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

function data({ additions = 1, deletions = 1, prUser = 'author', comments = [], permissions = {}, files = [], fields = {}, labels = [] } = {}) {
  return {
    pr: {
      number: 1, body: body(fields), head: { sha }, base: { sha, ref: 'main' },
      additions, deletions, labels, user: { login: prUser }, draft: false,
    },
    comments, permissions, files,
  };
}

function confirmation({ id = 1, login = 'reviewer', type = 'User', body: text }) {
  return { id, user: { login, type }, body: text };
}

function errors(input) {
  return validate(input, repo).join('\n');
}

assert.deepEqual(validate(data(), repo), []);
assert.match(errors(data({ fields: { Video: 'Video pending.' } })), /Video must be an HTTPS reference/);
assert.match(errors(data({ fields: { Screenshot: 'Screenshot pending.' } })), /Screenshot requires a non-placeholder HTTPS reference/);

const evidenceCommand = `/accept-evidence ${sha} ${sha} ${tested}`;
for (const permission of ['admin', 'maintain']) {
  for (const prUser of [permission, 'author']) {
    assert.deepEqual(validate(data({
      prUser, fields: { 'Tested SHA': tested, 'Evidence freshness': commentUrl(1) },
      comments: [confirmation({ login: permission, body: evidenceCommand })],
      permissions: { [permission]: permission },
    }), repo), []);
  }
}
assert.deepEqual(validate(data({
  fields: { 'Tested SHA': tested, 'Evidence freshness': commentUrl(1) },
  comments: [confirmation({ body: evidenceCommand })], permissions: { reviewer: 'write' },
}), repo), []);
assert.match(errors(data({
  prUser: 'writer', fields: { 'Tested SHA': tested, 'Evidence freshness': commentUrl(1) },
  comments: [confirmation({ login: 'writer', body: evidenceCommand })], permissions: { writer: 'write' },
})), /Reused evidence needs linked eligible confirmation/);

const governanceCommand = `/approve-governance ${sha} ${sha}`;
for (const permission of ['admin', 'maintain']) {
  for (const prUser of [permission, 'author']) {
    assert.deepEqual(validate(data({
      prUser, files: ['docs/pr-evidence.md'], fields: { 'Governance review': commentUrl(1) },
      comments: [confirmation({ login: permission, body: governanceCommand })],
      permissions: { [permission]: permission },
    }), repo), []);
  }
}
assert.match(errors(data({
  files: ['docs/pr-evidence.md'], fields: { 'Governance review': commentUrl(1) },
  comments: [confirmation({ type: 'Bot', body: governanceCommand })], permissions: { reviewer: 'admin' },
})), /Governance changes need linked eligible confirmation/);
assert.match(errors(data({
  files: ['docs/pr-evidence.md'], fields: { 'Governance review': commentUrl(1) },
  comments: [confirmation({ body: governanceCommand })], permissions: { reviewer: 'read' },
})), /Governance changes need linked eligible confirmation/);
assert.match(errors(data({
  files: ['docs/pr-evidence.md'], fields: { 'Governance review': commentUrl(1) },
  comments: [confirmation({ body: `/approve-governance ${tested} ${sha}` })], permissions: { reviewer: 'admin' },
})), /Governance changes need linked eligible confirmation/);
assert.match(errors(data({
  files: ['docs/pr-evidence.md'],
  comments: [confirmation({ body: governanceCommand })], permissions: { reviewer: 'admin' },
})), /Governance changes need linked eligible confirmation/);
assert.match(errors(data({
  files: ['docs/pr-evidence.md'],
  fields: { 'Governance review': 'https://github.com/other/repo/issues/1#issuecomment-1' },
  comments: [confirmation({ body: governanceCommand })], permissions: { reviewer: 'admin' },
})), /Governance changes need linked eligible confirmation/);
assert.match(errors(data({
  files: ['docs/pr-evidence.md'], fields: { 'Governance review': commentUrl(1) },
  permissions: { reviewer: 'admin' },
})), /Governance changes need linked eligible confirmation/);

const sizeCommand = `/approve-size ${sha} ${sha}`;
assert.deepEqual(validate(data({
  additions: 401,
  fields: { 'Size exception': `This narrow change cannot be split safely. ${commentUrl(1)}` },
  comments: [confirmation({ body: sizeCommand })], permissions: { reviewer: 'maintain' },
  files: ['src/example.py'], labels: [{ name: 'size:exception' }],
}), repo), []);
assert.match(errors(data({
  additions: 401, prUser: 'reviewer',
  fields: { 'Size exception': `This narrow change cannot be split safely. ${commentUrl(1)}` },
  comments: [confirmation({ body: sizeCommand })], permissions: { reviewer: 'maintain' },
  files: ['src/example.py'], labels: [{ name: 'size:exception' }],
})), /Over 400 lines requires size:exception/);
