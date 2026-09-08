'use strict';

const assert = require('node:assert/strict');
const { validate } = require('../.github/governance/pr-evidence.cjs');

const sha = 'a'.repeat(40);
const screenshot = 'https://github.com/creep1ng/sre-agent/issues/183';
const deferredVideo = 'Deferred: media storage unavailable; screenshot evidence is mandatory.';

function body(video = deferredVideo, image = screenshot) {
  return `## Related issues\nRefs #183\n\n## Summary\nTemporary evidence policy fixture.\n\n## Delivery route\ndirect\n\n## Acceptance evidence\n${screenshot}\n\n## Pending criteria\nNone; this fixture validates only metadata.\n\n## Environment\nDocker with synthetic local configuration.\n\n## Tested SHA\n${sha}\n\n## Base SHA\n${sha}\n\n## Reproduction commands\n\`\`\`sh\ndocker run --rm alpine:3.21 true\n\`\`\`\n\n## Expected result\nThe fixture passes structural validation.\n\n## Actual result\nThe fixture passed structural validation.\n\n## Video\n${video}\n\n## Screenshot\n${image}\n\n## Evidence kind\nrendered artifact\n\n## Evidence freshness\nTested SHA is the candidate SHA.\n\n## Risks and rollback\nRemove the temporary fixture.\n\n## Security\nSanitized: yes`;
}

function data(video, image) {
  return {
    pr: {
      number: 1, body: body(video, image), head: { sha }, base: { sha, ref: 'main' },
      additions: 1, deletions: 1, labels: [], user: { login: 'author' }, draft: false,
    },
    comments: [], permissions: {}, files: [],
  };
}

assert.deepEqual(validate(data(), { owner: 'creep1ng', repo: 'sre-agent' }), []);
assert.match(
  validate(data('Video pending.'), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Video must be an HTTPS reference or the documented storage deferral/,
);

assert.match(
  validate(data(deferredVideo, 'Screenshot pending.'), { owner: 'creep1ng', repo: 'sre-agent' }).join('\n'),
  /Screenshot requires a non-placeholder HTTPS reference/,
);
