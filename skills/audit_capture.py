"""Observe HTTP status/correlation only; never record credentials or instructions."""
import json
import os
from pathlib import Path
from fastapi.testclient import TestClient

observations=[]
original=TestClient.request

def request(self, method, url, *args, **kwargs):
    response=original(self,method,url,*args,**kwargs)
    item={'method':method,'path':str(url).split('?')[0],'http':response.status_code}
    try:
        data=response.json()
        if isinstance(data,dict):
            for key in ('request_id','retryable','status','version','skill_id'):
                if key in data:
                    item[key]=data[key]
            if 'skill' in data:
                item['resolved_version']=data['skill']['version']
                item['dependency_count']=len(data.get('dependencies',[]))
            if 'error' in data:
                item['error_code']=data['error'].get('code')
    except ValueError:
        pass
    observations.append(item)
    return response

def pytest_configure(config):
    TestClient.request=request

def pytest_sessionfinish(session,exitstatus):
    TestClient.request=original
    Path(os.environ.get('EVIDENCE_OUT','/evidence'),'pr-'+os.environ['AUDIT_PR']+'-http.json').write_text(json.dumps({
        'pr':int(os.environ['AUDIT_PR']),'head':os.environ['AUDIT_HEAD'],
        'exitstatus':int(exitstatus),'evidence_kind':'controlled integration',
        'capture':'TestClient observation of real requests and PostgreSQL integration; no external service',
        'observations':observations},indent=2)+'\n')
