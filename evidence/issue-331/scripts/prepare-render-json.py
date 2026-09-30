#!/usr/bin/env python3
"""Create safe presentation JSON from an executed R9 probe; never fabricate measurements."""
import argparse,json,re
from pathlib import Path

HEADS={
'387':'402ff6e580fa15e765bedc89ae5a6f889202e640','388':'c0d8076908dbe425f8dbb7b4ff7d717a39ae2117','397':'7327ca0ef8a4d810afe2376aec2ce5bd0959677e','403':'025476049fa094c852c48565f45d1e32f472bb3d','402':'6eb618906ff846f202ab6d43fca4fa7ae7523fd8','404':'4b82922bef24bd455c41283b98409d1af5886830','405':'3b525e0a305e8b44bdcd54495284950393a7b415','331-validation-child':'94d14d9e37c5b456b441201b4d98a13bacc056d1','406':'2e9b24004043d830b911c15cea6fb10d1da7a9cc','407':'c56f32eeed1e07d230f4de402c263075c5191809','409':'e5ec78a0b0e60363af1ac674c2ce8d3a6627d094'}
SCENARIOS={
'387':'Readiness returns HTTP 200; SQL shows revision 20260930_17, one Alembic version row, and zero Skill rows.',
'388':'Skills catalog HTTP response reflects the persisted synthetic Skill row.',
'397':'Publish with a valid-semver 33-character version is rejected with HTTP 422 and correlated validation audit.',
'403':'Readiness returns HTTP 200 at revision 20260930_18 with 42 schema columns; this screenshot does not establish historical row preservation.',
'402':'Injected status-audit failure rolls back state, then retry is recorded successfully.',
'404':'Skill status endpoint persists the transition and successful status audit.',
'405':'Authorized root resolution returns the closed response; denial does not read unauthorized content; missing auth challenges Bearer.',
'331-validation-child':'Syntactically valid 33-character version path is rejected with correlated terminal 422 audit.',
'406':'One request checks 16 direct dependencies with one real credential-verifier call and direct grants.',
'407':'Pinned lifecycle resume/deactivation/reactivation and grant revocation are exercised across real requests.',
'409':'Demo root hidden until direct dependency grant; three correlated instruction-free audit records.'}
HTTP={'status','request_id','retryable','allowlisted_fields','www_authenticate','credential_verifier_calls','dependency_count','publish_status','denied_status','unauthorized_content_selects','before_dependency_grant_status','pre_deactivation_status','lifecycle_status_write','retry_status','rollback_status_unchanged','status_sequence','resolution_count','request_ids','unauthenticated_status','unauthenticated_challenge'}
SQL={'audit_rows_correlated','audit_rows_total','audit_status','audit_outcome','audit_reason','failed_audit_rows','retry_audit_rows','status_after_retry','skill_rows','grant_rows','status_rows','content_selects','dependency_content_selects','migration_heads','schema_columns','audit_events_without_content','resolution_audit_rows','audit_instruction_matches','active_grant_rows','migration_revision','successful_status_audit_rows'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--probe-command',required=True);a=p.parse_args()
 d=json.loads(Path(a.input).read_text())
 required={'slice','tested_sha','observed_at_utc','http','sql','probe_command'}
 if set(d)!=required: raise SystemExit('refusing unexpected/missing probe fields')
 if d['slice'] not in HEADS or d['tested_sha']!=HEADS[d['slice']]: raise SystemExit('refusing unrecognized/mismatched candidate SHA')
 if not isinstance(a.probe_command,str) or not a.probe_command.startswith('docker compose '): raise SystemExit('missing Docker Compose reproduction provenance')
 if set(d['http'])-HTTP or set(d['sql'])-(SQL|{'statement_categories'}): raise SystemExit('refusing field outside evidence allowlist')
 raw=json.dumps(d,sort_keys=True)
 if re.search(r'(?i)(bearer\s+\S+|api[_ -]?key|password|secret|authorization:|prompt|instructions|postgres(?:ql)?://|/home/|/tmp/)',raw): raise SystemExit('refusing possible credentials, payload/instructions or private path')
 out={'slice':d['slice'],'tested_sha':d['tested_sha'],'observed_at_utc':d['observed_at_utc'],'probe_command':a.probe_command,'scenario':SCENARIOS[d['slice']], 'http':d['http'],'sql':{k:v for k,v in d['sql'].items() if k in SQL}}
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(out,sort_keys=True)+'\n')
 print('allowlisted only values from executed probe JSON; scenario is explanatory text')
if __name__=='__main__':main()
