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
function fileReference(value) {
  return /(?:^|[\s`\[(])(?:\.?\/)?(?:[\w.-]+\/)*[\w.-]+\.(?:md|mdx|ya?ml|json|toml|txt|py|c?js|mjs|ts|tsx|jsx|html|css)(?:#[\w-]+)?(?=$|[\s`\])])/im.test(value || '');
}
function visualApplicability(value) {
  const declarations = [...clean(value || '').matchAll(/^Visual applicability:\s*(yes|no)\s*(?:—|--|-)\s*(.+)$/gim)];
  if (declarations.length !== 1) return null;
  const [, answer, declaredReason] = declarations[0];
  const applies = answer.toLowerCase() === 'yes';
  const reason = clean(declaredReason);
  if (reason.length < 12 || /^(?:n\/?a|none|not applicable)\.?$/i.test(reason) ||
      /\b(TODO|TBD|PLACEHOLDER)\b|<[^>]+>/i.test(reason)) return null;
  return { applies, reason };
}

async function snapshot(github, repo, number) {
  const { data: pr } = await github.rest.pulls.get({ ...repo, pull_number: number });
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...repo, issue_number: number, per_page: 100,
  });
  const files = await github.paginate(github.rest.pulls.listFiles, {
    ...repo, pull_number: number, per_page: 100,
  });
  // GitHub caps this endpoint at 3,000 files; an incomplete scope cannot pass.
  if (files.length !== pr.changed_files) throw new Error('Incomplete changed-file inventory');
  const permissions = {};
  for (const user of new Set(comments.filter(c => c.user?.type === 'User' &&
    /^\/(approve-size|accept-evidence|approve-governance) /.test(c.body || '')).map(c => c.user.login))) {
    const { data } = await github.rest.repos.getCollaboratorPermissionLevel({ ...repo, username: user });
    permissions[user] = data.role_name || data.permission;
  }
  return { pr, comments, files: files.map(f => f.filename), permissions };
}
function fingerprint(data) {
  const { pr, comments, files, permissions } = data;
  return hash([pr.state, pr.draft, pr.body, pr.head.sha, pr.base.sha, pr.base.ref,
    pr.additions, pr.deletions, pr.labels.map(l => l.name).sort(),
    comments.map(c => [c.id, c.body, c.user.login, c.user.type, c.updated_at]), files, permissions]);
}

function validate(data, repo) {
  const { pr, comments, permissions, files } = data;
  const errors = [];
  let fields;
  try { fields = parse(pr.body); } catch { return ['Duplicate section headings']; }
  for (const name of sections) {
    const value = fields[name] || '';
    if (name === 'Video') {
      if (!Object.hasOwn(fields, name)) errors.push(`Complete section: ${name}`);
      continue;
    }
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
  if (!reference(fields['Acceptance evidence']) && !fileReference(fields['Acceptance evidence'])) {
    errors.push('Acceptance evidence requires a non-placeholder HTTPS or repository-file reference');
  }
  const visual = visualApplicability(fields.Screenshot);
  if (!visual) {
    errors.push('Screenshot must declare visual applicability as yes or no with a reason');
  } else if (visual.applies && !reference(fields.Screenshot)) {
    errors.push('Visual evidence requires a non-placeholder HTTPS screenshot reference');
  }
  if (fields.Video && !reference(fields.Video)) {
    errors.push('Video must be empty or an HTTPS reference');
  }
  if (!/```(?:sh|bash|shell)\n[\s\S]*?\S[\s\S]*?\n```/.test(fields['Reproduction commands'] || '')) {
    errors.push('Reproduction commands require a nonempty sh/bash/shell code block');
  }
  if (fields.Security !== 'Sanitized: yes') errors.push('Security must declare Sanitized: yes');
  const tested = fields['Tested SHA'] || '';
  if (!/^[a-f0-9]{40}$/.test(tested)) errors.push('Tested SHA must be a full commit SHA');
  if (fields['Base SHA'] !== pr.base.sha) errors.push('Base SHA must match the current PR base commit');

  const approved = (field, command, sizeException = false) => {
    const text = fields[field] || '';
    return comments.some(comment => {
      const urls = ['issues', 'pull'].map(kind =>
        `https://github.com/${repo.owner}/${repo.repo}/${kind}/${pr.number}#issuecomment-${comment.id}`);
      return urls.some(url => links(text).includes(url)) && comment.user.type === 'User' &&
        (sizeException || comment.user.login !== pr.user.login) &&
        (sizeException ? ['admin', 'maintain'] : ['admin', 'maintain', 'write'])
          .includes(permissions[comment.user.login]) &&
        clean(comment.body || '') === command;
    });
  };
  if (tested !== pr.head.sha && !approved('Evidence freshness',
    `/accept-evidence ${pr.head.sha} ${pr.base.sha} ${tested}`)) {
    errors.push('Reused evidence needs linked independent reviewer acceptance for this head and base');
  }
  if (!Number.isInteger(pr.additions) || !Number.isInteger(pr.deletions) ||
      pr.additions < 0 || pr.deletions < 0) errors.push('Size metadata is unavailable');
  else if (pr.additions + pr.deletions > 400) {
    const rationale = clean(fields['Size exception'] || '').replace(/https:\/\/\S+/g, '').trim();
    if (!pr.labels.some(l => l.name === 'size:exception') || rationale.length < 30 ||
        /\b(TODO|TBD|PLACEHOLDER)\b|<[^>]+>/.test(rationale) ||
        !approved('Size exception', `/approve-size ${pr.head.sha} ${pr.base.sha}`, true)) {
      errors.push('Over 400 lines requires size:exception, rationale and linked maintainer approval');
    }
  }
  if (files.some(path => /^(\.github\/|\.agents\/|\.codex\/|\.atl\/|openspec\/config\.yaml$|AGENTS\.md$|\.importlinter$|compose(?:\.e2e)?\.yaml$|docker\/(?:api|web|harness|e2e)\.Dockerfile$|pyproject\.toml$|uv\.lock$|playwright\.production\.config\.js$|tests\/browser\/(?:api-seam|production-proxy)\.spec\.js$|scripts\/(validate_|assert_)|tests\/test_ci_hardening\.py$|docs\/(team-workflow|gentle-ai-profile|pr-evidence|governance-|ci-controls))/.test(path)) &&
      !approved('Governance review', `/approve-governance ${pr.head.sha} ${pr.base.sha}`)) {
    errors.push('Governance changes need linked independent reviewer approval in Governance review');
  }
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
      const description = `${identity}: ${errors.length ? 'Policy incomplete; see summary' : 'Structure/size checked; human acceptance required'}`;
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
