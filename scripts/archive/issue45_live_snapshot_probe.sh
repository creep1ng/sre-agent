#!/bin/bash
set -Eeuo pipefail
cd /opt/sre-agent
set -a; source .env; set +a
install -d -m 0700 /opt/issue45-private
python3 - <<'PY'
import importlib.util,json,os,urllib.error,urllib.request
spec=importlib.util.spec_from_file_location('provision','/opt/sre-agent/scripts/provision_incident_workflow.py')
module=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=module
spec.loader.exec_module(module)
base='http://127.0.0.1:18000'
def post(path,body,key):
 req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['ADMIN_HUMAN_API_KEY'],'Idempotency-Key':key,'Content-Type':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=10) as r: return r.status,None
 except urllib.error.HTTPError as e:
  payload=json.loads(e.read())
  return e.code,(payload.get('error') or {}).get('code')
catalog=post('/v1/catalog/resources',module.CATALOG_BODY,module.CATALOG_IDEMPOTENCY_KEY)
grant=post('/v1/grants',module.GRANT_BODY,module.GRANT_IDEMPOTENCY_KEY)
print(json.dumps({'catalog':catalog,'grant':grant}))
assert catalog[0]==201 and grant[0]==201
PY
cat > /opt/issue45-private/snapshot_seed.py <<'PY'
import asyncio,json,sys
from datetime import UTC,datetime
from sre_agent.incident.runtime import IncidentCommand,IncidentRuntime
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
import os
marker=sys.argv[1]
incident_id='inc-issue45-marker'
run_id='run_issue45marker01'
now=datetime.now(UTC)
state={
 'workflow_id':'incident-response','workflow_version':'1.0.0','state':'detected',
 'severity':None,'impact':None,
 'alert':{'alert_id':'alt-issue45-marker','service':'paymentservice','severity':'sev2','status':'new','observed_at':now.isoformat(),'summary':'Synthetic marker projection check.','source':'grafana-alerting'},
 'hypotheses':[],
 'evidence':[{'source':'controlled-mcp-error-marker','private_marker':marker}],
 'mitigation_strategy':None,'postmortem':None,'approvals':[],'updated_at':now.isoformat(),
}
run_state={'workflow_version':'1.0.0','current_state':'detected','status':'running'}
async def main():
 db=Database(os.environ['DATABASE_URL'])
 try:
  async with PostgresIncidentUnitOfWork(db) as work:
   if await work.incidents.get(incident_id) is None:
    await work.incidents.add(incident_id,state,now=now)
    await work.runs.add(run_id,incident_id,run_state,now=now)
  workflow=load_incident_workflow('/app/agent/workflows/incident-response.yaml')
  runtime=IncidentRuntime(workflow,lambda:PostgresIncidentUnitOfWork(db))
  result=await runtime.execute(IncidentCommand(command_id='cmd_issue45_marker_open',incident_id=incident_id,run_id=run_id,transition_id='open_triage',actor='system'))
  async with PostgresIncidentUnitOfWork(db) as work:
   snap=await work.snapshots.latest(run_id)
  report={'incident_id':incident_id,'run_id':run_id,'transition_replayed':result.replayed,'private_snapshot_present':snap is not None,'private_snapshot_marker_present':marker in json.dumps(snap.incident_state) if snap else False,'snapshot_version':snap.version if snap else None}
  print(json.dumps(report))
  assert snap is not None and marker in json.dumps(snap.incident_state)
 finally:
  await db.dispose()
asyncio.run(main())
PY
chmod 0600 /opt/issue45-private/snapshot_seed.py
marker=$(cat /opt/issue45-private/marker.txt)
docker exec -i issue45-gateway-api-1 python - "$marker" < /opt/issue45-private/snapshot_seed.py
python3 - <<'PY'
import json,os,urllib.error,urllib.request
from pathlib import Path
marker=Path('/opt/issue45-private/marker.txt').read_text().strip()
incident_id='inc-issue45-marker'
req=urllib.request.Request('http://127.0.0.1:18000/v1/incidents/'+incident_id+'/snapshot',headers={'Authorization':'Bearer '+os.environ['DEMO_HUMAN_API_KEY']})
try:
 with urllib.request.urlopen(req,timeout=10) as response: status=response.status; raw=response.read()
except urllib.error.HTTPError as error:
 status=error.code; raw=error.read()
obj=json.loads(raw)
report={'schema':'sre-agent.issue45.populated-public-snapshot/v1','status':status,'incident_id':incident_id,'snapshot_id':obj.get('snapshot_id'),'snapshot_version':obj.get('version'),'incident_state':(obj.get('incident') or {}).get('state'),'marker_in_public_snapshot':marker.encode() in raw,'has_populated_incident':isinstance(obj.get('incident'),dict),'has_populated_run':isinstance(obj.get('run'),dict),'public_keys':sorted(obj)}
Path('/opt/issue45-evidence/populated-public-snapshot.json').write_text(json.dumps(report)+'\n')
print(json.dumps(report))
assert status==200 and report['has_populated_incident'] and report['has_populated_run'] and report['snapshot_id'] and not report['marker_in_public_snapshot']
PY
