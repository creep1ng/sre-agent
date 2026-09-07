# ADR-008: Cursor-Based Polling for the Delivery of Execution Events

Status: Accepted

Location: docs/adrs/, not in schemas/adrs/. This decision pertains to the Incident Execution API (HT-INC-04), not to the set of frozen gateway contracts.

## Context

The operations user interface must track the progress of an investigation as evidence is collected, hypotheses are formulated, and authorizations are requested over the course of seconds or minutes.

HT-INC-04 must determine how the user interface receives these updates, whether it fetches them via polling or whether the server sends them through a persistent connection using Server-Sent Events (SSE).

Two factors limit this choice. The gateway's response contract is explicitly designed not to be streaming-based, so the rest of the platform deliberately avoids real-time streams. Furthermore, the execution API already exposes GET .../events with "order, cursor, or resume" based on the cursor in its acceptance criteria, which in itself constitutes a retrieval model.

## Decision: Use the polling approach for the MVP, with the door open to SSE

Execution events are delivered via cursor-based polling through GET .../events. The endpoint returns events based on a cursor provided by the requester; the user interface polls at its own interval and advances the cursor. No persistent connection or SSE endpoint is defined.

## Implications

The events endpoint already required by the API becomes the sole delivery mechanism, so no additional contract surface is introduced. The model remains consistent with the non-streaming gateway. The user interface controls its own refresh rate and survives disconnection by resuming from the last cursor. The cost is limited latency (up to one polling interval) and an empty poll.
