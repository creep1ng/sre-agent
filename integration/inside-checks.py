"""Run reviewed checks inside the isolated Docker test container, never on the host."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psycopg

for _ in range(90):
    try:
        with psycopg.connect(os.environ['TEST_DATABASE_URL']):
            break
    except psycopg.OperationalError:
        time.sleep(0.5)
else:
    raise SystemExit('Isolated test database did not become ready')
mode = sys.argv[1]
if mode == 'focused':
    raise SystemExit(subprocess.call(['pytest', '-q', '-rs', '-p', 'no:cacheprovider', *sys.argv[2:]]))
commands = [
    ['python', 'scripts/assert_test_database_isolated.py'],
    ['shellcheck', 'docker/harness-entrypoint.sh', 'scripts/worktree-compose'],
    ['ruff', 'check', '--no-cache', '.'],
    ['ruff', 'format', '--check', '--no-cache', '.'],
    ['uv', 'lock', '--check', '--no-cache', '--offline'],
    ['lint-imports', '--no-cache'],
    ['mypy', '--cache-dir=/tmp/mypy', 'src/sre_agent/incident/commands.py', 'src/sre_agent/incident/persistence.py', 'src/sre_agent/incident/runtime.py', 'src/sre_agent/governance/dto.py', 'src/sre_agent/governance/authorization.py', 'src/sre_agent/investigator'],
    *[['python', f'scripts/{name}.py'] for name in ['validate_incident_contracts', 'validate_incident_authorization', 'validate_run_api', 'validate_incident_queries', 'validate_ci_hardening']],
    ['pytest', '-q', '-rs', '-p', 'no:cacheprovider'],
    ['alembic', 'upgrade', 'head'],
    ['alembic', 'check'],
]
results = []
for index, command in enumerate(commands, 1):
    logfile = f'final-check-{index:02d}.log'
    started = time.monotonic()
    with Path('/out', logfile).open('w') as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    item = {'command': command, 'exit_code': result.returncode, 'seconds': round(time.monotonic()-started, 2), 'log': logfile}
    results.append(item)
    Path('/out/final-checks.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(item), flush=True)
raise SystemExit(any(item['exit_code'] for item in results))
