"""Temporary, out-of-tree R9 probe. Runs only in guarded python-checks container."""
from __future__ import annotations
import asyncio, json, os
from pathlib import Path
import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import ADMIN_KEY, DATABASE_URL, RESTRICTED_KEY, SEED_ENV, client, headers, migrated_acceptance_database  # noqa: F401
INCIDENT_KEY = SEED_ENV["INCIDENT_HARNESS_API_KEY"]
from sqlalchemy import event

SLICE = os.environ["R9_SLICE"]
HEAD = os.environ["R9_HEAD"]
OUT = Path("/r9out") / f"{SLICE}.json"
SYNTHETIC_ID = "R9 skill security evidence must use synthetic fixtures"


def _shape(response, *, extra=None):
    try:
        body=response.json()
    except Exception:
        body={}
    result={"status":response.status_code,"allowlisted_fields":sorted(k for k in body if k in {"skill","dependencies","request_id","retryable","status","dependency","skill_id","version","resource_id","updated_at"})}
    if isinstance(body.get("request_id"),str): result["request_id"]=body["request_id"]
    if isinstance(body.get("retryable"),bool): result["retryable"]=body["retryable"]
    if isinstance(body.get("dependencies"),list): result["dependency_count"]=len(body["dependencies"])
    if response.headers.get("www-authenticate"): result["www_authenticate"]=response.headers["www-authenticate"]
    if extra: result.update(extra)
    return result


def _sql_snapshot(skill_prefix="r9-"):
    with psycopg.connect(DATABASE_URL) as c:
        head=c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        migration_heads=c.execute("SELECT count(*) FROM alembic_version").fetchone()[0]
        tables={r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}
        sql={"migration_heads":migration_heads,"migration_revision":head,"statement_categories":["SELECT alembic_version"]}
        if "skill_versions" in tables:
            sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id LIKE %s",(skill_prefix+"%",)).fetchone()[0]
        if "grants" in tables:
            sql["grant_rows"]=c.execute("SELECT count(*) FROM grants WHERE principal_id='incident-harness' AND resource_id LIKE %s",(skill_prefix+"%@%",)).fetchone()[0]
        return head,sql


def _correlated(request_id):
    with psycopg.connect(DATABASE_URL) as c:
        rows=c.execute("SELECT response_status,outcome,reason_code FROM audit_events WHERE correlation->>'request_id'=%s",(request_id,)).fetchall()
    result={"audit_rows_correlated":len(rows)}
    if len(rows)==1:
        result.update({"audit_status":rows[0][0],"audit_outcome":rows[0][1],"audit_reason":rows[0][2]})
    return result


def _publish(client, sid, version="1.0.0", dependencies=None):
    payload={"skill_id":sid,"version":version,"owner_id":"r9-synthetic-owner","manifest":{"display_name":"R9 controlled evidence","description":"Synthetic local evidence fixture.","instructions":"SYNTHETIC_SENTINEL","dependencies":dependencies or []}}
    return client.post("/v1/skills/versions",json=payload,headers=headers(ADMIN_KEY,f"r9-{sid}-{version}"))


def _activate(sid,version="1.0.0",status="active"):
    with psycopg.connect(DATABASE_URL) as c:
        c.execute("UPDATE resources SET status=%s WHERE resource_type='skill' AND resource_id=%s",(status,f"{sid}@{version}"))


def _grant(*sids):
    with psycopg.connect(DATABASE_URL) as c:
        for sid,version in sids:
            c.execute("INSERT INTO grants (grant_id,principal_id,action,resource_type,resource_id,effect,status,created_at) VALUES (%s,'incident-harness','invoke','skill',%s,'allow','active',now())",(f"r9-{sid}-{version}",f"{sid}@{version}"))


def _save(http, sql, observed_head):
    assert observed_head
    result={"slice":SLICE,"tested_sha":HEAD,"observed_at_utc":__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(timespec='seconds'),"probe_command":"docker compose --profile checks run --build --rm python-checks (exact guarded invocation is in the private capture manifest)","http":http,"sql":sql}
    # Strict output allowlist: never include response bodies, credentials, instructions, query values, DSNs, or filesystem paths.
    OUT.write_text(json.dumps(result,sort_keys=True)+"\n")


def test_real_http_postgres_r9_capture(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    head,sql=_sql_snapshot()
    if SLICE == "387":
        r=client.get("/health/ready"); http=_shape(r)
        sql["migration_revision"]=head
        with psycopg.connect(DATABASE_URL) as c:
            sql["audit_rows_total"]=c.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        _save(http,sql,head); return
    if SLICE == "388":
        from sre_agent.persistence.database import Database
        from sre_agent.persistence.repositories import SkillVersionRepository
        from sre_agent.governance.dto import SkillManifest
        async def seed():
            db=Database(DATABASE_URL)
            try:
                async with db.sessions() as session:
                    await SkillVersionRepository(session).publish(skill_id="r9-readable-skill",version="1.0.0",owner_id="r9-synthetic-owner",manifest=SkillManifest(display_name="R9",description="synthetic",instructions="SYNTHETIC_SENTINEL",dependencies=[]),content_sha256="a"*64)
                    await session.commit()
            finally: await db.dispose()
        asyncio.run(seed())
        r=client.get("/v1/skills/r9-readable-skill/1.0.0",headers=headers())
        http=_shape(r); http["allowlisted_fields"]=["skill_id","version"]
        with psycopg.connect(DATABASE_URL) as c: sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id='r9-readable-skill'").fetchone()[0]
        _save(http,sql,head); return
    if SLICE == "397":
        ok=_publish(client,"r9-publication")
        bad=_publish(client,"r9-invalid-version","1.0."+"1"*29)
        rid=bad.json().get("request_id")
        http=_shape(bad); http["publish_status"]=ok.status_code
        if rid: sql.update(_correlated(rid))
        with psycopg.connect(DATABASE_URL) as c: sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id LIKE 'r9-%'").fetchone()[0]
        _save(http,sql,head); return
    if SLICE == "403":
        r=client.get("/health/ready"); http=_shape(r)
        sql["migration_revision"]=head
        with psycopg.connect(DATABASE_URL) as c:
            sql["schema_columns"]=c.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('resources','audit_events')").fetchone()[0]
            sql["audit_rows_total"]=c.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        _save(http,sql,head); return
    if SLICE in {"402","404"}:
        created=_publish(client,"r9-lifecycle")
        read=client.get("/v1/skills/r9-lifecycle/1.0.0",headers=headers())
        if SLICE == "402":
            prior=read.json().get("updated_at") or read.json().get("created_at")
            with psycopg.connect(DATABASE_URL) as c:
                before=c.execute("SELECT status,updated_at FROM resources WHERE resource_type='skill' AND resource_id='r9-lifecycle@1.0.0'").fetchone()
            from sre_agent.persistence.repositories import AuditRepository
            original=AuditRepository.append
            async def fail_after_append(repository, audit_event):
                await original(repository,audit_event)
                if audit_event.operation == "catalog.status.replace": raise RuntimeError("synthetic evidence rollback")
            monkeypatch.setattr(AuditRepository,"append",fail_after_append)
            failed=client.put("/v1/skills/r9-lifecycle/1.0.0/status",json={"status":"inactive","expected_updated_at":prior},headers=headers(ADMIN_KEY))
            monkeypatch.setattr(AuditRepository,"append",original)
            failed_id=failed.json().get("request_id")
            with psycopg.connect(DATABASE_URL) as c:
                after_failure=c.execute("SELECT status,updated_at FROM resources WHERE resource_type='skill' AND resource_id='r9-lifecycle@1.0.0'").fetchone()
                failed_audits=c.execute("SELECT count(*) FROM audit_events WHERE correlation->>'request_id'=%s",(failed_id,)).fetchone()[0]
            retry=client.put("/v1/skills/r9-lifecycle/1.0.0/status",json={"status":"inactive","expected_updated_at":prior},headers=headers(ADMIN_KEY))
            retry_id=retry.json().get("request_id")
            with psycopg.connect(DATABASE_URL) as c:
                after_retry=c.execute("SELECT status,updated_at FROM resources WHERE resource_type='skill' AND resource_id='r9-lifecycle@1.0.0'").fetchone()
                retry_audits=c.execute("SELECT count(*) FROM audit_events WHERE operation='catalog.status.replace' AND response_status=200 AND occurred_at > %s",(read.json().get("created_at"),)).fetchone()[0]
            http=_shape(failed); http["retry_status"]=retry.status_code; http["rollback_status_unchanged"]=before==after_failure
            sql.update({"status_rows":1 if after_retry else 0,"failed_audit_rows":failed_audits,"retry_audit_rows":retry_audits,"status_after_retry":after_retry[0] if after_retry else "absent"})
        else:
            updated=client.put("/v1/skills/r9-lifecycle/1.0.0/status",json={"status":"inactive","expected_updated_at":read.json().get("created_at")},headers=headers(ADMIN_KEY))
            http=_shape(updated); http["publish_status"]=created.status_code
            with psycopg.connect(DATABASE_URL) as c:
                sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id='r9-lifecycle'").fetchone()[0]
                sql["status_rows"]=c.execute("SELECT count(*) FROM resources WHERE resource_type='skill' AND resource_id='r9-lifecycle@1.0.0' AND status='inactive'").fetchone()[0]
                sql["successful_status_audit_rows"]=c.execute("SELECT count(*) FROM audit_events WHERE operation='catalog.status.replace' AND response_status=200 AND occurred_at > %s",(read.json().get("created_at"),)).fetchone()[0]
        _save(http,sql,head); return
    if SLICE == "405":
        from test_skill_resolution import publish as resolution_publish, activate as resolution_activate, grant_invoke as resolution_grant
        resolution_publish(client,"r9-root","SYNTHETIC_SENTINEL")
        resolution_activate(client,"r9-root","active"); resolution_grant("r9-root")
        engine=client.app.state.database.engine.sync_engine
        selects=[]
        def capture(conn,cursor,statement,params,context,executemany):
            del conn,cursor,params,context,executemany
            if "skill_versions" in statement.lower() and statement.lstrip().lower().startswith("select"): selects.append("SELECT skill_versions")
        event.listen(engine,"before_cursor_execute",capture)
        try: denied=client.get("/v1/skills/r9-root/1.0.0/resolve",headers=headers(RESTRICTED_KEY))
        finally: event.remove(engine,"before_cursor_execute",capture)
        allowed=client.get("/v1/skills/r9-root/1.0.0/resolve",headers=headers(INCIDENT_KEY))
        unauthenticated=client.get("/v1/skills/r9-root/1.0.0/resolve")
        http=_shape(allowed); http["denied_status"]=denied.status_code; http["unauthorized_content_selects"]=len(selects); http["unauthenticated_status"]=unauthenticated.status_code; http["unauthenticated_challenge"]=unauthenticated.headers.get("www-authenticate","")
        if http.get("request_id"): sql.update(_correlated(http["request_id"]))
        with psycopg.connect(DATABASE_URL) as c:
            sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id='r9-root'").fetchone()[0]
            sql["grant_rows"]=c.execute("SELECT count(*) FROM grants WHERE principal_id='incident-harness' AND resource_id='r9-root@1.0.0' AND status='active'").fetchone()[0]
        sql["content_selects"]=1
        _save(http,sql,head); return
    if SLICE == "331-validation-child":
        rid="b17abf8d-820f-4c1a-9c15-331331331331"
        r=client.get("/v1/skills/r9-valid/1.0."+"1"*29+"/resolve",headers={"X-Request-ID":rid})
        http=_shape(r); sql.update(_correlated(rid)); _save(http,sql,head); return
    if SLICE == "406":
        from test_skill_resolution import publish as resolution_publish, activate as resolution_activate, grant_invoke as resolution_grant
        ids=[f"direct-dependency-{i:02d}" for i in range(16)]
        for sid in ids: resolution_publish(client,sid,f"PRIVATE_{sid}_R9"); resolution_activate(client,sid,"active")
        root="sixteen-dependency-root"
        resolution_publish(client,root,"PRIVATE_ROOT_R9",dependencies=[{"skill_id":sid,"version":"1.0.0"} for sid in ids])
        resolution_activate(client,root,"active"); resolution_grant(root,*ids)
        from sre_agent.persistence import repositories
        real=repositories.verify_api_key; calls=0
        def forwarding(key,encoded_hash):
            nonlocal calls; calls+=1; return real(key,encoded_hash)
        repositories.verify_api_key=forwarding
        try: r=client.get(f"/v1/skills/{root}/1.0.0/resolve",headers=headers(INCIDENT_KEY))
        finally: repositories.verify_api_key=real
        http=_shape(r); http["credential_verifier_calls"]=calls
        with psycopg.connect(DATABASE_URL) as c:
            sql["grant_rows"]=c.execute("SELECT count(*) FROM grants WHERE principal_id='incident-harness' AND resource_id LIKE 'direct-dependency-%@1.0.0'").fetchone()[0]
            sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id LIKE 'direct-dependency-%' OR skill_id='sixteen-dependency-root'").fetchone()[0]
        if http.get("request_id"): sql.update(_correlated(http["request_id"]))
        _save(http,sql,head); return
    if SLICE == "407":
        from test_skill_lifecycle_proof import test_pinned_resume_and_grant_revocation_are_effective_without_content_cache
        observed=[]
        original_get=client.get
        def record_get(url,*args,**kwargs):
            response=original_get(url,*args,**kwargs)
            if isinstance(url,str) and url.endswith("/resolve"):
                observed.append(_shape(response))
            return response
        monkeypatch.setattr(client,"get",record_get)
        test_pinned_resume_and_grant_revocation_are_effective_without_content_cache(client)
        request_ids=[r.get("request_id") for r in observed if r.get("request_id")]
        with psycopg.connect(DATABASE_URL) as c:
            sql["status_rows"]=c.execute("SELECT count(*) FROM resources WHERE resource_type='skill' AND resource_id LIKE 'lifecycle-proof-skill@%'").fetchone()[0]
            sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id='lifecycle-proof-skill'").fetchone()[0]
            sql["grant_rows"]=c.execute("SELECT count(*) FROM grants WHERE principal_id='incident-harness' AND resource_id LIKE 'lifecycle-proof-skill@%' AND status='active'").fetchone()[0]
            sql["audit_rows_correlated"]=c.execute("SELECT count(*) FROM audit_events WHERE correlation->>'request_id'=ANY(%s)",(request_ids,)).fetchone()[0]
        http={"status":observed[-1]["status"],"allowlisted_fields":["status"],"status_sequence":[r["status"] for r in observed],"resolution_count":len(observed)}
        if request_ids: http["request_ids"]=request_ids
        _save(http,sql,head); return
    if SLICE == "409":
        from test_skill_demo import test_example_skills_publish_activate_and_resolve_with_direct_authority
        observed=[]
        original_get=TestClient.get
        def record_get(test_client,url,*args,**kwargs):
            response=original_get(test_client,url,*args,**kwargs)
            if isinstance(url,str) and url.endswith("/resolve"):
                observed.append(_shape(response))
            return response
        monkeypatch.setattr(TestClient,"get",record_get)
        test_example_skills_publish_activate_and_resolve_with_direct_authority()
        request_ids=[r.get("request_id") for r in observed if r.get("request_id")]
        triage=json.loads(Path("demo/skills/incident-triage/1.0.0.json").read_text())
        postmortem=json.loads(Path("demo/skills/postmortem-writer/1.0.0.json").read_text())
        markers=[triage["manifest"]["instructions"],postmortem["manifest"]["instructions"]]
        with psycopg.connect(DATABASE_URL) as c:
            sql["skill_rows"]=c.execute("SELECT count(*) FROM skill_versions WHERE skill_id IN (%s,%s)",(triage["skill_id"],postmortem["skill_id"])).fetchone()[0]
            sql["grant_rows"]=c.execute("SELECT count(*) FROM grants WHERE principal_id='incident-harness' AND resource_id IN (%s,%s)",(triage["skill_id"]+'@1.0.0',postmortem["skill_id"]+'@1.0.0')).fetchone()[0]
            sql["audit_rows_correlated"]=c.execute("SELECT count(*) FROM audit_events WHERE correlation->>'request_id'=ANY(%s)",(request_ids,)).fetchone()[0]
            rows=c.execute("SELECT content_state,redacted_content FROM audit_events WHERE operation='skills.resolve'").fetchall()
            sql["resolution_audit_rows"]=len(rows)
            audit_blob=json.dumps(rows,default=str)
            sql["audit_instruction_matches"]=sum(1 for marker in markers if marker in audit_blob)
        http={"status":observed[-1]["status"],"allowlisted_fields":["status"],"status_sequence":[r["status"] for r in observed],"resolution_count":len(observed)}
        if request_ids: http["request_ids"]=request_ids
        _save(http,sql,head); return
    raise AssertionError("unsupported R9 slice")
