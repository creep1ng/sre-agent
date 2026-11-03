import { PlusIcon, RefreshCwIcon, SearchIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import {
  adminApi,
  BOK_SLUG,
  SEMVER,
  type AdminError,
  type BoKChunk,
  type BoKDocument,
  type BoKSearchResult,
  type BoKVersion,
} from "@/lib/admin-api";
import { useAdminQuery, useRetryKey } from "./use-admin-query";
import { AdminPage, Empty, ErrorNote, Facts, Field, Mono, Panel, ROW, StatusBadge, TD, TH, Table } from "./ui";

const MAX_DOCUMENTS = 20;
const MAX_CHUNKS = 50;
const MAX_CHUNK = 4000;

/** `demo-incident-response@1.0.0` → its collection id and version. */
const split = (resourceId: string) => {
  const at = resourceId.lastIndexOf("@");
  return { collectionId: resourceId.slice(0, at), version: resourceId.slice(at + 1) };
};

/** "Rollback del checkout" → "rollback-del-checkout": the ids the publish route accepts. */
const slugify = (text: string) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);

const unique = (wanted: string, taken: Set<string>) => {
  let candidate = wanted;
  for (let n = 2; taken.has(candidate); n += 1) candidate = `${wanted}-${n}`;
  taken.add(candidate);
  return candidate;
};

/** Paragraphs packed into pieces of at most MAX_CHUNK characters; a longer paragraph is cut. */
const pack = (text: string) => {
  const pieces: string[] = [];
  let current = "";
  for (const paragraph of text.split(/\n\s*\n/)) {
    const next = current ? `${current}\n\n${paragraph}` : paragraph;
    if (next.length <= MAX_CHUNK) {
      current = next;
      continue;
    }
    if (current) pieces.push(current);
    current = paragraph;
    while (current.length > MAX_CHUNK) {
      pieces.push(current.slice(0, MAX_CHUNK));
      current = current.slice(MAX_CHUNK);
    }
  }
  if (current.trim()) pieces.push(current);
  return pieces;
};

/** A Markdown text as chunks: one section per heading, the text before the first one as `intro`. */
const toChunks = (body: string): BoKChunk[] => {
  const sections: { heading: string; lines: string[] }[] = [{ heading: "intro", lines: [] }];
  for (const line of body.split("\n")) {
    const heading = /^#{1,6}\s+(.+)$/.exec(line);
    if (heading) sections.push({ heading: heading[1], lines: [line] });
    else sections[sections.length - 1].lines.push(line);
  }
  const taken = new Set<string>();
  const chunks: BoKChunk[] = [];
  for (const section of sections) {
    const text = section.lines.join("\n").trim();
    if (!text) continue;
    const sectionId = unique(slugify(section.heading) || "section", taken);
    for (const content of pack(text)) chunks.push({ section_id: sectionId, chunk_index: chunks.length, content });
  }
  return chunks;
};

export function KnowledgePage() {
  const t = useT("admin");
  const collections = useAdminQuery(adminApi.listCollections, "collections");
  const [openId, setOpenId] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const items = collections.data?.items ?? [];

  return (
    <AdminPage
      title={t("knowledge.title")}
      lead={t("knowledge.lead")}
      actions={
        <>
          <Button variant="outline" onClick={collections.reload}>
            <RefreshCwIcon /> {t("common.refresh")}
          </Button>
          <Button onClick={() => setPublishing(true)}>
            <PlusIcon /> {t("knowledge.publish")}
          </Button>
        </>
      }
    >
      <Panel flush description={collections.data ? t("common.count", { count: items.length }) : undefined}>
        {collections.state.phase === "error" ? (
          <div className="px-6 py-5">
            <ErrorNote error={collections.state.error} onRetry={collections.reload} />
          </div>
        ) : !collections.data ? (
          <Empty>{t("common.loading")}</Empty>
        ) : items.length === 0 ? (
          <Empty>{t("knowledge.empty")}</Empty>
        ) : (
          <Table
            label={t("knowledge.title")}
            head={
              <>
                <th className={TH}>{t("knowledge.col.collection")}</th>
                <th className={TH}>{t("knowledge.col.version")}</th>
                <th className={TH}>{t("knowledge.col.status")}</th>
              </>
            }
          >
            {items.map((item) => {
              const { collectionId, version } = split(item.resource_id);
              return (
                <tr
                  key={item.resource_id}
                  data-clickable
                  data-collection-row={item.resource_id}
                  tabIndex={0}
                  aria-label={t("knowledge.open", { id: item.resource_id })}
                  onClick={() => setOpenId(item.resource_id)}
                  onKeyDown={(event) => event.key === "Enter" && setOpenId(item.resource_id)}
                  className={ROW}
                >
                  <td className={TD}>
                    <div>{item.discoverability?.display_name || collectionId}</div>
                    <Mono className="text-muted-foreground">{collectionId}</Mono>
                  </td>
                  <td className={TD}>
                    <Mono>{version}</Mono>
                  </td>
                  <td className={TD}>
                    <StatusBadge status={item.status} />
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Panel>

      <CollectionSheet resourceId={openId} onClose={() => setOpenId(null)} />
      <PublishDialog
        open={publishing}
        onOpenChange={setPublishing}
        onPublished={(collection) => {
          collections.reload();
          setOpenId(collection.resource_id);
        }}
      />
    </AdminPage>
  );
}

function CollectionSheet({ resourceId, onClose }: { resourceId: string | null; onClose: () => void }) {
  const t = useT("admin");
  const target = resourceId ? split(resourceId) : null;
  const detail = useAdminQuery(
    target ? () => adminApi.getCollection(target.collectionId, target.version) : null,
    `collection:${resourceId}`,
  );
  const record = detail.data?.resource_id === resourceId ? detail.data : null;

  return (
    <Sheet open={resourceId !== null} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader className="gap-2 px-6 pt-8">
          <div>{record && <StatusBadge status={record.status} />}</div>
          <SheetTitle className="font-display text-3xl font-light tracking-[-.015em]">
            {record?.display_name ?? resourceId}
          </SheetTitle>
          <SheetDescription asChild>
            <Mono className="text-muted-foreground">{resourceId}</Mono>
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-8 px-6 pb-8">
          {detail.state.phase === "error" ? (
            <ErrorNote error={detail.state.error} onRetry={detail.reload} />
          ) : !record ? (
            <p className="text-muted-foreground">{t("common.loading")}</p>
          ) : (
            <>
              {record.description && <p className="text-[15px] text-[var(--text-2)]">{record.description}</p>}
              <Facts
                rows={[
                  [t("knowledge.d.documents"), String(record.document_count)],
                  [t("knowledge.d.chunks"), String(record.chunk_count)],
                  [t("knowledge.d.owner"), <Mono>{record.owner_id}</Mono>],
                ]}
              />
              {target && <SearchBox key={resourceId} collectionId={target.collectionId} version={target.version} />}
              <section className="flex flex-col gap-4">
                <h3 className="font-mono text-[11px] tracking-[.08em] text-muted-foreground uppercase">{t("knowledge.d.content")}</h3>
                {(record.documents ?? []).map((document) => (
                  <article key={document.document_id} data-bok-document={document.document_id} className="flex flex-col gap-2">
                    <div>
                      <p className="font-medium">{document.title}</p>
                      <Mono className="text-muted-foreground">{document.source_ref}</Mono>
                    </div>
                    {[...document.chunks].sort((a, b) => a.chunk_index - b.chunk_index).map((chunk) => (
                      <div key={`${chunk.section_id}:${chunk.chunk_index}`} className="rounded-xl border bg-[var(--code)] px-4 py-3">
                        <Mono className="text-muted-foreground">
                          {chunk.section_id} · {chunk.chunk_index}
                        </Mono>
                        <p className="mt-1 text-[14px] leading-relaxed whitespace-pre-wrap">{chunk.content}</p>
                      </div>
                    ))}
                  </article>
                ))}
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** Searches as the agent would, with the session's own grant on this exact version. */
function SearchBox({ collectionId, version }: { collectionId: string; version: string }) {
  const t = useT("admin");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AdminError | null>(null);
  const [results, setResults] = useState<BoKSearchResult[] | null>(null);

  const search = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    const result = await adminApi.searchCollection(collectionId, version, query.trim());
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      setResults(null);
      return;
    }
    setResults(result.body.results);
  };

  return (
    <section className="flex flex-col gap-3">
      <h3 className="font-mono text-[11px] tracking-[.08em] text-muted-foreground uppercase">{t("knowledge.search")}</h3>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <Input
          id="bok-query"
          aria-label={t("knowledge.search")}
          autoComplete="off"
          maxLength={300}
          placeholder={t("knowledge.searchPlaceholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="submit" variant="outline" disabled={busy || !query.trim()}>
          <SearchIcon /> {t("knowledge.searchSubmit")}
        </Button>
      </form>
      {error === "forbidden" ? (
        <p role="alert" className="text-sm text-[var(--text-2)]">
          {t("knowledge.searchForbidden", { id: `${collectionId}@${version}` })}
        </p>
      ) : (
        error && <ErrorNote error={error} />
      )}
      {results &&
        (results.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("knowledge.noResults")}</p>
        ) : (
          <ol className="flex flex-col gap-2" data-bok-results>
            {results.map((hit) => (
              <li key={`${hit.document_id}:${hit.section_id}:${hit.chunk_index}`} className="rounded-xl border px-4 py-3">
                <p className="font-medium">
                  {hit.title} <Mono className="text-muted-foreground">· {hit.section_id}</Mono>
                </p>
                <p className="mt-1 line-clamp-3 text-[14px] text-[var(--text-2)]">{hit.content}</p>
              </li>
            ))}
          </ol>
        ))}
    </section>
  );
}

interface DraftDocument {
  title: string;
  source: string;
  body: string;
}

const EMPTY_DOCUMENT: DraftDocument = { title: "", source: "", body: "" };

function PublishDialog({
  open,
  onOpenChange,
  onPublished,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPublished: (collection: BoKVersion) => void;
}) {
  const t = useT("admin");
  const [collectionId, setCollectionId] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [drafts, setDrafts] = useState<DraftDocument[]>([EMPTY_DOCUMENT]);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<AdminError | "local" | null>(null);
  const [busy, setBusy] = useState(false);
  const retry = useRetryKey("bok-publish");

  const taken = new Set<string>();
  const documents: BoKDocument[] = drafts.map((draft) => ({
    document_id: unique(slugify(draft.title) || "document", taken),
    title: draft.title.trim(),
    source_ref: draft.source.trim() || "console",
    chunks: toChunks(draft.body),
  }));
  const docOk = (document: BoKDocument) =>
    document.title.length >= 1 && document.title.length <= 300 && document.chunks.length >= 1 && document.chunks.length <= MAX_CHUNKS;
  const ok = {
    id: BOK_SLUG.test(collectionId.trim()),
    version: SEMVER.test(version.trim()),
    name: name.trim().length >= 1 && name.trim().length <= 200,
    description: description.trim().length <= 500,
    documents: documents.every(docOk),
  };

  const update = (index: number, change: Partial<DraftDocument>) =>
    setDrafts((current) => current.map((draft, at) => (at === index ? { ...draft, ...change } : draft)));

  const close = (next: boolean) => {
    if (busy) return;
    if (!next) {
      setCollectionId("");
      setVersion("1.0.0");
      setName("");
      setDescription("");
      setDrafts([EMPTY_DOCUMENT]);
      setChecked(false);
      setError(null);
    }
    onOpenChange(next);
  };

  const submit = async () => {
    setChecked(true);
    if (!Object.values(ok).every(Boolean)) {
      setError("local");
      return;
    }
    const body = {
      collection_id: collectionId.trim(),
      version: version.trim(),
      display_name: name.trim(),
      description: description.trim(),
      documents,
    };
    setBusy(true);
    setError(null);
    const result = await adminApi.publishCollection(body, retry.keyFor(body));
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    retry.settle();
    toast.success(t("knowledge.published", { id: result.body.resource_id }));
    onPublished(result.body);
    close(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-normal">{t("knowledge.publish")}</DialogTitle>
          <DialogDescription>{t("knowledge.publishLead")}</DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {error === "local" ? (
            <p role="alert" className="text-sm text-critical">
              {t("knowledge.invalid")}
            </p>
          ) : error === "conflict" ? (
            <p role="alert" className="text-sm text-critical">
              {t("knowledge.conflict")}
            </p>
          ) : (
            error && <ErrorNote error={error} />
          )}
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_9rem]">
            <Field id="bok-id" label={t("knowledge.field.id")} hint={t("knowledge.field.idHint")}>
              <Input
                id="bok-id"
                className="font-mono"
                autoComplete="off"
                spellCheck={false}
                maxLength={100}
                placeholder="runbooks-checkout"
                aria-describedby="bok-id-hint"
                aria-invalid={checked && !ok.id}
                value={collectionId}
                onChange={(event) => setCollectionId(event.target.value)}
                autoFocus
              />
            </Field>
            <Field id="bok-version" label={t("knowledge.field.version")}>
              <Input
                id="bok-version"
                className="font-mono"
                autoComplete="off"
                spellCheck={false}
                maxLength={32}
                aria-invalid={checked && !ok.version}
                value={version}
                onChange={(event) => setVersion(event.target.value)}
              />
            </Field>
          </div>
          <Field id="bok-name" label={t("knowledge.field.name")}>
            <Input
              id="bok-name"
              autoComplete="off"
              maxLength={200}
              aria-invalid={checked && !ok.name}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field id="bok-description" label={t("knowledge.field.description")}>
            <Input
              id="bok-description"
              autoComplete="off"
              maxLength={500}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
          {drafts.map((draft, index) => {
            const document = documents[index];
            return (
              <fieldset key={index} className="grid gap-3 rounded-xl border px-4 py-4" data-bok-draft={index}>
                <div className="flex items-center justify-between">
                  <legend className="font-mono text-[11px] tracking-[.08em] text-muted-foreground uppercase">
                    {t("knowledge.document", { n: index + 1 })}
                  </legend>
                  {drafts.length > 1 && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={t("knowledge.removeDocument", { n: index + 1 })}
                      onClick={() => setDrafts((current) => current.filter((_, at) => at !== index))}
                    >
                      <XIcon />
                    </Button>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field id={`bok-doc-${index}-title`} label={t("knowledge.field.docTitle")}>
                    <Input
                      id={`bok-doc-${index}-title`}
                      autoComplete="off"
                      maxLength={300}
                      aria-invalid={checked && !document.title}
                      value={draft.title}
                      onChange={(event) => update(index, { title: event.target.value })}
                    />
                  </Field>
                  <Field id={`bok-doc-${index}-source`} label={t("knowledge.field.source")}>
                    <Input
                      id={`bok-doc-${index}-source`}
                      className="font-mono"
                      autoComplete="off"
                      maxLength={500}
                      placeholder="https://…/runbook.md"
                      value={draft.source}
                      onChange={(event) => update(index, { source: event.target.value })}
                    />
                  </Field>
                </div>
                <Field id={`bok-doc-${index}-body`} label={t("knowledge.field.body")} hint={t("knowledge.field.bodyHint")}>
                  <Textarea
                    id={`bok-doc-${index}-body`}
                    className="max-h-72 min-h-32 font-mono text-[13px]"
                    spellCheck={false}
                    aria-describedby={`bok-doc-${index}-body-hint`}
                    aria-invalid={checked && (document.chunks.length === 0 || document.chunks.length > MAX_CHUNKS)}
                    value={draft.body}
                    onChange={(event) => update(index, { body: event.target.value })}
                  />
                </Field>
                <p className="text-sm text-muted-foreground" data-bok-chunk-count={index}>
                  {t("knowledge.chunkCount", { count: document.chunks.length })}
                </p>
              </fieldset>
            );
          })}
          {drafts.length < MAX_DOCUMENTS && (
            <Button
              type="button"
              variant="outline"
              className="justify-self-start"
              onClick={() => setDrafts((current) => [...current, EMPTY_DOCUMENT])}
            >
              <PlusIcon /> {t("knowledge.addDocument")}
            </Button>
          )}
          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={() => close(false)} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={busy}>
              {t("knowledge.publishSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
