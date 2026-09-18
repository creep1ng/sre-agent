# Demo environment signals

How the declared failure, `paymentUnreachable`, shows in the metrics, logs and
traces of the pinned OpenTelemetry Demo, how to read each signal, how to reach
the cause and how to confirm recovery. Issue: #186 (CA6). Operating the
environment is covered in [demo-env.md](demo-env.md).

## How to read them

The signals are read through Grafana MCP, the path the harness will use through
the gateway (#187):

| Signal | MCP tool | Grafana datasource |
|---|---|---|
| Metrics | `query_prometheus` | `webstore-metrics` (Prometheus) |
| Logs | `query_elasticsearch`, index `otel-logs-*` | `webstore-logs` (OpenSearch) |
| Traces | none | opened in the Jaeger UI from a `trace_id` |

The MCP has no Jaeger tool and does not query traces. A trace is opened by a
person, or a later tool, from the `trace_id` that a log carries.

`scripts/demo_signals.py` runs the queries below for one window and prints only
counts, status codes and trace ids:

    docker run --rm -i --network opentelemetry-demo \
      --env-file .demo-state/grafana-mcp.env -e LABEL=now \
      python:3.12-slim python - < scripts/demo_signals.py

The same queries work in Grafana Explore, under `http://localhost:8090/grafana`.

## Window

Span metrics come from the Collector's span metrics connector and reach
Prometheus about once a minute. Every query uses a two-minute window
(`increase(...[2m])` for metrics, `now-2m` to `now` for logs), read at least
150 seconds after `fail` or `reset` so that the window holds one state only.

## Metrics

| Question | PromQL |
|---|---|
| Which services fail | `sum by (service_name) (increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR", service_name=~"frontend-proxy\|frontend\|checkout\|payment"}[2m]))` |
| Where in checkout | `sum by (span_name) (increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR", service_name="checkout"}[2m]))` |

Measured on the reference host, error calls per two-minute window:

| State | checkout | frontend | frontend-proxy | payment |
|---|---|---|---|---|
| Baseline | 0 | 0 | 0 | 0 to 2 |
| Failure on | 12 | 24 to 32 | 12 | 0 |
| After `reset` | 0 | 0 | 0 | 0 |

Inside checkout the errors fall on `oteldemo.CheckoutService/PlaceOrder` and on
its client call `oteldemo.PaymentService/Charge`, in equal numbers. `payment`
records no errors of its own while the flag is on: checkout never reaches it.
The occasional baseline errors in `payment` are unrelated to this failure.

## Logs

**checkout does not log the failure.** When the charge fails it returns the
error to its caller without writing a log. Its logs are `INFO` and mark the
stages of an order, each with the order's `traceId`:

| Stage | Log body |
|---|---|
| Order received | `[PlaceOrder]` |
| Charge accepted | `payment went through` |
| Order completed | `order placed` |

The signal is an order that starts and never completes: a `traceId` with
`[PlaceOrder]` and no `order placed`.

| Question | Query on `otel-logs-*` |
|---|---|
| Order stages in checkout | `resource.service.name:checkout` |
| Checkout requests at the proxy | `resource.service.name:"frontend-proxy" AND body:*checkout*` |

The proxy access log body holds the request line and the response code, as in
`"POST /api/checkout HTTP/1.1" 500`.

Measured on the reference host, per two-minute window:

| State | `[PlaceOrder]` | `payment went through` | `order placed` | Proxy `POST` checkout |
|---|---|---|---|---|
| Baseline | 7 | 7 | 7 | 7 answered 200 |
| Failure on | 4 to 5 | 0 | 0 | 3 to 5 answered 500 |
| After `reset` | 5 to 6 | 5 | 5 | 5 to 6 answered 200 |

**Noise to ignore.** `severity.text:ERROR` returns about fifty logs per window
from `otelcol-contrib` in every state: the Collector's Kafka and PostgreSQL
receivers have no target in the minimal profile. They say nothing about this
failure.

## Traces

Each stalled order's `traceId` opens its trace in the Jaeger UI at
`http://localhost:8090/jaeger/ui/trace/` followed by the id. The trace shows the
`PaymentService/Charge` call in error under `PlaceOrder`, which carries the
error that checkout returns, `failed to charge card: ...` in the checkout source.

## Diagnosis

1. **Symptom.** Checkout requests answer 500 at the proxy, and `frontend-proxy`
   records error calls.
2. **Locate.** `frontend` and `checkout` record error calls; inside checkout they
   are `PlaceOrder` and `PaymentService/Charge` in equal numbers, and `payment`
   records none. The call from checkout to payment fails before reaching it.
3. **Confirm in the logs.** Orders reach `[PlaceOrder]` and never
   `payment went through`.
4. **Detail.** Open one stalled order's trace in Jaeger.
5. **Cause in this environment.** The flag `paymentUnreachable`, served by flagd
   from `.demo-state/flagd/demo.flagd.json`.

## Recovery

Run `python scripts/demo_env.py reset`, wait 150 seconds and read again: error
calls drop to zero, orders reach `order placed` and the proxy answers 200.

An order still in flight at the edge of the window can show `[PlaceOrder]`
without `order placed`; the reference run saw one after a `reset`. The failure
shows as several such orders together with 500s at the proxy and error calls in
checkout, never as one order alone.

## Mapping to the incident signal

`agent/signals/otel-mapping.yaml` (#149) maps an error span to a canonical alert.
For this failure the fields come from the checkout `PlaceOrder` span:

| Span field | Alert field | Value here |
|---|---|---|
| `resource.attributes[service.name]` | `alert.service` | `checkout` |
| `span.name` | `alert.origin.signal` | `oteldemo.CheckoutService/PlaceOrder` |
| `span.status.message` | `alert.origin.condition` | the error checkout returns |
| `span.timestamp` | `alert.observed_at` | the span time |

`trace_id` and `span_id` travel in the correlation envelope, never in the alert.
This guide does not wire the adapter; that integration depends on #149.
