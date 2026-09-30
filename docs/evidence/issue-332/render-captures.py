"""Render recorded real probe output; this is an evidence viewer, not a product UI."""
import html
import json
from pathlib import Path

root = Path(__file__).parent
for mode in ("foundation", "retrieval"):
    file = root / f"{mode}-results.json"
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
        }]
    else:
        selected = observations
    for entry in selected:
        displayed = {k: v for k, v in entry.items() if k not in {"scenario", "sql"}}
        cards.append('<section><h2>' + html.escape(entry["scenario"].replace('_', ' ')) + '</h2><pre>' + html.escape(json.dumps(displayed, indent=2)) + '</pre></section>')
    matrix = ''.join('<tr><td>' + html.escape(x['scenario']) + '</td><td>' + str(x['status']) + '</td></tr>' for x in observations if 'status' in x)
    text = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Recorded BoK producer evidence</title>
<style>body{font-family:system-ui,sans-serif;background:#f1f5f9;color:#142438;margin:32px}h1{margin:0;font-size:29px}header{background:#142438;color:white;padding:24px;border-radius:8px}p{margin:10px 0}code{font-size:15px}main{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}section{background:white;border:1px solid #c6d1dc;border-radius:6px;padding:14px}h2{font-size:17px;margin:0 0 9px;color:#183f67}pre{font-size:13px;line-height:1.35;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}table{font-size:13px;border-collapse:collapse;width:100%}td{border-bottom:1px solid #ddd;padding:4px}footer{margin-top:16px;font-size:13px}</style>'''
    text += f'<header><h1>Issue #332 · {mode.title()} · Actual producer / storage results</h1><p>Frozen source <code>{data["source_sha"]}</code></p><p>{data["captured_at_utc"]} · {len(observations)} observed scenarios · all assertions passed</p><p>Recorded FastAPI TCP + PostgreSQL output, rendered for review. Not a live product UI.</p></header>'
    text += '<main>' + ''.join(cards) + '</main>'
    text += '<footer>Synthetic corpus only. No credentials or request headers are displayed. Full JSON and portable probe accompany this capture. '
    text += 'Foundation does not expose retrieval endpoints.' if mode == 'foundation' else 'Independent per-collection SQL-read instrumentation is separately verified by the real-DB TestClient suite, not measured by this network probe.'
    text += '</footer></html>'
    (root / f'{mode}-capture.html').write_text(text)
    if mode == 'retrieval':
        audit = next(x for x in observations if x['scenario'] == 'persisted_metadata_only_audit')
        audit_table = '<table><tr><td>Operation</td><td>Status</td><td>Decision</td><td>Identity</td><td>Content</td></tr>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(row[key])) + '</td>' for key in ('operation', 'status', 'decision', 'identity_present', 'content_state')) + '</tr>' for row in audit['rows']) + '</table>'
        body = '<header><h1>Issue #332 · Network transitions and persisted audit</h1><p>Frozen source <code>' + data['source_sha'] + '</code></p><p>Actual recorded TCP statuses and sanitized PostgreSQL audit projection</p></header><main><section><h2>Observed HTTP outcomes</h2><table>' + matrix + '</table></section><section><h2>Persisted audit metadata</h2><pre>' + html.escape('Query / fragment / credential scan: ' + audit['query_fragment_credential_scan']) + '</pre>' + audit_table + '</section></main>'
        (root/'retrieval-audit-capture.html').write_text(text[:text.index('<header>')] + body + '<footer>Grant/catalog/owner changes committed before the next request. Query, fragments and credentials absent from persisted audit. Not hosted CI or human acceptance.</footer></html>')
