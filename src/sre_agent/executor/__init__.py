"""The deploy-executor: named operations over docker-socket-proxy (HT-EXEC-SERVICE, #720).

A separate process from the gateway, served from the same image. It reaches
only the Docker Engine API through the socket proxy and never imports the
incident, governance, persistence or gateway packages: the grant, the audit
and the approval live in the gateway; the executor only executes what its
catalog names, after validating everything it can before the first write.
"""
