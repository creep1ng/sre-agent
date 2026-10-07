# 2.6.0 additive publication

Release 2.6.0 is additive over immutable 2.5.0. It publishes the already delivered `POST /v1/grants` 404 `resource_not_found` response for missing or inactive grant principals and resources, matching the sibling missing-dependency routes. It preserves prior schemas and consumers; no new envelope or error code was introduced.
