"""Reconstruct and compare prospective trees in a disposable clone, not a delivery branch."""
import json
import os
from pathlib import Path
import subprocess

summary = json.loads(Path('/evidence/integration-summary.json').read_text())
env = dict(os.environ, GIT_AUTHOR_NAME='Integration Verification', GIT_AUTHOR_EMAIL='verification@example.invalid', GIT_COMMITTER_NAME='Integration Verification', GIT_COMMITTER_EMAIL='verification@example.invalid', GIT_AUTHOR_DATE='2026-09-29T04:00:00Z', GIT_COMMITTER_DATE='2026-09-29T04:00:00Z')
def git(*args, stdin=None):
    return subprocess.check_output(['git', '-c', 'safe.directory=/repo', *args], text=True, input=stdin, env=env).strip()
if git('status','--porcelain'):
    raise SystemExit('Use a clean, disposable source clone')
parent = summary['starting_main']
for step in summary['steps']:
    actual = git('merge-tree','--write-tree',parent,step['head']).splitlines()[0]
    if actual != step['tree']:
        raise SystemExit(f"PR {step['pr']}: expected tree {step['tree']}, got {actual}; stop")
    parent = git('commit-tree',actual,'-p',parent,'-p',step['head'],stdin=f"chore: verify prospective PR {step['pr']} integration\n")
    print(f"PR {step['pr']}: tree {actual}; local synthetic commit {parent}")
git('checkout','--detach',parent)
print('Exact final prospective source selected; no branch was updated')
