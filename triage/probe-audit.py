import os,json
from urllib.parse import urlparse
_review_database = urlparse(os.environ.get('TEST_DATABASE_URL', ''))
if (_review_database.hostname not in ('db', 'audit-triage-db-20260928')
        or _review_database.path != '/python_checks' or _review_database.username != 'audit'):
    raise RuntimeError('Refusing fixture setup outside the isolated review database')
import audit_fixture as t
print('Candidate:',os.environ['CANDIDATE_SHA'])
t.prepare_audit_http_database()
c=t._client();headers={'Authorization':t.BEARERS['admin']}
for path,auth in [('/v1/audit-events?decision=allow&limit=1',headers),('/v1/audit-events/'+t.DIGIT_EVENT_ID,headers),('/v1/audit-events?decision=deny',headers),('/v1/audit-events?decision=allow&content=x',headers),('/v1/audit-events?decision=allow',{'Authorization':t.BEARERS['bystander']})]:
 r=c.get(path,headers=auth);body=r.json()
 if 'items' in body:body={'items':[{'event_id':x['event_id'],'decision':x.get('policy_decision',{}).get('decision'),'response_status':x['response_status'],'latency_ms':x['latency_ms']} for x in body['items']],'limit':body['limit'],'truncated':body['truncated'],'contains_content':'redacted_content' in r.text}
 elif 'event_id' in body:body={k:v for k,v in body.items() if k in ['event_id','response_status','latency_ms','outcome']}
 print(path,'status=',r.status_code,'response=',json.dumps(body,sort_keys=True))
