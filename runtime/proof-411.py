import sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import test_incident_run_http as t
from fastapi.testclient import TestClient
from sre_agent.incident.runtime import IncidentRuntime,IncidentCommand,ActorReference
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
t.authorized_database.__wrapped__()
client=TestClient(t.create_application(t.Settings(t.DATABASE_URL)),raise_server_exceptions=False)
url=f'/v1/incidents/{t.INCIDENT_ID}/runs'
headers={'Authorization':t.BEARERS['demo'],'Idempotency-Key':'audit-start-00001'}
for objective in [[],{}]:
 r=client.post(url,json={'workflow_version':'1.0.0','objective':objective},headers=headers);print(json.dumps({'objective_type':type(objective).__name__,'expected':422,'actual':r.status_code}))
for size in [128,129,200]:
 r=client.post(url,json=t._body(),headers={**headers,'Idempotency-Key':'k'*size}); print(json.dumps({'idempotency_key_length':size,'actual':r.status_code}));
 if size==128:run_id=r.json()['run_id']
async def advance():
 db=Database(t.DATABASE_URL);rt=IncidentRuntime(load_incident_workflow('agent/workflows/incident-response.yaml'),lambda:PostgresIncidentUnitOfWork(db));res=await rt.execute(IncidentCommand('audit-declare-01',t.INCIDENT_ID,run_id,'triage_declare','human',actor_reference=ActorReference('demo-human'),outcome='declare',inputs={'severity':'sev2'})); print(json.dumps({'persisted_current_state':res.run.state['current_state'],'latest_event_sequence':max(e.sequence for e in res.events)}));await db.dispose()
asyncio.run(advance())
r=client.post(url,json=t._body(resume_from_run_id=run_id),headers={**headers,'Idempotency-Key':'audit-resume-01'});print(json.dumps({'resume_status':r.status_code,'body':r.json()}))
