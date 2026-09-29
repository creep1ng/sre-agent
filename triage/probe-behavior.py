import asyncio,json,os,sys
from urllib.parse import urlparse
_review_database = urlparse(os.environ.get('TEST_DATABASE_URL', ''))
if (_review_database.hostname not in ('db', 'audit-triage-db-20260928')
        or _review_database.path != '/python_checks' or _review_database.username != 'audit'):
    raise RuntimeError('Refusing fixture setup outside the isolated review database')
from dataclasses import asdict
print('Candidate:',os.environ['CANDIDATE_SHA'])
mode=sys.argv[1]
def show(label,value):print(label,json.dumps(value,default=str,sort_keys=True))
if mode=='store':
 import test_triage_store as t
 t.triage_store_database.__wrapped__()
 async def run():
  show('Created',await t._write(**t._base()))
  show('Dismissed',await t._write(**t._base(expected_version=1,status='dismissed',reason='Controlled false positive')))
  show('Stale expected_version=1',await t._write(**t._base(expected_version=1,status='open')))
 asyncio.run(run())
elif mode=='commands':
 import test_triage_commands as t
 t.triage_commands_database.__wrapped__()
 async def run():
  kwargs={'alert_id':'al-review-command','expected_version':1}
  show('Open',asdict(await t.SERVICE.execute(t._principal('op-human'),**kwargs,operation='open_triage',idempotency_key='review-open-key-001')))
  args={**kwargs,'operation':'triage_dismiss','reason':'Controlled false positive','idempotency_key':'review-dismiss-key-001'}
  show('Dismiss',asdict(await t.SERVICE.execute(t._principal('op-human'),**args)))
  show('Replay',asdict(await t.SERVICE.execute(t._principal('op-human'),**args)))
  try:await t.SERVICE.execute(t._principal('bystander-human'),**args)
  except t.TriageError as e:show('Unauthorized replay',{'status':e.http_status,'code':e.code})
 asyncio.run(run())
elif mode=='link':
 import test_triage_link as t
 t.triage_link_database.__wrapped__()
 async def run():
  for target,state in [('inc-review-open','active'),('inc-review-closed','closed')]:
   await t._add_incident(target,state)
   try:
    result=await t.SERVICE.execute(t._principal('op-human'),alert_id='al-'+target,operation='triage_link',expected_version=1,reason='Controlled related incident',target_incident_id=target,idempotency_key='review-'+target)
    show(target,asdict(result))
   except t.TriageError as e:show(target,{'status':e.http_status,'code':e.code})
 asyncio.run(run())
elif mode=='audit-query':
 import test_audit_filtered_query as t
 t.audit_database.__wrapped__()
 async def run():
  await t._seed()
  for label,filters in [('bounded allow',{'decision':'allow','limit':2}),('deny',{'decision':'deny'}),('missing trace',{'trace_digest':'0'*64})]:
   items,more=await t._query(**t.WINDOW,**filters);show(label,{'items':[{'event_id':str(x.event_id),'time':x.occurred_at,'decision':x.policy_decision.decision} for x in items],'has_more':more})
 asyncio.run(run())
elif mode=='restart':
 import test_incident_restart_reads as t
 import httpx
 t.prepare_authorized_database();port=t._free_port();headers={'Authorization':t.BEARERS['demo']};before_count=t._grant_count()
 server=t._start_server(port)
 try:before=t._reads(port,headers)
 finally:t._stop_server(server)
 server=t._start_server(port)
 try:
  after=t._reads(port,headers)
  with httpx.Client(base_url=f'http://127.0.0.1:{port}') as c:codes=[c.get(t.PATHS[0]).status_code,c.get(t.PATHS[0],headers={'Authorization':t.BEARERS['bystander']}).status_code]
 finally:t._stop_server(server)
 for name,obj in [('before',before),('after',after)]:
  show(name,{k:{x:v for x,v in body.items() if x in ['incident_id','version','state','snapshot_id','run_id']} for k,body in obj.items()})
 show('Restart assertions',{'identical':before==after,'anonymous':codes[0],'forbidden':codes[1],'grants_before':before_count,'grants_after':t._grant_count()})
