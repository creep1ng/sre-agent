import asyncio,sys,json,os
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import test_incident_run_start as t
import psycopg
from sre_agent.incident.runtime import IncidentRuntime,RunStart,ActorReference
from sre_agent.incident.persistence import IncidentIdempotencyConflictError
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.incident.workflow import load_incident_workflow
t.run_start_database.__wrapped__()
async def main():
 db=Database(t.DATABASE_URL);runtime=IncidentRuntime(load_incident_workflow('agent/workflows/incident-response.yaml'),lambda:PostgresIncidentUnitOfWork(db))
 async with PostgresIncidentUnitOfWork(db) as work:
  await work.incidents.add('inc-audit-atomic',t.incident_state('active'),now=t.NOW)
  await work.incidents.add('inc-audit-rollback',t.incident_state('active'),now=t.NOW)
 r=RunStart('audit-start-0001','inc-audit-atomic','investigate','human',ActorReference('demo-human'))
 a=await runtime.start_run(r); b=await runtime.start_run(r)
 print(json.dumps({'operation':'start + retry','same_run':a.run.run_id==b.run.run_id,'first_replayed':a.replayed,'retry_replayed':b.replayed,'run_version':a.run.version,'state':a.run.state['current_state']}))
 try: await runtime.start_run(RunStart('audit-start-0001','inc-audit-atomic','triage','human',ActorReference('demo-human')))
 except Exception as e:print('changed payload:',type(e).__name__)
 try: await runtime.start_run(RunStart('audit-start-0002','inc-audit-rollback','postmortem','human',ActorReference('demo-human')))
 except Exception as e:print('invalid state:',type(e).__name__)
 # New runtime/database object proves persisted replay rather than process-local state.
 await db.dispose();db2=Database(t.DATABASE_URL);fresh=IncidentRuntime(load_incident_workflow('agent/workflows/incident-response.yaml'),lambda:PostgresIncidentUnitOfWork(db2));view=await fresh.reconstruct('inc-audit-atomic',a.run.run_id)
 print(json.dumps({'fresh_runtime_reconstruction':view.run_state['current_state'],'run_version':view.run_version}));await db2.dispose()
asyncio.run(main())
with psycopg.connect(t.DATABASE_URL) as c:
 for row in c.execute("select i.incident_id,count(distinct r.run_id) as runs,count(distinct e.event_id) as events,count(distinct s.snapshot_id) as snapshots from incident.incidents i left join incident.runs r using(incident_id) left join incident.run_events e using(run_id) left join incident.snapshots s using(run_id) group by i.incident_id order by i.incident_id"):
  print('SQL persisted:',row)
