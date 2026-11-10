#!/bin/bash
set -Eeuo pipefail
cd /opt/sre-agent
set -a; source .env; set +a
install -d -m 0700 /opt/issue45-private /opt/issue45-evidence
network_id=$(docker network inspect -f '{{.Id}}' sre-mcp-boundary)
bridge=br-${network_id:0:12}
api_ip=$(docker inspect -f '{{(index .NetworkSettings.Networks "sre-mcp-boundary").IPAddress}}' issue45-gateway-api-1)
mcp_ip=$(docker inspect -f '{{(index .NetworkSettings.Networks "sre-mcp-boundary").IPAddress}}' grafana-mcp)
endpoint=$(docker inspect -f '{{json .Config.Env}}' issue45-gateway-api-1 | python3 -c 'import json,sys; e=dict(x.split("=",1) for x in json.load(sys.stdin) if "=" in x); print(e.get("GRAFANA_MCP_ENDPOINT"))')
test "$endpoint" = 'http://grafana-mcp:8000/mcp'
test -n "$api_ip" && test -n "$mcp_ip"
test "$(docker inspect -f '{{.State.Status}}' grafana-mcp)" = running
# Force a fresh MCP session, then confirm the API is healthy before the first real call.
docker restart issue45-gateway-api-1 >/dev/null
for attempt in $(seq 1 30); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' issue45-gateway-api-1)" = healthy ]; then break; fi
  sleep 1
done
test "$(docker inspect -f '{{.State.Health.Status}}' issue45-gateway-api-1)" = healthy
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
capture() {
  local label="$1"
  python3 /opt/issue45-private/direct_capture.py "$bridge" "$api_ip" "$mcp_ip" > "/opt/issue45-evidence/direct-${label}-counter.json" &
  CAP=$!
  sleep 1
  kill -0 "$CAP"
}
finish_capture() {
  kill -USR1 "$CAP"
  wait "$CAP"
  cat "/opt/issue45-evidence/direct-$1-counter.json"
}
cleanup() {
  docker unpause grafana-mcp >/dev/null 2>&1 || true
  if [ -n "${CAP:-}" ]; then kill -USR1 "$CAP" >/dev/null 2>&1 || true; wait "$CAP" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
capture positive
python3 - <<'PY'
import json,os,urllib.error,urllib.request
payload={'datasource_uid':'webstore-metrics','expr':'count(traces_span_metrics_calls_total)','query_type':'instant','end_time':'now'}
req=urllib.request.Request('http://127.0.0.1:18000/v1/mcp/tools/query_prometheus',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['DEMO_HUMAN_API_KEY'],'Content-Type':'application/json'},method='POST')
try:
 with urllib.request.urlopen(req,timeout=40) as response: status=response.status; raw=response.read()
except urllib.error.HTTPError as error:
 status=error.code; raw=error.read()
obj=json.loads(raw)
report={'status':status,'result_type':obj.get('result_type'),'result_count':len(obj.get('result',[])) if isinstance(obj.get('result'),list) else None}
print(json.dumps({'positive_gateway':report}))
assert status==200 and report['result_type']=='vector' and report['result_count']>0
PY
finish_capture positive
CAP=
python3 - <<'PY'
import json
from pathlib import Path
report=json.loads(Path('/opt/issue45-evidence/direct-positive-counter.json').read_text())
assert report['http_post_attempts']>=1, 'capture blind: positive control saw no direct POST'
PY
docker pause grafana-mcp >/dev/null
capture timeout
python3 - <<'PY'
import json,os,time,urllib.error,urllib.request
from pathlib import Path
payload={'datasource_uid':'webstore-metrics','expr':'count(traces_span_metrics_calls_total)','query_type':'instant','end_time':'now'}
req=urllib.request.Request('http://127.0.0.1:18000/v1/mcp/tools/query_prometheus',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['DEMO_HUMAN_API_KEY'],'Content-Type':'application/json'},method='POST')
start=time.monotonic()
try:
 with urllib.request.urlopen(req,timeout=40) as response: status=response.status; raw=response.read()
except urllib.error.HTTPError as error:
 status=error.code; raw=error.read()
obj=json.loads(raw)
report={'status':status,'error_code':(obj.get('error') or {}).get('code'),'request_id':obj.get('request_id'),'elapsed_seconds':round(time.monotonic()-start,2),'normalized_keys':sorted(obj),'secret_present':os.environ['DEMO_HUMAN_API_KEY'].encode() in raw,'raw_body_fields_present':any(k in obj for k in ('body','result','content','traceback','stacktrace'))}
Path('/opt/issue45-evidence/direct-timeout-gateway.json').write_text(json.dumps(report)+'\n')
print(json.dumps({'timeout_gateway':report}))
assert status==504 and report['error_code']=='upstream_timeout' and not report['secret_present'] and not report['raw_body_fields_present']
PY
finish_capture timeout
CAP=
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/opt/issue45-evidence')
positive=json.loads((p/'direct-positive-counter.json').read_text())
timeout=json.loads((p/'direct-timeout-counter.json').read_text())
assert positive['http_post_attempts']>=1
assert timeout['http_post_attempts']==1, timeout['http_post_attempts']
print(json.dumps({'direct_count_assertion':'pass','positive_post_attempts':positive['http_post_attempts'],'timeout_post_attempts':timeout['http_post_attempts']}))
PY
docker unpause grafana-mcp >/dev/null
python3 scripts/demo_env.py verify >/var/log/issue45-direct-verify.log 2>&1
printf 'demo_verify=pass\n'
trap - EXIT
