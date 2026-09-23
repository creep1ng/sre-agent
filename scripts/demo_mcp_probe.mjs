// Boundary probe for Grafana MCP (issue #186, CA5). Runs inside the harness
// container, on the project's own network. Every attempt must fail: by name,
// and by each address the MCP holds on the demo networks (MCP_IPS).
const targets = ["grafana-mcp", ...(process.env.MCP_IPS ?? "").split(/\s+/).filter(Boolean)];
let reached = 0;
for (const host of targets) {
  const url = `http://${host}:8000/healthz`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    reached += 1;
    console.log(`REACHED ${url} -> HTTP ${res.status}`);
  } catch (err) {
    console.log(`BLOCKED ${url} -> ${err.cause?.code ?? err.name}`);
  }
}
console.log(reached === 0 ? "OK the harness cannot reach Grafana MCP" : "FAIL the harness reached Grafana MCP");
process.exit(reached === 0 ? 0 : 1);
