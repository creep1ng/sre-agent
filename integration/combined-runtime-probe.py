"""Controlled integration: real PostgreSQL, synthetic incident, trusted internal actor.
No API credential, external provider, HTTP command route or remediation is exercised.
"""
import asyncio
from datetime import UTC, datetime
import json
import os
import time
import psycopg
from alembic import command
from alembic.config import Config
from sre_agent.incident.commands import HumanCommand, resolve
from sre_agent.incident.projections import project_run_state
from sre_agent.incident.runtime import ActorReference, IncidentRuntime, RunStart
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

url = os.environ['TEST_DATABASE_URL']
for _ in range(90):
    try:
        with psycopg.connect(url):
            break
    except psycopg.OperationalError:
        time.sleep(0.5)
else:
    raise SystemExit('Isolated database unavailable')
config = Config('/repo/alembic.ini')
config.set_main_option('sqlalchemy.url', url)
command.upgrade(config, 'head')

async def scenario():
    now = datetime(2026,9,29,4,0,tzinfo=UTC)
    incident_id = 'inc-integration-triage'
    actor = ActorReference(principal_id='integration-operator', display_name='Synthetic operator')
    workflow = load_incident_workflow('/repo/agent/workflows/incident-response.yaml')
    database = Database(url)
    def runtime(db):
        return IncidentRuntime(workflow, lambda: PostgresIncidentUnitOfWork(db), clock=lambda: now)
    state = {'workflow_id':'incident-response','workflow_version':'1.0.0','state':'detected','severity':None,'impact':None,'alert':None,'hypotheses':[],'evidence':[],'mitigation_strategy':None,'postmortem':None,'approvals':[],'updated_at':now.isoformat()}
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(incident_id, state, now=now)
    start = RunStart(command_id='integration-start',incident_id=incident_id,objective='triage',actor='human',actor_reference=actor)
    opened = await runtime(database).start_run(start)
    again = await runtime(database).start_run(start)
    assert again.replayed and again.run.run_id == opened.run.run_id
    human = HumanCommand(command_id='integration-declare',incident_id=incident_id,run_id=opened.run.run_id,command='propose_disposition',actor_reference=actor,disposition='declare',comment='Synthetic integration acceptance only.',inputs={'severity':'sev2'})
    result = await runtime(database).execute(resolve(human))
    duplicate = await runtime(database).execute(resolve(human))
    assert duplicate.replayed and result.incident.state['state'] == 'active'
    async with PostgresIncidentUnitOfWork(database) as work:
        ids = await work.runs.list_ids(incident_id)
        events = await work.events.list_after(opened.run.run_id,sequence=-1,limit=10)
        decision = await work.decisions.get(result.events[-1].payload['decision_id'])
    assert len(ids) == 1 and len(events) == 2
    assert decision.document['comment'] == human.comment
    assert decision.document['approval'] is None
    assert decision.document['actor_reference']['principal_id'] == actor.principal_id
    projection = project_run_state(result.run,workflow,event_sequence=events[-1].sequence)
    assert projection['cursor'] == 'seq:1' and projection['current_state'] == 'active'
    await database.dispose()
    restarted = Database(url)
    reconstructed = await runtime(restarted).reconstruct(incident_id,opened.run.run_id)
    assert reconstructed.incident_state == result.incident.state
    assert reconstructed.run_state == result.run.state
    await restarted.dispose()
    print(json.dumps({'proof_kind':'controlled real-PostgreSQL internal-service integration','start_retry_replayed':again.replayed,'human_command_retry_replayed':duplicate.replayed,'run_count':len(ids),'event_count':len(events),'decision_comment_preserved':True,'nonapproval_has_no_approval':True,'trusted_actor_preserved':True,'projected_cursor':projection['cursor'],'final_state':projection['current_state'],'new_database_handle_reconstruction_equal':True,'live_provider_used':False,'http_authorization_proven':False},indent=2))
asyncio.run(scenario())
