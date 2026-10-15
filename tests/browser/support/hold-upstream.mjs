// Test-only upstream between the web-held proxy and the API (#486): it holds the answer to an armed
// request until the test releases it, whole or cut. Playwright cannot route a SharedWorker.
import { createHash } from "node:crypto";
import { createServer, request } from "node:http";

const [host, port] = (process.env.HOLD_UPSTREAM_TARGET ?? "api:8000").split(":");
const digest = (value) => createHash("sha256").update(value).digest("hex");
const armed = [];
const held = new Map();

createServer((incoming, outgoing) => {
  const chunks = [];
  incoming.on("data", (chunk) => chunks.push(chunk));
  incoming.on("end", () => {
    const key = digest((incoming.headers.authorization ?? "").replace(/^Bearer /, ""));
    const path = incoming.url.split("?")[0];
    const index = armed.findIndex((rule) => rule.key === key && rule.path === path);
    const [rule] = index < 0 ? [] : armed.splice(index, 1);
    const { method, url, headers } = incoming;
    const forward = request({ host, port, method, path: url, headers }, (answer) => {
      const body = [];
      answer.on("data", (chunk) => body.push(chunk));
      answer.on("end", () => {
        const send = (cut) => {
          outgoing.writeHead(answer.statusCode, answer.headers);
          if (!cut) return outgoing.end(Buffer.concat(body));
          outgoing.write(Buffer.concat(body).subarray(0, 1), () => outgoing.destroy());
        };
        if (rule) held.set(rule.label, send);
        else send(false);
      });
    });
    forward.on("error", () => outgoing.destroy());
    forward.end(Buffer.concat(chunks));
  });
}).listen(8000);

// POST /hold {label, path, key} arms, POST /release {label, cut} answers; both list held labels.
createServer((incoming, outgoing) => {
  let text = "";
  incoming.on("data", (chunk) => (text += chunk));
  incoming.on("end", () => {
    const { label, path, key, cut } = text ? JSON.parse(text) : {};
    if (incoming.url === "/hold") armed.push({ label, path, key: digest(key) });
    if (incoming.url === "/release") held.get(label)?.(cut);
    if (incoming.url === "/release") held.delete(label);
    outgoing.writeHead(200, { "content-type": "application/json" });
    outgoing.end(JSON.stringify([...held.keys()]));
  });
}).listen(8001);
