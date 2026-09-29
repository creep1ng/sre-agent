import os,json
from urllib.parse import urlparse
_review_database = urlparse(os.environ.get('TEST_DATABASE_URL', ''))
if (_review_database.hostname not in ('db', 'audit-triage-db-20260928')
        or _review_database.path != '/python_checks' or _review_database.username != 'audit'):
    raise RuntimeError('Refusing fixture setup outside the isolated review database')
from pathlib import Path
import test_triage_http as t
from fastapi.staticfiles import StaticFiles
import uvicorn
# Real candidate fixtures seed only this isolated review database.
t.triage_http_database.__wrapped__()
os.umask(0o077)
Path('/evidence/local-credential.json').write_text(json.dumps({'credential':t.BEARERS['op'].removeprefix('Bearer ')}))
app=t.create_application(t.Settings(t.DATABASE_URL))
app.mount('/public',StaticFiles(directory='/repo/public'),name='public')
app.mount('/styles',StaticFiles(directory='/repo/styles'),name='styles')
@app.middleware('http')
async def proxy(request,call_next):
 if request.scope['path'].startswith('/api/'):
  request.scope['path']=request.scope['path'][4:]
 return await call_next(request)
uvicorn.run(app,host='0.0.0.0',port=8100,log_level='warning')
