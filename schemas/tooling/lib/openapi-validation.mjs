import { spawnSync } from "node:child_process";
import { constants } from "node:fs";
import { access, lstat, mkdir, readFile, readdir, realpath, rm, stat, writeFile } from "node:fs/promises";
import { basename, dirname, extname, isAbsolute, join, relative, resolve, win32 } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseDocument } from "yaml";
const toolingRoot = fileURLToPath(new URL("../", import.meta.url)), schemaRoot = resolve(toolingRoot, ".."), config = join(toolingRoot, "redocly.yaml"), redocly = join(toolingRoot, "node_modules/@redocly/cli/bin/cli.js");
const API_NAMES = new Set(["control-plane", "responses"]);
const SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const inside = (root, target) => { const path = relative(root, target); return path === "" || (!path.startsWith("..") && !isAbsolute(path)); };
export function parseContractSource(source, extension = ".yaml") {
  const document = parseDocument(source, { strict: true, uniqueKeys: true }), problems = [...document.errors, ...document.warnings];
  if (problems.length) throw new Error(`Parse failed: ${problems.map(({ message }) => message).join("; ")}`);
  try { const value = document.toJS({ maxAliasCount: 0 }); return extension.toLowerCase() === ".json" ? JSON.parse(source) : value; } catch (error) { throw new Error(`Parse failed: ${error.message}`); }
}
async function checkedFile(path, root, label) {
  const lexical = resolve(path); if (!inside(root, lexical)) throw new Error(`${label} escapes approved root`);
  let actual; try { actual = await realpath(lexical); } catch { throw new Error(`${label} is missing`); }
  if (!inside(root, actual)) throw new Error(`${label} realpath escape rejected`);
  const metadata = await stat(actual); if (!metadata.isFile()) throw new Error(`${label} must be a regular file`); if (metadata.nlink !== 1) throw new Error(`${label} hard-link ambiguity rejected`);
  try { await access(actual, constants.R_OK); } catch { throw new Error(`${label} must be readable`); } return actual;
}
function locatorPath(locator) {
  if (typeof locator !== "string" || !locator) throw new Error("Locator must be a non-empty string");
  if (/^urn:sre-agent:schema:[a-z-]+:(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:#.*)?$/.test(locator)) return null;
  if (/[\x00-\x1f\x7f]/.test(locator)) throw new Error("Locator control character rejected");
  if (locator.includes("\\")) throw new Error("Locator backslash ambiguity rejected");
  const [path, ...fragments] = locator.split("#"); if (!path) return null;
  if (fragments.length > 1 || path.includes("?") || path.includes("%")) throw new Error("Locator encoding/query ambiguity rejected");
  if (path.startsWith("//")) throw new Error("Protocol-relative locator rejected");
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(path)) throw new Error("Locator URI scheme rejected");
  if (isAbsolute(path) || win32.isAbsolute(path)) throw new Error("Absolute locator rejected");
  if (path.split("/").includes("..")) throw new Error("Parent traversal locator rejected"); return path;
}
const mappingRef = (value) => typeof value === "string" && (value.startsWith("#") || /^(?:[A-Za-z][A-Za-z0-9+.-]*:|\.\.?\/)/.test(value) || value.includes("/") || /\.ya?ml$|\.json$/i.test(value.split("#")[0]));
function locators(value, found = []) {
  if (!value || typeof value !== "object") return found; if (Array.isArray(value)) { for (const item of value) locators(item, found); return found; }
  for (const [key, child] of Object.entries(value)) { if (["$ref", "externalValue", "operationRef", "defaultMapping"].includes(key) && typeof child === "string") found.push(child); if (key === "mapping" && value.propertyName && child && typeof child === "object") for (const item of Object.values(child)) if (mappingRef(item)) found.push(item); locators(child, found); } return found;
}
export async function preflightOpenapi(entry, root = schemaRoot) {
  const approved = await realpath(root), first = await checkedFile(entry, approved, "OpenAPI entry"), documents = new Map();
  async function visit(path) { if (documents.has(path)) return; const source = await readFile(path, "utf8"), value = parseContractSource(source, extname(path)); documents.set(path, value); for (const locator of locators(value)) { const local = locatorPath(locator); if (local) await visit(await checkedFile(resolve(dirname(path), local), approved, `Locator ${locator}`)); } }
  await visit(first); const document = documents.get(first); if (document?.openapi !== "3.1.0" || !SEMVER.test(document?.info?.version ?? "")) throw new Error("Entry must be OpenAPI 3.1.0 with a SemVer info.version"); return documents;
}
async function checkedOutput(output) {
  const temporary = join(toolingRoot, ".tmp"), target = resolve(output); if (dirname(target) !== temporary) throw new Error("Bundle output must be a direct child of schemas/tooling/.tmp");
  await mkdir(temporary, { recursive: true }); const temporaryInfo = await lstat(temporary); if (temporaryInfo.isSymbolicLink() || !temporaryInfo.isDirectory() || await realpath(temporary) !== temporary) throw new Error("Bundle output root symlink rejected");
  try { const targetInfo = await lstat(target); if (targetInfo.isSymbolicLink()) throw new Error("Bundle output symlink rejected"); if (!targetInfo.isFile()) throw new Error("Bundle output must be a regular file"); if (targetInfo.nlink !== 1) throw new Error("Bundle output hard-link rejected"); } catch (error) { if (error.code !== "ENOENT") throw error; } return target;
}
export function assertInvocation(result, operation) { if (result.error) throw new Error(`Redocly ${operation} failed to launch: ${result.error.message}`); if (result.status !== 0) throw new Error(`Redocly ${operation} failed (${result.status}):\n${result.stdout ?? ""}${result.stderr ?? ""}`); return `${result.stdout ?? ""}${result.stderr ?? ""}`; }
function invoke(args, runner) { return assertInvocation(runner(process.execPath, [redocly, ...args, `--config=${config}`], { cwd: toolingRoot, encoding: "utf8" }), args[0]); }
const rewriteUrns = (value, version) => JSON.parse(JSON.stringify(value, (key, item) => { const match = key === "$ref" && typeof item === "string" && new RegExp(`^urn:sre-agent:schema:([a-z-]+):${version.replaceAll(".", "\\.")}(.*)$`).exec(item); return match ? `./${match[1]}.schema.json${match[2]}` : item; }));
async function materializeRelease(entry, version) {
  await preflightOpenapi(entry); const name = basename(entry, extname(entry)), temporary = join(toolingRoot, `.tmp/${name}-${version}-resolved`), release = join(schemaRoot, `releases/${version}/json-schema`), approved = await realpath(schemaRoot); await rm(temporary, { recursive: true, force: true }); await mkdir(temporary, { recursive: true });
  for (const kind of ["domain", "http"]) for (const name of await readdir(join(release, kind))) if (name.endsWith(".schema.json")) { const file = await checkedFile(join(release, kind, name), approved, `Schema ${name}`); await writeFile(join(temporary, name), JSON.stringify(rewriteUrns(JSON.parse(await readFile(file, "utf8")), version))); }
  const target = join(temporary, `${name}.json`); await writeFile(target, JSON.stringify(rewriteUrns(await readContractFile(entry), version))); return target;
}
export async function runReleaseOpenapi(name, output, version = "1.0.0") { if (!API_NAMES.has(name) || !SEMVER.test(version)) throw new Error(`Unknown API or invalid release: ${name}/${version}`); const source = join(schemaRoot, `releases/${version}/openapi/${name}.yaml`), target = await checkedOutput(output); await rm(target, { force: true }); try { return await runOpenapi("bundle", await materializeRelease(source, version), target); } catch (error) { await rm(target, { force: true }); throw error; } }
export async function runOpenapi(mode, entry, output, runner = spawnSync) {
  if (!['lint', 'bundle'].includes(mode)) throw new Error("Mode must be lint or bundle"); const source = resolve(entry), target = mode === "bundle" ? await checkedOutput(output) : null;
  if (target) await rm(target, { force: true }); try { await preflightOpenapi(source); const logs = [invoke(["lint", source], runner)]; if (mode === "bundle") logs.push(invoke(["bundle", source, "-o", target], runner)); return logs.join(""); } catch (error) { if (target) await rm(target, { force: true }); throw error; }
}
export async function readContractFile(path) { return parseContractSource(await readFile(path, "utf8"), extname(path)); }
if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) { const [mode, entry, output, ...extra] = process.argv.slice(2); try { if (mode === "check" && entry === "--api" && output && !extra.length) process.stdout.write(await runReleaseOpenapi(output, join(toolingRoot, ".tmp", `${output}.yaml`))); else if (!entry || extra.length || (mode === "bundle") !== Boolean(output)) { console.error("Usage: node lib/openapi-validation.mjs lint <api> | bundle <api> <schemas/tooling/.tmp/output> | check --api <name>"); process.exitCode = 2; } else process.stdout.write(await runOpenapi(mode, entry, output)); } catch (error) { console.error(`OpenAPI tooling failed: ${error.message}`); process.exitCode = 1; } }
