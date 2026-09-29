"""Read-only candidate audit; writes only isolated database and evidence output."""
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
from unittest.mock import patch
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

PR = int(os.environ['AUDIT_PR'])
URL = os.environ['TEST_DATABASE_URL']
assert URL == 'postgresql://python_checks@127.0.0.1:5432/python_checks'
ADMIN = 'sre_admn_0123456789abcdefghijklmnop'
INCIDENT = 'sre_inci_0123456789abcdefghijklmnop'
RESTRICTED = 'sre_rest_0123456789abcdefghijklmnop'
ENV = dict(ADMIN_HUMAN_API_KEY=ADMIN, DEMO_HUMAN_API_KEY='sre_demo_0123456789abcdefghijklmnop',
           INCIDENT_HARNESS_API_KEY=INCIDENT, RESTRICTED_HARNESS_API_KEY=RESTRICTED,
           TRIAGE_AGENT_MODEL='openai/gpt-4o-mini', TRIAGE_AGENT_PROVIDER='openai',
           REMEDIATION_AGENT_MODEL='anthropic/claude-3.5-haiku', REMEDIATION_AGENT_PROVIDER='anthropic')
AUDIT_KEY = 'local-synthetic-skill-audit-only'
result = {'pr': PR, 'head': os.environ['AUDIT_HEAD'], 'evidence_kind':'controlled integration',
          'environment':'FastAPI TestClient + real PostgreSQL 17.4 in isolated network-none Docker container',
          'observations': []}

def record(name, **values):
    item = dict(scenario=name, **values)
    result['observations'].append(item)
    print(json.dumps(item, default=str), flush=True)

def query(sql, params=()):
    with psycopg.connect(URL) as conn:
        cursor=conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else []

with psycopg.connect(URL, autocommit=True) as conn:
    assert conn.execute('SELECT current_database()').fetchone()[0] == 'python_checks'
    conn.execute('DROP SCHEMA IF EXISTS incident CASCADE')
    conn.execute('DROP SCHEMA public CASCADE')
    conn.execute('CREATE SCHEMA public')
config = Config('alembic.ini')
config.set_main_option('sqlalchemy.url', URL)
command.upgrade(config, 'head')

async def bootstrap():
    db = Database(URL)
    try:
        await seed(db, SeedSettings.from_environment(ENV))
    finally:
        await db.dispose()
asyncio.run(bootstrap())

def headers(key=ADMIN, idem=None):
    value = {'Authorization': f'Bearer {key}'}
    if idem:
        value['Idempotency-Key'] = idem
    return value

def body(skill='audit-review-root', version='1.0.0', dependencies=None):
    return dict(skill_id=skill, version=version, owner_id='demo-human', manifest=dict(
        display_name='Controlled audit Skill', description='Synthetic local review example.',
        instructions='Use supplied evidence only.', dependencies=dependencies or []))

app = create_application(Settings(URL, audit_hmac_key=AUDIT_KEY))
with TestClient(app, raise_server_exceptions=False) as client:
    if PR in (387, 388):
        from sre_agent.governance.dto import SkillManifest
        from sre_agent.persistence.repositories import SkillVersionRepository
        async def repository_roundtrip():
            db = Database(URL)
            try:
                async with db.transaction() as session:
                    repo = SkillVersionRepository(session)
                    args=dict(skill_id='audit-review-root', version='1.0.0', owner_id='demo-human',
                              manifest=SkillManifest.model_validate(body()['manifest']), content_sha256='a'*64)
                    first = await repo.publish(**args)
                    again = await repo.publish(**args)
                    record('repository immutable replay', same_record=first == again)
            finally:
                await db.dispose()
        asyncio.run(repository_roundtrip())
        record('SQL persisted immutable version', rows=query('SELECT skill_id, version, owner_id FROM skill_versions'))
        if PR == 388:
            for key, label in ((ADMIN,'authorized'),(RESTRICTED,'restricted')):
                response=client.get('/v1/skills/audit-review-root/1.0.0', headers=headers(key))
                record('administrative GET '+label, http=response.status_code,
                       version=response.json().get('version'), has_manifest='manifest' in response.json())
    else:
        first=client.post('/v1/skills/versions', json=body(), headers=headers(idem='review-publication-0001'))
        replay=client.post('/v1/skills/versions', json=body(), headers=headers(idem='review-publication-0002'))
        record('publication and replay', http=[first.status_code,replay.status_code], identical=first.json()==replay.json())
        if PR in (397,409):
            response=client.post('/v1/skills/versions', json=body('audit-long-version','1'*33+'.0.0'), headers=headers(idem='review-long-version-0001'))
            record('overlong version', version_length=37, expected_http=422, actual_http=response.status_code,
                   rows=query("SELECT count(*) FROM skill_versions WHERE skill_id='audit-long-version'")[0][0])
        if PR in (403,404):
            response=client.get('/health/ready')
            record('readiness at migration head', http=response.status_code,
                   database_revision=query('SELECT version_num FROM alembic_version')[0][0])
        if PR in (402,409):
            response=client.put('/v1/skills/audit-missing-version/1.0.0/status', json=dict(status='active',expected_updated_at='2026-09-01T00:00:00Z'), headers=headers())
            record('unpublished exact-version lifecycle', expected_http=404, actual_http=response.status_code)
            from sre_agent.gateway.responses import PostgresAuditStore
            async def fail_append(*args, **kwargs):
                raise RuntimeError('controlled local audit outage')
            timestamp=first.json()['created_at']
            with patch.object(PostgresAuditStore, 'append', fail_append):
                response=client.put('/v1/skills/audit-review-root/1.0.0/status', json=dict(status='inactive',expected_updated_at=timestamp), headers=headers())
            record('lifecycle audit outage', injection='PostgresAuditStore.append raises; real SQL mutation remains unchanged',
                   http=response.status_code, expected_persisted_status='published',
                   actual_persisted_status=query("SELECT status FROM resources WHERE resource_id='audit-review-root@1.0.0'")[0][0],
                   terminal_audit_rows=query("SELECT count(*) FROM audit_events WHERE operation='catalog.status.replace'")[0][0])
            response=client.put('/v1/skills/audit-review-root/1.0.0/status', json=dict(status='inactive',expected_updated_at=timestamp), headers=headers())
            record('retry after failed audit', actual_http=response.status_code, expected='successful retry or no previous mutation')
        if PR in (404,409):
            from sre_agent.gateway.audit import AuditProjector
            from sre_agent.governance.dto import AuditEvent, PolicyDecision, Principal, PrincipalContext
            now=datetime.now(UTC)
            context=PrincipalContext(principal=Principal(principal_id='incident-harness',kind='agent',display_name='Audit',status='active',created_at=now,updated_at=now),credential_id='credential-review',authenticated_at=now)
            event=AuditProjector(AUDIT_KEY.encode()).control_event(uuid4(),200,1,'authorization',operation='skills.resolve',action='invoke',context=context,resource_ref=('skill','audit-review-root@1.0.0'),decision=PolicyDecision(decision='allow',reason_code='grant_matched',policy_id='grant-review'))
            raw=event.model_dump(mode='json')
            raw['consumption']=dict(availability='partial',source='openrouter',input_tokens=1,output_tokens=None,total_tokens=None,billed_usd=None,currency=None,precision=None,pricing_context=None)
            try:
                invalid=AuditEvent.model_validate_json(json.dumps(raw))
                from sre_agent.persistence.repositories import AuditRepository
                async def persist():
                    db=Database(URL)
                    try:
                        async with db.transaction() as session:
                            await AuditRepository(session).append(invalid)
                    finally:
                        await db.dispose()
                asyncio.run(persist())
                record('non-LLM consumption exclusion', expected='rejected', dto='accepted', sql=query("SELECT operation, consumption->>'input_tokens' FROM audit_events WHERE event_id=%s",(str(invalid.event_id),)))
            except ValidationError:
                record('non-LLM consumption exclusion', expected='rejected', dto='rejected')
        if PR in (405,406,409):
            query("UPDATE resources SET status='active' WHERE resource_id='audit-review-root@1.0.0'")
            query("INSERT INTO grants (grant_id,principal_id,action,resource_type,resource_id,effect,status,created_at) VALUES ('grant-audit-review','incident-harness','invoke','skill','audit-review-root@1.0.0','allow','active',now())")
            route='/v1/skills/audit-review-root/1.0.0/resolve'
            response=client.get(route,headers=headers(INCIDENT))
            from sre_agent.gateway.skills import SkillResolutionResponse
            try:
                SkillResolutionResponse.model_validate_json(response.text)
                valid=True
            except ValidationError:
                valid=False
            record('success response contract', http=response.status_code, public_keys=list(response.json()), declared_model_valid=valid,
                   request_id=response.json().get('request_id'))
            req_id=str(uuid4())
            response=client.get('/v1/skills/INVALID/1.0.0/resolve',headers={**headers(INCIDENT),'X-Request-ID':req_id})
            record('invalid resolution path', http=response.status_code, request_id_in_body=response.json().get('request_id'),
                   audit_rows=query("SELECT count(*) FROM audit_events WHERE correlation->>'request_id'=%s",(req_id,))[0][0])
            response=client.get(route)
            record('missing bearer credential', http=response.status_code, www_authenticate=response.headers.get('www-authenticate'))
        if PR in (406,409):
            dependencies=[]
            for idx in range(16):
                skill=f'audit-dependency-{idx:02}'
                deps=[]
                response=client.post('/v1/skills/versions',json=body(skill),headers=headers(idem=f'review-dependency-{idx:02}-0001'))
                assert response.status_code==201
                dependencies.append(dict(skill_id=skill,version='1.0.0'))
                query("UPDATE resources SET status='active' WHERE resource_id=%s",(skill+'@1.0.0',))
                query("INSERT INTO grants (grant_id,principal_id,action,resource_type,resource_id,effect,status,created_at) VALUES (%s,'incident-harness','invoke','skill',%s,'allow','active',now())",(f'grant-review-dep-{idx}',skill+'@1.0.0'))
            response=client.post('/v1/skills/versions',json=body('audit-max-dependencies',dependencies=dependencies),headers=headers(idem='review-dependency-root-0001'))
            assert response.status_code==201
            query("UPDATE resources SET status='active' WHERE resource_id='audit-max-dependencies@1.0.0'")
            query("INSERT INTO grants (grant_id,principal_id,action,resource_type,resource_id,effect,status,created_at) VALUES ('grant-review-max','incident-harness','invoke','skill','audit-max-dependencies@1.0.0','allow','active',now())")
            import sre_agent.persistence.repositories as repositories
            count=[0]
            real_verify=repositories.verify_api_key
            def count_verify(*args,**kwargs):
                count[0]+=1
                return real_verify(*args,**kwargs)
            with patch.object(repositories,'verify_api_key',count_verify):
                start=time.monotonic()
                response=client.get('/v1/skills/audit-max-dependencies/1.0.0/resolve',headers=headers(INCIDENT))
                elapsed=round(time.monotonic()-start,3)
            record('maximum direct dependencies', dependencies=16, http=response.status_code,
                   real_scrypt_verifications=count[0], elapsed_seconds=elapsed,
                   instrumentation='count wrapper forwards every real key verification; no authentication bypass')
Path(os.environ.get('EVIDENCE_OUT','/evidence'),f'pr-{PR}-probe.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
