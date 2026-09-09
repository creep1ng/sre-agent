'use strict';

const assert = require('node:assert/strict');
const { validate } = require('../.github/governance/pr-evidence.cjs');

const sha = 'a'.repeat(40);
const screenshot = 'https://github.com/creep1ng/sre-agent/issues/183';
const visualScreenshot = `Visual applicability: yes — The changed UI surface is visible.\n${screenshot}`;
const nonvisualEvidence = 'Visual applicability: no — This backend-only authorization change has no visual surface.';

function body({
  video = '', visual = visualScreenshot, acceptanceEvidence = screenshot,
} = {}) {
  return `## Related issues\nRefs #183\n\n## Summary\nTemporary evidence policy fixture.\n\n## Delivery route\ndirect\n\n## Acceptance evidence\n${acceptanceEvidence}\n\n## Pending criteria\nNone; this fixture validates only metadata.\n\n## Environment\nDocker with synthetic local configuration.\n\n## Tested SHA\n${sha}\n\n## Base SHA\n${sha}\n\n## Reproduction commands\n\`\`\`sh\ndocker run --rm alpine:3.21 true\n\`\`\`\n\n## Expected result\nThe fixture passes structural validation.\n\n## Actual result\nThe fixture passed structural validation.\n\n## Video\n${video}\n\n## Screenshot\n${visual}\n\n## Evidence kind\nrendered artifact\n\n## Evidence freshness\nTested SHA is the candidate SHA.\n\n## Risks and rollback\nRemove the temporary fixture.\n\n## Security\nSanitized: yes`;
}

function data(options) {
  return {
    pr: {
      number: 1, body: body(options), head: { sha }, base: { sha, ref: 'main' },
      additions: 1, deletions: 1, labels: [], user: { login: 'author' }, draft: false,
    },
    comments: [], permissions: {}, files: [],
  };
}

assert.deepEqual(validate(data(), { owner: 'creep1ng', repo: 'sre-agent' }), []);
assert.deepEqual(validate(data({
  visual: nonvisualEvidence,
  acceptanceEvidence: 'docs/pr-evidence.md',
}), { owner: 'creep1ng', repo: 'sre-agent' }), []);
for (const acceptanceEvidence of [
  'docs/pr-evidence.md',
  'tests/test_authorization.py',
  'src/sre_agent/control/service.py',
]) {
  assert.deepEqual(validate(data({
    visual: nonvisualEvidence,
    acceptanceEvidence,
  }), { owner: 'creep1ng', repo: 'sre-agent' }), []);
}
assert.match(
  validate(data({ video: 'Video pending.' }), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Video must be empty or an HTTPS reference/,
);

assert.match(
  validate(data({ visual: 'Visual applicability: yes — The UI changed.' }), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Visual evidence requires a non-placeholder HTTPS screenshot reference/,
);
assert.match(
  validate(data({ visual: 'Screenshot pending.' }), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Screenshot must declare visual applicability as yes or no with a reason/,
);
assert.match(
  validate(data({ visual: 'Visual applicability: no — N/A' }), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Screenshot must declare visual applicability as yes or no with a reason/,
);
assert.match(
  validate(data({
    visual: `${visualScreenshot}\nVisual applicability: no — The backend has no visual surface.`,
  }), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Screenshot must declare visual applicability as yes or no with a reason/,
);
assert.match(
  validate(data({
    visual: nonvisualEvidence,
    acceptanceEvidence: 'Evidence pending.',
  }), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Acceptance evidence requires a non-placeholder HTTPS or repository-file reference/,
);
