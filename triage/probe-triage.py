import os,json,asyncio,sys
from urllib.parse import urlparse
_review_database = urlparse(os.environ.get('TEST_DATABASE_URL', ''))
if (_review_database.hostname not in ('db', 'audit-triage-db-20260928')
        or _review_database.path != '/python_checks' or _review_database.username != 'audit'):
    raise RuntimeError('Refusing fixture setup outside the isolated review database')
import psycopg
print('Candidate',os.environ['CANDIDATE_SHA'])
if sys.argv[1]=='declare':
 import test_triage_declare as t
 t.triage_declare_database.__wrapped__()
 async def probe():
  first=await t._declare('al-review-duplicate','review-declare-first-1234')
  second=await t._declare('al-review-duplicate','review-declare-second-1234')
  print('First declaration:',json.dumps(first.__dict__ if hasattr(first,'__dict__') else {k:getattr(first,k) for k in first.__slots__}))
  print('Second declaration (same alert/version, fresh key):',json.dumps({k:getattr(second,k) for k in second.__slots__}))
  print('Incident count:',await t._count('incident.incidents'))
  assert first.incident_id != second.incident_id
 asyncio.run(probe())
else:
 import test_triage_http as t
 t.triage_http_database.__wrapped__()
 c=t._client()
 cases=[('reason_integer',{'operation':'triage_dismiss','expected_version':1,'reason':42}),('reason_list',{'operation':'triage_dismiss','expected_version':1,'reason':['reason']}),('severity_list',{'operation':'triage_declare','expected_version':1,'reason':'Controlled demo','severity':['sev2']}),('target_integer',{'operation':'triage_link','expected_version':1,'reason':'Controlled demo','target_incident_id':42}),('operation_list',{'operation':['open_triage'],'expected_version':1}),('missing_version',{'operation':'open_triage'})]
 for i,(name,body) in enumerate(cases):
  r=t._post(c,'al-review-validate',body,f'review-invalid-key-{i:03d}',t.BEARERS['op']);print(name,'request=',json.dumps(body),'status=',r.status_code,'response=',r.text)
 body={'operation':'triage_declare','expected_version':1,'reason':'Controlled demo','severity':'sev2'}
 for i in range(2):
  r=t._post(c,'al-review-double',body,f'review-double-key-{i:03d}',t.BEARERS['op']);print('declaration',i+1,'status=',r.status_code,'response=',r.text)
