// Loaded only from the default branch by the metadata workflow, never from a PR.
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');

const sections = [
  'Related issues', 'Summary', 'Delivery route', 'Acceptance evidence',
  'Pending criteria', 'Environment', 'Tested SHA', 'Base SHA',
  'Reproduction commands', 'Expected result', 'Actual result', 'Video',
  'Screenshot', 'Evidence kind', 'Evidence freshness', 'Risks and rollback', 'Security',
];
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const videoDeferral = 'Deferred: media storage unavailable; screenshot evidence is mandatory.';
const clean = value => value.replace(/<!--[\s\S]*?-->/g, '').trim();
function parse(body) {
  const result = {};
  for (const match of clean(body || '').matchAll(/^## ([^\n]+)\n([\s\S]*?)(?=^## |$(?![\s\S]))/gm)) {
    if (Object.hasOwn(result, match[1])) throw new Error('Duplicate PR section');
    result[match[1]] = clean(match[2]);
  }
  return result;
}
function links(value) {
  return (value || '').match(/https:\/\/[^\s<>\)\]]+/g) || [];
}
function reference(value) {
  return links(value).some(link => {
    try {
      const url = new URL(link);
      return !url.username && !url.password && url.hostname.includes('.') &&
        !/^(example\.(com|org|net)|localhost)$/i.test(url.hostname);
    } catch { return false; }
  });
}

async function snapshot(github, repo, number) {
  const { data: pr } = await github.rest.pulls.get({ ...repo, pull_number: number });
  return { pr };
}
function fingerprint(data) {
  const { pr } = data;
  return hash([pr.state, pr.draft, pr.body, pr.head.sha, pr.base.sha, pr.base.ref,
    pr.additions, pr.deletions]);
}

function validate(data) {
  const { pr } = data;
  const errors = [];
  let fields;
  try { fields = parse(pr.body); } catch { return ['Duplicate section headings']; }
  for (const name of sections) {
    const value = fields[name] || '';
    if (!value || /\b(TODO|TBD|PLACEHOLDER)\b|<[^>]+>|^\s*(?:[-*] )?(?:\.\.\.|…|\[ \])\s*$/im.test(value)) {
      errors.push(`Complete section: ${name}`);
    }
  }
  if (!/\b(?:Refs|Closes|Fixes|Resolves)\s+#\d+\b/i.test(fields['Related issues'] || '')) {
    errors.push('Related issues must reference an issue number');
  }
  if (!/^(direct|sdd)$/i.test(fields['Delivery route'] || '')) errors.push('Delivery route must be direct or sdd');
  if (fields['Delivery route']?.toLowerCase() === 'sdd' &&
      !/openspec\/(?:changes|specs)\//.test(fields['Acceptance evidence'] || '')) {
    errors.push('SDD requires a shared OpenSpec path in Acceptance evidence');
  }
  if (!/^(mock|controlled integration|real external service|rendered artifact)$/i.test(fields['Evidence kind'] || '')) {
    errors.push('Declare the documented evidence kind');
  }
  for (const name of ['Screenshot', 'Acceptance evidence']) {
    if (!reference(fields[name])) errors.push(`${name} requires a non-placeholder HTTPS reference`);
  }
  if (!reference(fields.Video) && fields.Video !== videoDeferral) {
    errors.push('Video must be an HTTPS reference or the documented storage deferral');
  }
  if (!/```(?:sh|bash|shell)\n[\s\S]*?\S[\s\S]*?\n```/.test(fields['Reproduction commands'] || '')) {
    errors.push('Reproduction commands require a nonempty sh/bash/shell code block');
  }
  if (fields.Security !== 'Sanitized: yes') errors.push('Security must declare Sanitized: yes');
  const tested = fields['Tested SHA'] || '';
  if (!/^[a-f0-9]{40}$/.test(tested)) errors.push('Tested SHA must be a full commit SHA');
  if (fields['Base SHA'] !== pr.base.sha) errors.push('Base SHA must match the current PR base commit');

  if (!Number.isInteger(pr.additions) || !Number.isInteger(pr.deletions) ||
      pr.additions < 0 || pr.deletions < 0) errors.push('Size metadata is unavailable');
  return errors;
}

// Metadata is data only: no shell execution, URL fetching or PR checkout.
async function run({ github, context, core }) {
  const repo = context.repo;
  const open = await github.paginate(github.rest.pulls.list, { ...repo, state: 'open', per_page: 100 });
  const target_url = `${context.serverUrl}/${repo.owner}/${repo.repo}/actions/runs/${context.runId}`;
  let failures = 0;
  for (const item of open) {
    const sha = item.head.sha;
    const status = (state, description) => github.rest.repos.createCommitStatus({
      ...repo, sha, state, description, context: 'pr-governance', target_url,
    });
    try {
      const data = await snapshot(github, repo, item.number);
      const errors = validate(data, repo);
      if (data.pr.draft) errors.push('Draft PR is not submitted for acceptance');
      if (open.filter(other => other.head.sha === sha).length !== 1) {
        errors.push('Multiple open PRs share this SHA; a commit status cannot distinguish them');
      }
      const fresh = await snapshot(github, repo, item.number);
      if (data.pr.head.sha !== sha || fresh.pr.state !== 'open' || fingerprint(data) !== fingerprint(fresh)) {
        errors.push('Metadata changed during validation; wait for the next reconciliation');
      }
      const state = errors.length ? 'failure' : 'success';
      const identity = hash([fingerprint(fresh), errors, readFileSync(__filename, 'utf8')]).slice(0, 32);
      const description = `${identity}: ${errors.length ? 'Policy incomplete; see summary' : 'Structure checked; human acceptance required'}`;
      const { data: combined } = await github.rest.repos.getCombinedStatusForRef({ ...repo, ref: sha });
      const previous = combined.statuses.find(entry => entry.context === 'pr-governance');
      // Reconcile reads on every event, but do not exhaust GitHub's per-SHA status
      // limit by appending identical results to long-lived PRs every 15 minutes.
      if (previous?.state !== state || previous?.description !== description) {
        await status(state, description);
      }
      // Never print the PR body, command text, exception comments or attachment URLs.
      await core.summary.addHeading(`PR #${item.number}: ${state}`, 3)
        .addRaw(`Candidate: ${sha}\n\n`).addList(errors.length ? errors : ['Structural checks passed.']).write();
      if (errors.length) failures++;
    } catch {
      failures++;
      await status('error', 'Metadata unavailable; retry reconciliation, do not bypass');
      core.error(`PR #${item.number}: metadata could not be validated`);
    }
  }
  if (failures) core.setFailed(`${failures} open PR(s) do not meet the governance policy`);
}
module.exports = { parse, validate, fingerprint, run };
