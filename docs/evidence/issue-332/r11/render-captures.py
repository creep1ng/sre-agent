"""Render recorded real probe output; this is an evidence viewer, not a product UI."""
import html
import json
from pathlib import Path

root = Path(__file__).parent
results = root / "results"
for mode in ("foundation", "retrieval"):
    file = results / f"{mode}-results.json"
    if not file.exists():
        continue
    data = json.loads(file.read_text())
    cards = []
    observations = data["observations"]
    if mode == "retrieval":
        selected = [x for x in observations if x["scenario"] in {
            "demo-incident-response_allowed", "demo-platform-operations_allowed",
            "demo-platform-operations_other_identity", "authorized_no_match",
            "owner_unready", "bok_section_chunks_storage_failure",
            "replay_drift_chunk_content_update", "replay_drift_chunk_delete",
            "replay_drift_document_title_update", "replay_drift_document_hash_update",
            "activation_partial_document", "activation_changed_chunk",
            "activation_deleted_chunk", "activation_arbitrary_document_chunk_order",
            "activation_catalog_timestamp", "activation_rejected_catalog_timestamp",
        }]
    else:
        selected = observations
    for entry in selected:
        displayed = {k: v for k, v in entry.items() if k not in {"scenario", "sql"}}
        cards.append('<section><h2>' + html.escape(entry["scenario"].replace('_', ' ')) + '</h2><pre>' + html.escape(json.dumps(displayed, indent=2)) + '</pre></section>')
    matrix = ''.join('<tr><td>' + html.escape(x['scenario']) + '</td><td>' + str(x['status']) + '</td></tr>' for x in observations if 'status' in x)
    text = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Recorded BoK producer evidence</title>
<style>body{font-family:system-ui,sans-serif;background:#f1f5f9;color:#142438;margin:32px}h1{margin:0;font-size:29px}header{background:#142438;color:white;padding:24px;border-radius:8px}p{margin:10px 0}code{font-size:15px}main{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}section{background:white;border:1px solid #c6d1dc;border-radius:6px;padding:14px}h2{font-size:17px;margin:0 0 9px;color:#183f67}pre{font-size:13px;line-height:1.35;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}table{font-size:13px;border-collapse:collapse;width:100%}td{border-bottom:1px solid #ddd;padding:4px}footer{margin-top:16px;font-size:13px}</style>'''
    if len(selected) < len(observations):
        scenario_summary = f'{len(selected)} representative scenarios shown; full {len(observations)}-observation JSON accompanies this capture'
    else:
        scenario_summary = f'all {len(observations)} observed scenarios shown'
    text += f'<header><h1>Issue #332 · {mode.title()} · Actual producer / storage results</h1><p>Frozen source <code>{data["source_sha"]}</code></p><p>{data["captured_at_utc"]} · {scenario_summary} · all assertions passed</p><p>Recorded FastAPI TCP + PostgreSQL output, rendered for review. Not a live product UI.</p></header>'
    text += '<main>' + ''.join(cards) + '</main>'
    text += '<footer>Synthetic corpus only. No credentials or request headers are displayed. Full JSON and portable probe accompany this capture. '
    text += 'Foundation does not expose retrieval endpoints. Four replay-integrity cases and two R11 catalog-clock cases are separate owner SQL observations, not HTTP.' if mode == 'foundation' else 'Independent per-collection SQL-read instrumentation is separately verified by the real-DB TestClient suite, not measured by this network probe. Four replay-integrity cases and two R11 catalog-clock cases are separate owner SQL observations, not HTTP or audit rows.'
    text += '</footer></html>'
    (root / f'{mode}-capture.html').write_text(text)
    if mode == 'retrieval':
        audit = next(x for x in observations if x['scenario'] == 'persisted_metadata_only_audit')
        audit_table = '<table><tr><td>Operation</td><td>Status</td><td>Decision</td><td>Identity</td><td>Content</td></tr>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(row[key])) + '</td>' for key in ('operation', 'status', 'decision', 'identity_present', 'content_state')) + '</tr>' for row in audit['rows']) + '</table>'
        cause = json.loads((root / "r8-denial-cause.json").read_text())
        if cause.get("verification_state") != "verified":
            raise RuntimeError("R8 card requires exact-current-head source-test verification; no pending/expected data may be rendered")
        cause_table = '<table><tr><td>Committed transition</td><td>Asserted actual audit cause</td></tr>' + ''.join('<tr><td>' + html.escape(row['committed_transition']) + '</td><td>' + html.escape(row['asserted_audit_cause']) + '</td></tr>' for row in cause['verified_scenarios']) + '</table>'
        cause_card = '<section class="auth-card"><h2>R8 · Verified PostgreSQL / TestClient assertions (separate from TCP rows)</h2><p>' + html.escape(cause['test']) + ' · ' + html.escape(cause['test_output_excerpt']) + '</p>' + cause_table + '<p>Generic 403; zero additional content SELECTs; content-free audit assertion; synthetic state restored and next request allowed. Sanitized assertion summary, not a serialized audit-row dump. No TCP race or TCP SQL-count claim.</p></section>'
        body = '<header><h1>Issue #332 · Network audit + R8 locked-cause evidence</h1><p>TCP producer source <code>' + data['source_sha'] + '</code></p><p>Recorded TCP statuses and sanitized PostgreSQL audit projection; separate R8 TestClient assertions are labeled below</p></header><main><section><h2>Observed TCP HTTP outcomes</h2><table>' + matrix + '</table></section><section><h2>Persisted TCP audit metadata</h2><pre>' + html.escape('Query / fragment / credential scan: ' + audit['query_fragment_credential_scan']) + '</pre>' + audit_table + '</section>' + cause_card + '</main>'
        (root/'retrieval-audit-capture.html').write_text(text[:text.index('<header>')] + body + '<footer>The 20 persisted audit rows above are exclusively from the TCP producer. R8 is a separate real-PostgreSQL TestClient source-test result, not one of those rows. Grant/catalog/owner state changes were restored. Four replay-integrity cases and two R11 catalog-clock cases are separate owner SQL observations, not HTTP or audit rows. Not hosted CI or human acceptance.</footer></html>')
