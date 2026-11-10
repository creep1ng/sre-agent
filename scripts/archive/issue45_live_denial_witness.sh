#!/bin/bash
set -Eeuo pipefail
# Dedicated-host evidence runner for the current-main issue #45 gateway probe.
# Requires the pinned isolated OTel demo, gateway Compose stack and private .env.
# It publishes only metadata and safe counts; raw packets and credentials are never logged.
cd /opt/sre-agent
export DEMO_STATE_DIR=/opt/sre-agent/.demo-state
set -a; source .env; set +a
install -d -m 0700 /opt/issue45-private /opt/issue45-evidence
install -d -m 0755 /opt/issue45-evidence-stage
cat > /opt/issue45-private/direct_capture.py <<'PY'
import json,signal,socket,struct,sys
bridge,src_ip,dst_ip=sys.argv[1:4]
seen=set()
packets=0
running=True
def stop(*_):
 global running
 running=False
signal.signal(signal.SIGUSR1,stop)
sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3))
# Receive on all host interfaces; Docker forwards peer traffic on veth, not the bridge device.
sock.settimeout(0.25)
while running:
 try: frame=sock.recv(4096)
 except socket.timeout: continue
 if len(frame)<54 or frame[12:14]!=b'\x08\x00': continue
 ip=frame[14:]
 ihl=(ip[0]&15)*4
 if len(ip)<ihl+20 or ip[9]!=6: continue
 if socket.inet_ntoa(ip[12:16])!=src_ip or socket.inet_ntoa(ip[16:20])!=dst_ip: continue
 tcp=ip[ihl:]
 src_port,dst_port,sequence=struct.unpack('!HHI',tcp[:8])
 if dst_port!=8000: continue
 offset=(tcp[12]>>4)*4
 if len(tcp)<offset: continue
 payload=tcp[offset:]
 packets+=1
 if payload.startswith(b'POST /mcp HTTP/'):
  seen.add((src_port,dst_port,sequence))
sock.close()
print(json.dumps({'schema':'sre-agent.issue45.direct-mcp-http-count/v1','transport':'unmodified_api_to_mcp_bridge','http_post_attempts':len(seen),'filtered_tcp_packets':packets,'source_ip':src_ip,'destination_ip':dst_ip},sort_keys=True))
PY
chmod 0600 /opt/issue45-private/direct_capture.py
test "$(sha256sum scripts/demo_mcp_gateway_probe.mjs | cut -d' ' -f1)" = '242f5d9ac3e105158a89e803e349ae4e52e34986d2e2559791a6d48d8ae4771b'
network_id=$(docker network inspect -f '{{.Id}}' sre-mcp-boundary)
bridge=br-${network_id:0:12}
api_ip=$(docker inspect -f '{{(index .NetworkSettings.Networks "sre-mcp-boundary").IPAddress}}' issue45-gateway-api-1)
mcp_ip=$(docker inspect -f '{{(index .NetworkSettings.Networks "sre-mcp-boundary").IPAddress}}' grafana-mcp)
test -n "$api_ip" && test -n "$mcp_ip"
coord="$(mktemp -d /opt/issue45-private/http-denial.XXXXXX)"
chown 1000:1000 "$coord"; chmod 0700 "$coord"
CAP=''
cleanup(){
  if test -n "$CAP"; then kill -USR1 "$CAP" >/dev/null 2>&1 || true; wait "$CAP" >/dev/null 2>&1 || true; fi
  rm -rf "$coord" "${stage:-}"
}
trap cleanup EXIT
cat > "$coord/coordinated.mjs" <<'JS'
import {access,writeFile} from 'node:fs/promises';
import {runDiscovery} from '/source/scripts/demo_mcp_gateway_probe.mjs';
const originalFetch=globalThis.fetch;
const restrictedToken=process.env.RESTRICTED_HARNESS_API_KEY;
let intercepted=0;
async function awaitMarker(marker){
  const deadline=Date.now()+60000;
  while(Date.now()<deadline){
    try{await access('/source/barrier/'+marker);return;}catch{await new Promise(resolve=>setTimeout(resolve,100));}
  }
  throw new Error('barrier_timeout_'+marker);
}
globalThis.fetch=async(input,options={})=>{
  if(options.method==='POST' && String(input).endsWith('/v1/mcp/tools/query_prometheus') &&
     options.headers?.Authorization===`Bearer ${restrictedToken}`){
    intercepted++;
    await writeFile('/source/barrier/ready','1');
    await awaitMarker('go');
    const response=await originalFetch(input,options);
    await writeFile('/source/barrier/denied-done','1');
    await awaitMarker('ack');
    return response;
  }
  return originalFetch(input,options);
};
const report=await runDiscovery({gatewayUrl:'http://api:8000',humanToken:process.env.DEMO_HUMAN_API_KEY,restrictedToken});
process.stdout.write(JSON.stringify(report)+'\n');
process.exitCode=intercepted===1 && report.status==='pending' ? 0 : 1;
JS
chmod 0644 "$coord/coordinated.mjs"
set +e
docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml run --pull never --rm --no-deps -e DEMO_HUMAN_API_KEY -e RESTRICTED_HARNESS_API_KEY -v "$coord:/source/barrier:rw" -v "$coord/coordinated.mjs:/source/coordinated.mjs:ro" harness node /source/coordinated.mjs > /opt/issue45-evidence/main-http-pending.json 2>/var/log/issue45-main-http-stderr.log &
probe_pid=$!
set -e
wait_marker(){
  local marker="$1"; local ready=0
  for i in $(seq 1 600); do
    if test -f "$coord/$marker"; then ready=1; break; fi
    if ! kill -0 "$probe_pid" 2>/dev/null; then break; fi
    sleep 0.1
  done
  test "$ready" -eq 1
}
start_capture(){
  local label="$1"
  python3 /opt/issue45-private/direct_capture.py "$bridge" "$api_ip" "$mcp_ip" > "/opt/issue45-evidence/main-http-$label-counter.json" &
  CAP=$!
  sleep 1
  kill -0 "$CAP"
}
finish_capture(){
  kill -USR1 "$CAP"
  wait "$CAP"
  CAP=''
}
if ! wait_marker ready; then echo barrier_ready_missing; set +e; wait "$probe_pid"; set -e; exit 1; fi
start_capture denied
touch "$coord/go"
if ! wait_marker denied-done; then echo barrier_denied_done_missing; set +e; wait "$probe_pid"; set -e; exit 1; fi
finish_capture
start_capture positive
touch "$coord/ack"
set +e; wait "$probe_pid"; probe_rc=$?; set -e
finish_capture
printf 'probe_exit=%s\n' "$probe_rc"
test "$probe_rc" -eq 0
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/opt/issue45-evidence')
r=json.loads((p/'main-http-pending.json').read_text())
d=json.loads((p/'main-http-denied-counter.json').read_text())
c=json.loads((p/'main-http-positive-counter.json').read_text())
assert r['status']=='pending' and r['denied']['http_status']==403 and r['denied']['retryable'] is False
assert r['metric']['http_status']==200 and r['logs']['http_status']==200
assert d['http_post_attempts']==0 and c['http_post_attempts']>=1
w={'kind':'upstream-counter','source':'api-to-mcp-http-post-counter','request_id':r['denied']['request_id'],'before':0,'after':d['http_post_attempts']}
(p/'main-http-witness.json').write_text(json.dumps(w)+'\n')
print(json.dumps({'request_id':w['request_id'],'denied_http_post_attempts':d['http_post_attempts'],'positive_http_post_attempts':c['http_post_attempts'],'denied_filtered_tcp_packets':d['filtered_tcp_packets'],'positive_filtered_tcp_packets':c['filtered_tcp_packets'],'metric_status':r['metric']['http_status'],'log_status':r['logs']['http_status'],'restricted_discovery_status':r['restricted_discovery']['http_status'],'witness':w}))
PY
stage="$(mktemp -d /opt/issue45-evidence-stage/main-http.XXXXXX)"
chmod 0755 "$stage"
install -m 0644 /opt/issue45-evidence/main-http-pending.json "$stage/pending.json"
install -m 0644 /opt/issue45-evidence/main-http-witness.json "$stage/witness.json"
docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml run --pull never --rm --no-deps -v "$stage:/source/evidence:ro" harness node /source/scripts/demo_mcp_gateway_probe.mjs --reconcile /source/evidence/pending.json --witness /source/evidence/witness.json > /opt/issue45-evidence/main-http-final.json 2>/var/log/issue45-main-http-reconcile-stderr.log
cat /opt/issue45-evidence/main-http-final.json
rid="$(python3 -c 'import json; print(json.load(open("/opt/issue45-evidence/main-http-pending.json"))["denied"]["request_id"])')"
docker exec issue45-gateway-db-1 psql -U sre_agent -d sre_agent -Atc "select operation||':'||stage||':'||outcome||':'||response_status from audit_events where correlation->>'request_id'='${rid}'" | sed 's/^/audit=/'
