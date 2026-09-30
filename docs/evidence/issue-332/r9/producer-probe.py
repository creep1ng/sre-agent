"""Run only inside the checks image against its disposable isolated PostgreSQL database.

The caller must first run assert_test_database_isolated.py. Credentials are generated
in memory, used for the synthetic seed/HTTP requests, and never printed or serialized.
"""
import asyncio
import copy
import json
import os
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
import psycopg
from psycopg import sql

from sre_agent.bok.owner import (
    DEMO_BUNDLES, BoKVersionCollision, activate_version, ingest_bundle, seed_bok_demo,
)
from sre_agent.persistence.api_keys import generate_api_key
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import KEY_ENV, SeedSettings, seed

mode, source_sha = sys.argv[1:3]
assert mode in {"foundation", "retrieval"}
assert os.environ["DATABASE_URL"] == os.environ["TEST_DATABASE_URL"]
dsn = os.environ["TEST_DATABASE_URL"]
keys = {name: generate_api_key() for name in KEY_ENV}
observed = []
result = {
    "source_sha": source_sha, "mode": mode,
    "captured_at_utc": datetime.now(UTC).isoformat(),
    "evidence_kind": "controlled integration",
    "surface": "Runtime FastAPI over TCP plus real disposable PostgreSQL",
    "observations": observed,
}


def record(name, **data):
    observed.append({"scenario": name, **data})


async def bootstrap():
    database = Database(dsn)
    try:
        settings = SeedSettings.from_environment({
            **keys, "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
            "TRIAGE_AGENT_PROVIDER": "openai",
            "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
            "REMEDIATION_AGENT_PROVIDER": "anthropic",
        })
        assert await seed(database, settings)
        async with database.transaction() as session:
            first = await seed_bok_demo(session)
        async with database.transaction() as session:
            replay = await seed_bok_demo(session)
        assert first is True and replay is False
        record("immutable_seed_replay", first_created=first, replay_created=replay)
        changed = copy.deepcopy(DEMO_BUNDLES[0])
        changed["documents"][0]["chunks"][0]["content"] = "Changed synthetic collision probe."
        try:
            async with database.transaction() as session:
                await ingest_bundle(session, changed)
        except BoKVersionCollision:
            record("same_version_collision", outcome="rejected; original persisted bytes retained")
        else:
            raise AssertionError("changed bytes accepted")
        empty = copy.deepcopy(DEMO_BUNDLES[0])
        empty["collection_id"] = "proof-unready"
        empty["documents"][0]["chunks"][0]["content"] = ""
        async with database.transaction() as session:
            await ingest_bundle(session, empty)
        try:
            async with database.transaction() as session:
                await activate_version(session, "proof-unready", "1.0.0", expected_bundle=empty)
        except ValueError as error:
            assert str(error) == "bok_version_not_ready"
            record("empty_activation", outcome="bok_version_not_ready")
        else:
            raise AssertionError("empty owner version activated")
    finally:
        await database.dispose()


async def activation_integrity_probe():
    """Exercise current owner readiness/activation against real PostgreSQL rows."""
    database = Database(dsn)

    def bundle(collection_id, documents):
        return {
            "collection_id": collection_id,
            "version": "1.0.0",
            "owner_id": "bok-platform",
            "display_name": "Synthetic replay-integrity probe",
            "description": "Controlled synthetic corpus for owner activation checks.",
            "visibility": "private",
            "documents": documents,
        }

    def document(document_id, chunks):
        return {
            "document_id": document_id,
            "title": f"Synthetic {document_id}",
            "source_ref": f"synthetic://issue-332/{document_id}",
            "chunks": chunks,
        }

    def chunk(section_id, index, content):
        return {"section_id": section_id, "chunk_index": index, "content": content}

    try:
        partial = bundle("proof-partial-document", [
            document("doc-complete", [chunk("complete", 0, "complete synthetic content")]),
            document("doc-empty", []),
        ])
        async with database.transaction() as session:
            assert await ingest_bundle(session, partial) is True
        with psycopg.connect(dsn, autocommit=True) as connection:
            status = connection.execute(
                "SELECT status FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                (partial["collection_id"], partial["version"]),
            ).fetchone()[0]
        assert status == "indexing"
        try:
            async with database.transaction() as session:
                await activate_version(session, partial["collection_id"], partial["version"], expected_bundle=partial)
        except ValueError as error:
            assert str(error) == "bok_version_not_ready"
        else:
            raise AssertionError("partial-document version activated")
        with psycopg.connect(dsn, autocommit=True) as connection:
            status_after = connection.execute(
                "SELECT status FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                (partial["collection_id"], partial["version"]),
            ).fetchone()[0]
        assert status_after == "indexing"
        record("activation_partial_document", outcome="bok_version_not_ready", status_before=status, status_after=status_after)

        for scenario, mutation, read, restore, expected_drift in (
            (
                "activation_changed_chunk",
                "UPDATE bok_section_chunks SET content=%s WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
                "SELECT content FROM bok_section_chunks WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
                "UPDATE bok_section_chunks SET content=%s WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
                "R9 persisted changed content",
            ),
            (
                "activation_deleted_chunk",
                "DELETE FROM bok_section_chunks WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
                "SELECT content FROM bok_section_chunks WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
                "INSERT INTO bok_section_chunks (collection_id,version,document_id,section_id,chunk_index,content) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (collection_id,version,document_id,section_id,chunk_index) DO UPDATE SET content=EXCLUDED.content",
                None,
            ),
        ):
            collection_id = "proof-" + scenario
            target = (collection_id, "1.0.0", "doc-z", "z-last", 1)
            original_content = "zeta second synthetic content"
            source = bundle(collection_id, [document("doc-z", [
                chunk("z-last", 1, original_content),
                chunk("z-first", 0, "zeta first synthetic content"),
            ])])
            async with database.transaction() as session:
                assert await ingest_bundle(session, source) is True
            if scenario == "activation_changed_chunk":
                mutation_params = (expected_drift, *target)
                restore_params = (original_content, *target)
            else:
                mutation_params = target
                restore_params = (*target, original_content)
            try:
                with psycopg.connect(dsn, autocommit=True) as connection:
                    changed = connection.execute(mutation, mutation_params)
                    assert changed.rowcount == 1, scenario
                    status_before = connection.execute(
                        "SELECT status FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                        (collection_id, "1.0.0"),
                    ).fetchone()[0]
                    assert status_before == "ready"
                try:
                    async with database.transaction() as session:
                        await activate_version(session, collection_id, "1.0.0", expected_bundle=source)
                except BoKVersionCollision as error:
                    assert str(error) == "collection_version_collision", scenario
                else:
                    raise AssertionError(f"{scenario}: corrupted persisted bundle activated")
                with psycopg.connect(dsn, autocommit=True) as connection:
                    drift_row = connection.execute(read, target).fetchone()
                    actual_drift = drift_row[0] if drift_row else None
                    status_after = connection.execute(
                        "SELECT status FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                        (collection_id, "1.0.0"),
                    ).fetchone()[0]
                assert actual_drift == expected_drift and status_after == "ready", scenario
            finally:
                with psycopg.connect(dsn, autocommit=True) as connection:
                    restored = connection.execute(restore, restore_params)
                    assert restored.rowcount == 1, f"{scenario}: failed to restore synthetic row"
            with psycopg.connect(dsn, autocommit=True) as connection:
                restored_value = connection.execute(read, target).fetchone()[0]
            assert restored_value == original_content, scenario
            async with database.transaction() as session:
                await activate_version(session, collection_id, "1.0.0", expected_bundle=source)
            with psycopg.connect(dsn, autocommit=True) as connection:
                final_status = connection.execute(
                    "SELECT status FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                    (collection_id, "1.0.0"),
                ).fetchone()[0]
            assert final_status == "active"
            record(scenario, outcome="collection_version_collision", status_before=status_before,
                   status_after_rejection=status_after, drift_survived_rejection=True,
                   restored_in_finally=True, status_after_restored_activation=final_status)

        unordered = bundle("proof-unordered-valid", [
            document("doc-z", [chunk("z-last", 1, "zeta second"), chunk("z-first", 0, "zeta first")]),
            document("doc-a", [chunk("a-last", 1, "alpha second"), chunk("a-first", 0, "alpha first")]),
        ])
        async with database.transaction() as session:
            assert await ingest_bundle(session, unordered) is True
        async with database.transaction() as session:
            await activate_version(session, unordered["collection_id"], unordered["version"], expected_bundle=unordered)
        with psycopg.connect(dsn, autocommit=True) as connection:
            status = connection.execute(
                "SELECT status FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                (unordered["collection_id"], unordered["version"]),
            ).fetchone()[0]
        assert status == "active"
        record("activation_arbitrary_document_chunk_order", outcome="accepted", persisted_status=status)
    finally:
        await database.dispose()


async def replay_integrity_probe():
    """Prove owner replay rejects four committed child-row drift cases, then restore."""
    database = Database(dsn)
    owner_bundle = copy.deepcopy(DEMO_BUNDLES[0])
    collection_id = owner_bundle["collection_id"]
    version = owner_bundle["version"]
    document = owner_bundle["documents"][0]
    document_id = document["document_id"]
    chunk = document["chunks"][0]
    section_id = chunk["section_id"]
    chunk_index = chunk["chunk_index"]
    original_content = chunk["content"]
    original_title = document["title"]
    original_content_hash = sha256(
        "\n".join(item["content"] for item in document["chunks"]).encode("utf-8")
    ).hexdigest()
    scope = (collection_id, version, document_id, section_id, chunk_index)
    cases = [
        (
            "replay_drift_chunk_content_update",
            "UPDATE bok_section_chunks SET content=%s WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
            ("R9 synthetic child mutation", *scope),
            "SELECT content FROM bok_section_chunks WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
            scope,
            "R9 synthetic child mutation",
            "UPDATE bok_section_chunks SET content=%s WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
            (original_content, *scope),
            original_content,
            "committed chunk content UPDATE",
        ),
        (
            "replay_drift_chunk_delete",
            "DELETE FROM bok_section_chunks WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
            scope,
            "SELECT count(*) FROM bok_section_chunks WHERE collection_id=%s AND version=%s AND document_id=%s AND section_id=%s AND chunk_index=%s",
            scope,
            0,
            "INSERT INTO bok_section_chunks (collection_id,version,document_id,section_id,chunk_index,content) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (collection_id,version,document_id,section_id,chunk_index) DO UPDATE SET content=EXCLUDED.content",
            (*scope, original_content),
            1,
            "committed chunk DELETE",
        ),
        (
            "replay_drift_document_title_update",
            "UPDATE bok_documents SET title=%s WHERE collection_id=%s AND version=%s AND document_id=%s",
            ("R9 synthetic title mutation", collection_id, version, document_id),
            "SELECT title FROM bok_documents WHERE collection_id=%s AND version=%s AND document_id=%s",
            (collection_id, version, document_id),
            "R9 synthetic title mutation",
            "UPDATE bok_documents SET title=%s WHERE collection_id=%s AND version=%s AND document_id=%s",
            (original_title, collection_id, version, document_id),
            original_title,
            "committed document title UPDATE",
        ),
        (
            "replay_drift_document_hash_update",
            "UPDATE bok_documents SET content_sha256=%s WHERE collection_id=%s AND version=%s AND document_id=%s",
            ("0" * 64, collection_id, version, document_id),
            "SELECT content_sha256 FROM bok_documents WHERE collection_id=%s AND version=%s AND document_id=%s",
            (collection_id, version, document_id),
            "0" * 64,
            "UPDATE bok_documents SET content_sha256=%s WHERE collection_id=%s AND version=%s AND document_id=%s",
            (original_content_hash, collection_id, version, document_id),
            original_content_hash,
            "committed document content_sha256 UPDATE",
        ),
    ]
    try:
        for (
            scenario,
            mutation_sql,
            mutation_params,
            observed_sql,
            observed_params,
            drift_value,
            restore_sql,
            restore_params,
            original_value,
            operation,
        ) in cases:
            manifest_before = None
            drift_survived_replay = False
            try:
                with psycopg.connect(dsn, autocommit=True) as connection:
                    manifest_before = connection.execute(
                        "SELECT manifest_sha256 FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                        (collection_id, version),
                    ).fetchone()[0]
                    changed = connection.execute(mutation_sql, mutation_params)
                    assert changed.rowcount == 1, scenario
                    manifest_after = connection.execute(
                        "SELECT manifest_sha256 FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                        (collection_id, version),
                    ).fetchone()[0]
                    assert manifest_after == manifest_before, scenario

                try:
                    async with database.transaction() as session:
                        await ingest_bundle(session, owner_bundle)
                except BoKVersionCollision as error:
                    assert str(error) == "collection_version_collision", scenario
                else:
                    raise AssertionError(f"{scenario}: exact replay accepted persisted child drift")

                with psycopg.connect(dsn, autocommit=True) as connection:
                    persisted_drift = connection.execute(observed_sql, observed_params).fetchone()[0]
                    manifest_after_replay = connection.execute(
                        "SELECT manifest_sha256 FROM bok_collection_versions WHERE collection_id=%s AND version=%s",
                        (collection_id, version),
                    ).fetchone()[0]
                assert persisted_drift == drift_value, scenario
                assert manifest_after_replay == manifest_before, scenario
                drift_survived_replay = True
            finally:
                with psycopg.connect(dsn, autocommit=True) as connection:
                    restored = connection.execute(restore_sql, restore_params)
                    assert restored.rowcount == 1, f"{scenario}: failed to restore synthetic row"

            with psycopg.connect(dsn, autocommit=True) as connection:
                restored_value = connection.execute(observed_sql, observed_params).fetchone()[0]
            assert restored_value == original_value, scenario
            async with database.transaction() as session:
                replay_created = await ingest_bundle(session, owner_bundle)
            assert replay_created is False, scenario
            record(
                scenario,
                operation=operation,
                parent_manifest_unchanged=True,
                replay_outcome="BoKVersionCollision",
                child_drift_survived_replay=drift_survived_replay,
                restored=True,
                intact_replay_created=replay_created,
            )
    finally:
        await database.dispose()


asyncio.run(bootstrap())
asyncio.run(activation_integrity_probe())
asyncio.run(replay_integrity_probe())
with psycopg.connect(dsn, autocommit=True) as connection:
    query = """SELECT v.collection_id, v.version, v.status,
        (SELECT count(*) FROM bok_documents d WHERE d.collection_id=v.collection_id AND d.version=v.version),
        (SELECT count(*) FROM bok_section_chunks c WHERE c.collection_id=v.collection_id AND c.version=v.version)
        FROM bok_collection_versions v WHERE v.collection_id LIKE 'demo-%' ORDER BY v.collection_id"""
    rows = connection.execute(query).fetchall()
    assert rows == [(b["collection_id"], "1.0.0", "active", 1, 1) for b in DEMO_BUNDLES]
    record("persisted_demo_rows", sql=query, columns=["collection_id", "version", "status", "documents", "chunks"], rows=rows)
    original = connection.execute("SELECT content FROM bok_section_chunks WHERE collection_id='demo-incident-response'").fetchone()[0]
    assert original == DEMO_BUNDLES[0]["documents"][0]["chunks"][0]["content"]
    record("collision_preserves_original", unchanged=True)
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert revision == ("20260929_15" if mode == "foundation" else "20260929_16")
    record("schema_head", revision=revision)
    if mode == "retrieval":
        for principal, collection in (("demo-human", "demo-incident-response"), ("restricted-harness", "demo-platform-operations")):
            for action in ("bok.search", "bok.read"):
                connection.execute("""INSERT INTO grants (grant_id,principal_id,action,resource_type,resource_id,effect,status,created_at)
                    VALUES (%s,%s,%s,'bok_collection',%s,'allow','active',now())""",
                    (f"proof-{principal}-{action.replace('.', '-')}", principal, action, f"{collection}@1.0.0"))
        connection.execute("""INSERT INTO resources (resource_type,resource_id,status,owner_id,source,source_ref,display_name,visibility,description,tags)
            VALUES ('bok_collection','proof-unready@1.0.0','active','bok-platform','bok','proof-unready@1.0.0','Synthetic unready','private','Empty proof corpus','[]')""")
        connection.execute("""INSERT INTO grants (grant_id,principal_id,action,resource_type,resource_id,effect,status,created_at)
            VALUES ('proof-unready-search','demo-human','bok.search','bok_collection','proof-unready@1.0.0','allow','active',now())""")
        grants = connection.execute("SELECT principal_id,action,resource_type,resource_id FROM grants WHERE grant_id LIKE 'proof-%' ORDER BY principal_id,action,resource_id").fetchall()
        record("exact_synthetic_grants", columns=["principal_id", "action", "resource_type", "resource_id"], rows=grants)

client = httpx.Client(base_url="http://api:8000", timeout=10, trust_env=False)
for attempt in range(40):
    try:
        ready = client.get("/health/ready")
        if ready.status_code == 200:
            break
    except httpx.TransportError:
        pass
    time.sleep(0.5)
else:
    raise AssertionError("runtime API did not become ready")
record("runtime_readiness", method="GET", path="/health/ready", status=ready.status_code, body=ready.json())


def request(name, method, path, expected, key=None, body=None):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    response = client.request(method, path, headers=headers, json=body)
    value = response.json()
    assert response.status_code == expected, (name, response.status_code)
    record(name, method=method, path=path, status=response.status_code, body=value)
    return value


def url(collection):
    return f"/v1/bok/collections/{collection}/versions/1.0.0"


if mode == "foundation":
    request("retrieval_not_part_of_foundation", "POST", url("demo-incident-response") + "/search", 404,
            body={"query": "severity"})
else:
    demo, restricted = keys["DEMO_HUMAN_API_KEY"], keys["RESTRICTED_HARNESS_API_KEY"]
    for bundle, key, other in ((DEMO_BUNDLES[0], demo, restricted), (DEMO_BUNDLES[1], restricted, demo)):
        collection = bundle["collection_id"]
        document = bundle["documents"][0]
        chunk = document["chunks"][0]
        body = {"query": "severity OR rollback", "limit": 5}
        found = request(f"{collection}_allowed", "POST", url(collection) + "/search", 200, key, body)
        assert len(found["results"]) == 1
        expected = {"collection_id": collection, "version": "1.0.0", "document_id": document["document_id"],
                    "title": document["title"], "source_ref": document["source_ref"], **chunk}
        assert {k: v for k, v in found["results"][0].items() if k != "score"} == expected
        direct_path = url(collection) + f"/chunks/{document['document_id']}/{chunk['section_id']}/0"
        direct = request(f"{collection}_direct", "GET", direct_path, 200, key)
        assert direct == expected
        request(f"{collection}_other_identity", "POST", url(collection) + "/search", 403, other, body)
        request(f"{collection}_direct_denied", "GET", direct_path, 403, other)
    request("unauthenticated", "POST", url("demo-incident-response") + "/search", 401, body={"query": "severity"})
    empty = request("authorized_no_match", "POST", url("demo-incident-response") + "/search", 200, demo, {"query": "nonexistent-needle"})
    assert empty == {"results": []}
    request("authorized_exact_miss", "GET", url("demo-incident-response") + "/chunks/unknown/unknown/0", 404, demo)
    request("owner_unready", "POST", url("proof-unready") + "/search", 503, demo, {"query": "severity"})
    with psycopg.connect(dsn, autocommit=True) as connection:
        for kind, table, column, value, state, status in (
            ("grant_revocation", "grants", "grant_id", "proof-restricted-harness-bok-search", "revoked", 403),
            ("catalog_deactivation", "resources", "resource_id", "demo-platform-operations@1.0.0", "inactive", 403),
            ("owner_revocation", "bok_collection_versions", "collection_id", "demo-platform-operations", "revoked", 503),
        ):
            statement = sql.SQL("UPDATE {} SET status=%s WHERE {}=%s").format(sql.Identifier(table), sql.Identifier(column))
            try:
                connection.execute(statement, (state, value))
                request(kind, "POST", url("demo-platform-operations") + "/search", status, restricted, {"query": "rollback"})
            finally:
                connection.execute(statement, ("active", value))
            request(kind + "_restored", "POST", url("demo-platform-operations") + "/search", 200, restricted, {"query": "rollback"})
        for table in ("bok_section_chunks", "credentials"):
            rename = sql.SQL("ALTER TABLE {} RENAME TO {}").format(sql.Identifier(table), sql.Identifier("proof_unavailable_" + table))
            restore = sql.SQL("ALTER TABLE {} RENAME TO {}").format(sql.Identifier("proof_unavailable_" + table), sql.Identifier(table))
            try:
                connection.execute(rename)
                if table == "bok_section_chunks":
                    request("denied_while_content_storage_unavailable", "POST", url("demo-platform-operations") + "/search", 403, demo, {"query": "rollback"})
                failed = request(table + "_storage_failure", "POST", url("demo-incident-response") + "/search", 503, demo, {"query": "severity"})
                assert failed["error"]["code"] == "storage_unavailable"
            finally:
                connection.execute(restore)
        events = [r[0] for r in connection.execute("SELECT to_jsonb(audit_events) FROM audit_events WHERE operation IN ('bok.search','bok.read') ORDER BY occurred_at,event_id")]
        serialized = json.dumps(events, default=str)
        for private in [*keys.values(), "severity OR rollback", "nonexistent-needle", *[b["documents"][0]["chunks"][0]["content"] for b in DEMO_BUNDLES]]:
            assert private not in serialized
        assert all(row["content_state"] == "absent" and row["redacted_content"] is None for row in events)
        record("persisted_metadata_only_audit", rows=[{
            "operation": row["operation"], "stage": row["stage"], "status": row["response_status"],
            "decision": row["policy_decision"]["decision"] if row["policy_decision"] else None,
            "identity_present": row["identity"] is not None, "resource_present": row["resource"] is not None,
            "content_state": row["content_state"],
        } for row in events], query_fragment_credential_scan="passed")
client.close()
result["outcome"] = "all assertions passed"
result["storage_observer_scope"] = "Network probe reads persisted owner/audit SQL. Zero-content-read counts are independently covered by source TestClient SQL observer tests; not measured by this network process."
encoded = json.dumps(result, indent=2, default=str) + "\n"
assert all(secret not in encoded for secret in keys.values())
output_dir = Path(os.environ.get("EVIDENCE_RESULTS_DIR", "/results"))
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / f"{mode}-results.json").write_text(encoded)
print(json.dumps({"mode": mode, "source_sha": source_sha, "scenarios": len(observed), "outcome": result["outcome"]}))
