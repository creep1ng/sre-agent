#!/bin/bash
set -Eeuo pipefail
cd /opt/sre-agent
export DEMO_STATE_DIR=/opt/sre-agent/.demo-state
set -a; source .env; set +a
trap 'docker start grafana-mcp >/dev/null 2>&1 || true' EXIT
docker stop grafana-mcp >/dev/null
python3 - <<'PY'
import json,os,urllib.error,urllib.request
from pathlib import Path
payload={'datasource_uid':'webstore-metrics','expr':'count(traces_span_metrics_calls_total)','query_type':'instant','end_time':'now'}
req=urllib.request.Request('http://127.0.0.1:18000/v1/mcp/tools/query_prometheus',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['DEMO_HUMAN_API_KEY'],'Content-Type':'application/json'},method='POST')
try:
 with urllib.request.urlopen(req,timeout=40) as r: status=r.status; raw=r.read()
except urllib.error.HTTPError as e: status=e.code; raw=e.read()
o=json.loads(raw)
secrets=[os.environ[x].encode() for x in ('DEMO_HUMAN_API_KEY','RESTRICTED_HARNESS_API_KEY')]
secrets.append(Path('/opt/sre-agent/.demo-state/grafana-mcp.env').read_text().split('=',1)[1].strip().encode())
report={'http_status':status,'error_code':o.get('error',{}).get('code'),'retryable':o.get('retryable'),'request_id':o.get('request_id'),'normalized_keys':sorted(o),'secret_present':any(s in raw for s in secrets),'raw_body_fields_present':any(k in o for k in ('body','result','content','traceback','stacktrace'))}
Path('/opt/issue45-evidence/unavailable.json').write_text(json.dumps(report)+'\n')
print(json.dumps(report))
assert status==503 and report['error_code']=='upstream_unavailable' and not report['secret_present'] and not report['raw_body_fields_present']
PY
docker start grafana-mcp >/dev/null
trap - EXIT
python3 scripts/demo_env.py verify >/var/log/issue45-after-unavailable-verify.log 2>&1
printf 'mcp_restored=verified\n'
