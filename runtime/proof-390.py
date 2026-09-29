import asyncio,os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import test_openrouter_live as smoke
import httpx
from sre_agent.investigator.client import GatewayClient,GatewaySettings
from sre_agent.investigator.ports import GatewayError
URL=os.environ.get('INVESTIGATOR_AUDIT_URL','http://audit-runtime-live390-api:8000')
async def call(label,key,alias='triage-agent'):
 observed={}
 async def record(resp):
  await resp.aread()
  observed['status']=resp.status_code
  if resp.status_code==200:
   data=resp.json();smoke._contract_validator().validate(data)
   observed.update(request_id=data['request_id'],contract_valid=True,alias=data['metadata']['requested_model_alias'],provider=data['metadata']['inference_provider'],consumption=data['metadata']['consumption'])
  else:observed['error_code']=resp.json().get('error',{}).get('code')
 settings=GatewaySettings.from_environment({'INVESTIGATOR_GATEWAY_URL':URL,'INVESTIGATOR_GATEWAY_API_KEY':key,'INVESTIGATOR_MODEL_ALIAS':alias})
 # Harness client receives only its gateway key, URL and alias; provider key absent.
 client=GatewayClient(settings,httpx.AsyncClient(timeout=125,event_hooks={'response':[record]}))
 try:
  r=await client.respond(input='Return only the one word stable.',incident_id='inc-audit-gateway',run_id='run_audit00001',task_id='task_audit00001');observed['gateway_client_result']='completed';observed['output_chars']=len(r.text)
 except GatewayError as e:observed['gateway_client_result']=e.kind
 except Exception as e:observed['check_exception']=type(e).__name__
 finally:await client.aclose()
 print(json.dumps({'scenario':label,**observed}),flush=True)
 return observed
async def main():
 assert 'OPENROUTER_API_KEY' not in os.environ
 await call('permitted actual harness client',os.environ['INCIDENT_HARNESS_API_KEY'])
 await call('alias-only configuration change',os.environ['INCIDENT_HARNESS_API_KEY'],'remediation-agent')
 await call('principal without grant',os.environ['RESTRICTED_HARNESS_API_KEY'])
 async with httpx.AsyncClient(timeout=30) as http:
  h={'Authorization':'Bearer '+os.environ['ADMIN_HUMAN_API_KEY'],'Idempotency-Key':'audit390-ephemeral-01'}
  r=await http.post(URL+'/v1/principals/incident-harness/credentials',headers=h,json={})
  print(json.dumps({'scenario':'issue ephemeral credential','status':r.status_code}),flush=True)
  if r.status_code!=201:return
  d=r.json();key=d['key'];cid=d['credential']['credential_id']
  await call('ephemeral before revocation',key)
  r=await http.delete(URL+'/v1/credentials/'+cid,headers=h);print(json.dumps({'scenario':'revoke ephemeral credential','status':r.status_code}),flush=True)
  await call('ephemeral after revocation',key)
asyncio.run(main())
