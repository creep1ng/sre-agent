import sys,asyncio,json
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import test_incident_workflow_provisioning as t
from sre_agent.persistence.database import Database
import psycopg
t.provisioned_database.__wrapped__()
async def main():
 db=Database(t.DATABASE_URL);service=t.build_service(db,b'0'*32)
 print('Before provision:',await t._decision('run.start'))
 a=await t.provision(service,t.BEARER[0]);b=await t.provision(service,t.BEARER[0]);print('First:',json.dumps(asdict(a)));print('Replay:',json.dumps(asdict(b)))
 print('Revoke read status:',await t.revoke_run_read(service,t.BEARER[0]))
 for action in ['run.read','run.start','run.command','run.approve']:
  print('Human',action,await t._decision(action))
  if hasattr(t,'HARNESS'):print('Harness',action,await t._decision(action,t.HARNESS))
 await db.dispose()
asyncio.run(main())
with psycopg.connect(t.DATABASE_URL) as c:
 for row in c.execute("select principal_id, action, resource_type, resource_id, effect,status from grants where resource_type='incident_workflow' order by action"):
  print('SQL:',row)
