import os
from urllib.parse import urlparse
_review_database = urlparse(os.environ.get('TEST_DATABASE_URL', ''))
if (_review_database.hostname not in ('db', 'audit-triage-db-20260928')
        or _review_database.path != '/python_checks' or _review_database.username != 'audit'):
    raise RuntimeError('Refusing fixture setup outside the isolated review database')
import json,asyncio
from pathlib import Path
import audit_fixture as t
from fastapi.staticfiles import StaticFiles
import uvicorn
t.prepare_audit_http_database()
async def seed_routing():
 database=t.Database(t.DATABASE_URL)
 async with database.transaction() as session:
  raw=t.make_event(105,hours=5).model_dump();raw['routing']={'router':'openrouter','model_ref':t._ref('model','controlled-model'),'provider_ref':t._ref('provider','controlled-provider')}
  await t.AuditRepository(session).append(t.AuditEvent.model_validate(raw))
 await database.dispose()
asyncio.run(seed_routing())
os.umask(0o077)
Path('/evidence/local-credential.json').write_text(json.dumps({'credential':t.BEARERS['admin'].removeprefix('Bearer ')}))
app=t.create_application(t.Settings(t.DATABASE_URL,None,30.0,t.HMAC_KEY.decode()))
app.mount('/public',StaticFiles(directory='/repo/public'),name='public')
app.mount('/styles',StaticFiles(directory='/repo/styles'),name='styles')
@app.middleware('http')
async def proxy(request,call_next):
 if request.scope['path'].startswith('/api/'):request.scope['path']=request.scope['path'][4:]
 return await call_next(request)
uvicorn.run(app,host='0.0.0.0',port=8100,log_level='warning')
