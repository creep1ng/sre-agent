# Tasks: The core depends on ports (#1023)

## 1. Decision (the first two pull requests)

- [x] 1.1 ADR-009: core, ports, adapters, transactions, published names, a home for every module
- [ ] 1.2 Contracts: every core unit on the ADR's list, exceptions listed, `cli` forbidden and
  bound by the composition-root contract
- [ ] 1.3 Show a red `lint-imports` on a local branch: `import sqlalchemy` in a new `triage` and
  `chat` module, `sre_agent.cli` imported from `triage`, `sre_agent.application` from `cli`

## 2. Ports and moves (later layers, one pull request each)

- [ ] 2.1 Indicators for environment reads outside settings and for contract coverage
- [ ] 2.2 `incident/persistence.py` to `incident/ports.py`
- [ ] 2.3 Audit ports: `AuditStore` to `governance/ports.py`, the stores to `persistence/audit.py`,
  `AuditProjector` to `governance/audit.py`
- [ ] 2.4 `settings.py` without the investigator; the investigator's client to `gateway/adapters/`
- [ ] 2.5 Triage on a unit of work; its SQL to `persistence/triage.py`, `triage_unit.py`
- [ ] 2.6 Telegram's process to `cli/`; chat renderers, outbox, delivery, taps, decisions and
  digest on ports and units of work; Telegram settings
- [ ] 2.7 `bok` retrieval to `gateway/http/`; its SQL and version rules to `persistence/bok.py`
- [ ] 2.8 Seeds to `cli/`, their settings to `seed_settings.py`
- [ ] 2.9 Executor: journal, decision without `Request`, container-engine port, settings
- [ ] 2.10 `gateway/`: ports and outbound adapters, SQL to `persistence/`, then `usecases/` and
  `http/` by whole-module moves
- [ ] 2.11 `create_application` over a container built once
- [ ] 2.12 `docs/architecture.md` describes the boundary and its checklist
- [ ] 2.13 Sweep of `#NNN` references in `src/`, one layer per package group
