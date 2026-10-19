# Web proxy read timeout for the investigation run start

Starting an investigation run (`POST /api/v1/incidents/{id}/runs`, the war room's
"start investigation" since #651) answers only after the governed investigation: live runs
with `deepseek/deepseek-v4.1-flash` took 30-105 s on 2026-10-19. nginx's default 60 s
`proxy_read_timeout` answered 504 to the browser for the slow ones.

Controlled upstream (a container that answers every request after 75 s), both web images on
the same Docker network, one request each at the same time (2026-10-19 04:39Z):

```text
sre-agentic-web-old POST /api/v1/incidents/inc-demo/runs -> HTTP 504 after 60.058917s
sre-agentic-web-new POST /api/v1/incidents/inc-demo/runs -> HTTP 201 after 75.045859s
```

`web-old` is the image of `b822e08` (main); `web-new` adds `proxy_read_timeout 360s` to
`/api/`. 360 s covers the investigator's own bound (six model turns of at most 45 s plus
their 10 s tool calls).

Real stack, same patched image: the war room started `run_27b087a2c2f431c0` for
`inc-e13af17ebe5bf75babfe6674bcdd9db2` through the proxy; the browser received 201 after
53.6 s and the view shows the run in `Mitigando` with the proposed mitigation waiting for a
decision (`war-room-start-through-proxy.png`).
