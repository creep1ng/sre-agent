#!/bin/bash
set -Eeuo pipefail
# Run only on the dedicated, pinned OTel demo host with the gateway overlay active.
cd /opt/sre-agent
export DEMO_STATE_DIR=/opt/sre-agent/.demo-state
install -d -m 0700 /opt/issue45-evidence
mcp_ips="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' grafana-mcp)"
grafana_ips="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' grafana)"
host_ips='172.17.0.1'
for network in issue45-gateway_mcp-consumer issue45-gateway_runtime opentelemetry-demo; do
  host_ips="$host_ips $(docker network inspect "$network" --format '{{(index .IPAM.Config 0).Gateway}}')"
done
test -n "$mcp_ips" && test -n "$grafana_ips"
if test -n "$(docker port grafana-mcp 8000/tcp 2>/dev/null || true)"; then
  echo '{"status":"fail","failures":["published_mcp_port_present"]}'
  exit 1
fi
export MCP_IPS="$mcp_ips" GRAFANA_IPS="$grafana_ips" HOST_IPS="$host_ips"
docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml \
  run --pull never --rm --no-deps -e MCP_IPS -e GRAFANA_IPS -e HOST_IPS \
  harness node -e '
    const secretKeys=["MCP_GRAFANA_SERVER_TOKEN","GRAFANA_MCP_TOKEN","GRAFANA_API_KEY",
      "GRAFANA_SERVICE_ACCOUNT_TOKEN","OPENROUTER_API_KEY","AUDIT_HMAC_KEY"];
    const proxyKeys=["HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy"];
    const targets=[
      {kind:"mcp-name",url:"http://grafana-mcp:8000/healthz"},
      ...process.env.MCP_IPS.split(/\s+/).filter(Boolean).map(ip=>({kind:"mcp-ip",url:`http://${ip}:8000/healthz`})),
      {kind:"grafana-name",url:"http://grafana:3000/api/datasources"},
      ...process.env.GRAFANA_IPS.split(/\s+/).filter(Boolean).map(ip=>({kind:"grafana-ip",url:`http://${ip}:3000/api/datasources`})),
      ...process.env.HOST_IPS.split(/\s+/).filter(Boolean).map(ip=>({kind:"host-proxy",url:`http://${ip}:8090/grafana/api/datasources`})),
    ];
    async function reach(url){
      try {const r=await fetch(url,{redirect:"manual",signal:AbortSignal.timeout(1500)});
        await r.body?.cancel();return {reachable:true,http_status:r.status};}
      catch{return {reachable:false,http_status:null};}
    }
    const gateway=await reach("http://api:8000/health/ready");
    const results=await Promise.all(targets.map(async ({kind,url})=>({kind,...await reach(url)})));
    const providerTokenPresent=secretKeys.some(key=>Boolean(process.env[key]));
    const proxyEnvironmentPresent=proxyKeys.some(key=>Boolean(process.env[key]));
    const failures=[];
    if(gateway.http_status!==200)failures.push("gateway_unavailable");
    if(results.some(item=>item.reachable))failures.push("direct_or_proxy_route_reachable");
    if(providerTokenPresent)failures.push("provider_token_present");
    if(proxyEnvironmentPresent)failures.push("proxy_environment_present");
    const report={schema:"sre-agent.issue45.harness-boundary/v1",
      status:failures.length?"fail":"pass",failures,gateway_http_status:gateway.http_status,
      mcp_published_port:"absent",provider_token_present:providerTokenPresent,
      proxy_environment_present:proxyEnvironmentPresent,targets:results};
    process.stdout.write(JSON.stringify(report)+"\n");
    process.exitCode=failures.length?1:0;
  ' > /opt/issue45-evidence/harness-boundary-current-main.json
cat /opt/issue45-evidence/harness-boundary-current-main.json
