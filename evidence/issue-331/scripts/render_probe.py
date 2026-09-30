#!/usr/bin/env python3
"""Render ONLY actual allowlisted probe JSON; this does not execute probes or create PNGs."""
import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path

HEADS = {
    '387': '402ff6e580fa15e765bedc89ae5a6f889202e640',
    '388': 'c0d8076908dbe425f8dbb7b4ff7d717a39ae2117',
    '397': '7327ca0ef8a4d810afe2376aec2ce5bd0959677e',
    '403': '025476049fa094c852c48565f45d1e32f472bb3d',
    '402': '6eb618906ff846f202ab6d43fca4fa7ae7523fd8',
    '404': '4b82922bef24bd455c41283b98409d1af5886830',
    '405': '3b525e0a305e8b44bdcd54495284950393a7b415',
    '331-validation-child': '94d14d9e37c5b456b441201b4d98a13bacc056d1',
    '406': '2e9b24004043d830b911c15cea6fb10d1da7a9cc',
    '407': 'c56f32eeed1e07d230f4de402c263075c5191809',
    '409': 'e5ec78a0b0e60363af1ac674c2ce8d3a6627d094',
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True, help='Actual, sanitized JSON emitted by executed HTTP/Postgres probe')
    p.add_argument('--output', required=True, help='Private HTML report path; not a screenshot')
    a = p.parse_args()
    data = json.loads(Path(a.input).read_text())
    required = {'slice','tested_sha','observed_at_utc','http','sql','probe_command','scenario'}
    if set(data) != required: raise SystemExit('refusing unexpected/missing top-level field')
    if data['slice'] not in HEADS or data['tested_sha'] != HEADS[data['slice']]: raise SystemExit('refusing unknown or mismatched source SHA')
    if not isinstance(data['probe_command'], str) or not data['probe_command'].startswith('docker compose '): raise SystemExit('refusing: provenance must be an exact Docker Compose invocation')
    if re.search(r'(?i)(bearer\s+\S+|api[_ -]?key|password|secret|authorization:|prompt|instructions|postgres(?:ql)?://|/home/|/tmp/)', json.dumps(data)):
        raise SystemExit('refusing possible credential, prompt/content, connection string or private path; sanitize before rendering')
    if not isinstance(data['http'], dict) or set(data['http']) - {'status','request_id','retryable','allowlisted_fields','www_authenticate','credential_verifier_calls','dependency_count','publish_status','denied_status','unauthorized_content_selects','before_dependency_grant_status','pre_deactivation_status','lifecycle_status_write','retry_status','rollback_status_unchanged','status_sequence','resolution_count','request_ids','unauthenticated_status','unauthenticated_challenge'}: raise SystemExit('refusing unexpected HTTP fields')
    if not isinstance(data['sql'], dict) or set(data['sql']) - {'statement_categories','audit_rows_correlated','audit_rows_total','audit_status','audit_outcome','audit_reason','failed_audit_rows','retry_audit_rows','status_after_retry','skill_rows','grant_rows','status_rows','content_selects','dependency_content_selects','migration_heads','schema_columns','audit_events_without_content','resolution_audit_rows','audit_instruction_matches','active_grant_rows','migration_revision','successful_status_audit_rows'}: raise SystemExit('refusing unexpected SQL fields')
    if not isinstance(data['http'].get('status'), int): raise SystemExit('missing observed HTTP status')
    if 'request_id' in data['http'] and not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', str(data['http']['request_id'])): raise SystemExit('unsafe request id')
    lines=[('HTTP '+k, str(v)) for k,v in data['http'].items()]
    lines += [('PostgreSQL '+k, json.dumps(v,ensure_ascii=True)) for k,v in data['sql'].items()]
    esc=html.escape
    scenario=esc(data['scenario'])
    cards=''.join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>' for k,v in lines)
    sha=esc(data['tested_sha']); stamp=esc(data['observed_at_utc']); sl=esc(data['slice']); cmd=esc(data['probe_command'])
    doc=f'''<!doctype html><meta charset="utf-8"><title>Issue 331 controlled integration observation</title><style>body{{font:16px system-ui,sans-serif;margin:3rem;color:#18212b;background:#f5f7fa}}main{{max-width:980px;margin:auto;background:white;border:1px solid #cbd5e1;border-radius:12px;padding:2rem}}h1{{font-size:1.45rem}}table{{border-collapse:collapse;width:100%;margin-top:1.5rem}}th,td{{text-align:left;border-bottom:1px solid #d9e0e8;padding:.65rem;vertical-align:top}}th{{width:30%;background:#f8fafc}}code{{overflow-wrap:anywhere}}</style><main><h1>Observed HTTP → PostgreSQL result</h1><p>Slice: <b>{sl}</b> · Tested SHA: <code>{sha}</code></p><p>Observed at (UTC): {stamp}</p><p><b>Observed scenario:</b> {scenario}</p><table>{cards}</table><p>Captured with the Docker Compose checks runner; portable rerun command and exact image provenance accompany this observation.</p><p>Controlled integration; synthetic test data. This report displays only allowlisted actual result values.</p></main>'''
    Path(a.output).write_text(doc)
    print(f'rendered allowlisted observed result to {a.output}; this is HTML, not a screenshot')

if __name__ == '__main__': main()
