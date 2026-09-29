import os
import subprocess
import time
import psycopg

for attempt in range(60):
    try:
        with psycopg.connect(os.environ['TEST_DATABASE_URL']):
            break
    except psycopg.OperationalError:
        time.sleep(0.5)
else:
    raise SystemExit('Isolated database did not become ready')
raise SystemExit(subprocess.call(['pytest', '-q', *os.environ['AUDIT_TESTS'].split()]))
