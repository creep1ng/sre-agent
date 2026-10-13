#!/bin/bash
set -Eeuo pipefail
cd /opt/sre-agent
set -a; source .env; set +a
install -d -m 0700 /opt/issue45-private
python3 - <<'PY'
import json,os,secrets,subprocess,urllib.error,urllib.request
from pathlib import Path
private=Path('/opt/issue45-private')
marker_path=private/'marker.txt'
marker=marker_path.read_text().strip() if marker_path.exists() else 'MCP45SYNTHETIC'+secrets.token_hex(12)
marker_path.write_text(marker)
marker_path.chmod(0o600)
base='http://127.0.0.1:18000/v1/mcp/tools/query_prometheus'
token=os.environ['DEMO_HUMAN_API_KEY']
def request(payload):
 data=json.dumps(payload).encode()
 req=urllib.request.Request(base,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=40) as response: status=response.status; body=response.read()
 except urllib.error.HTTPError as error:
  status=error.code; body=error.read()
 try: obj=json.loads(body)
 except ValueError: obj={}
 return {'http_status':status,'error_code':(obj.get('error') or {}).get('code'),'marker_in_public_response':marker.encode() in body}
validation=request({'datasource_uid':marker,'expr':'count(traces_span_metrics_calls_total)','query_type':'instant','end_time':'now'})
upstream=request({'datasource_uid':'webstore-metrics','expr':f'bad{{issue45_marker="{marker}"}}(','query_type':'instant','end_time':'now'})
def log_hit(name):
 out=subprocess.run(['docker','logs',name],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False).stdout
 return marker.encode() in out
logs={name:log_hit(name) for name in ['issue45-gateway-api-1','grafana-mcp','grafana','frontend-proxy']}
def table_hits(query):
 proc=subprocess.run(['docker','exec','issue45-gateway-db-1','psql','-U','sre_agent','-d','sre_agent','-Atc',query],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
 return sum(marker.encode() in row for row in proc.stdout.splitlines())
db={
 'audit_events':table_hits('select row_to_json(t) from audit_events t'),
 'incident_snapshots':table_hits('select row_to_json(t) from incident.snapshots t'),
 'incident_context':table_hits('select row_to_json(t) from incident.text_context t'),
 'incident_events':table_hits('select row_to_json(t) from incident.run_events t'),
}
evidence=Path('/opt/issue45-evidence')
evidence_hits=sum(marker.encode() in p.read_bytes() for p in evidence.iterdir() if p.is_file() and p.name!='marker-scan.json')
report={'schema':'sre-agent.issue45.marker-scan/v1','validation':validation,'upstream_error':upstream,'log_marker_present':logs,'db_marker_rows':db,'evidence_marker_files':evidence_hits,'surfaces_scanned':['public_responses','api_logs','mcp_logs','grafana_logs','proxy_logs','audit_events','incident_snapshots','incident_context','incident_events','evidence_directory']}
(evidence/'marker-scan.json').write_text(json.dumps(report)+'\n')
print(json.dumps(report))
PY
