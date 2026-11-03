import { PlusIcon, RefreshCwIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { adminApi, SEMVER, SKILL_ID, type AdminError, type SkillDependency, type SkillVersion } from "@/lib/admin-api";
import { UploadButton } from "./upload-button";
import { baseName, firstHeading, frontMatter, readUpload } from "./uploads";
import { useAdminQuery, useRetryKey } from "./use-admin-query";
import { AdminPage, Empty, ErrorNote, Facts, Field, Mono, Panel, ROW, StatusBadge, TD, TH, Table, Timestamp } from "./ui";

/** `incident-triage@1.0.0` → its id and version; the catalog names a Skill version that way. */
const split = (resourceId: string) => {
  const at = resourceId.lastIndexOf("@");
  return { skillId: resourceId.slice(0, at), version: resourceId.slice(at + 1) };
};

/** "incident-triage@1.0.0, other@2.1.0" → pinned dependencies, or null when one does not parse. */
const parseDependencies = (text: string): SkillDependency[] | null => {
  const parts = text
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const out = parts.map((part) => split(part)).map(({ skillId, version }) => ({ skill_id: skillId, version }));
  return out.every((dep) => SKILL_ID.test(dep.skill_id) && SEMVER.test(dep.version)) && out.length <= 16 ? out : null;
};

export function SkillsPage() {
  const t = useT("admin");
  const skills = useAdminQuery(adminApi.listSkills, "skills");
  const [openId, setOpenId] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const items = skills.data?.items ?? [];

  return (
    <AdminPage
      title={t("skills.title")}
      lead={t("skills.lead")}
      actions={
        <>
          <Button variant="outline" onClick={skills.reload}>
            <RefreshCwIcon /> {t("common.refresh")}
          </Button>
          <Button onClick={() => setPublishing(true)}>
            <PlusIcon /> {t("skills.publish")}
          </Button>
        </>
      }
    >
      <Panel flush description={skills.data ? t("common.count", { count: items.length }) : undefined}>
        {skills.state.phase === "error" ? (
          <div className="px-6 py-5">
            <ErrorNote error={skills.state.error} onRetry={skills.reload} />
          </div>
        ) : !skills.data ? (
          <Empty>{t("common.loading")}</Empty>
        ) : items.length === 0 ? (
          <Empty>{t("skills.empty")}</Empty>
        ) : (
          <Table
            label={t("skills.title")}
            head={
              <>
                <th className={TH}>{t("skills.col.skill")}</th>
                <th className={TH}>{t("skills.col.version")}</th>
                <th className={TH}>{t("skills.col.status")}</th>
              </>
            }
          >
            {items.map((item) => {
              const { skillId, version } = split(item.resource_id);
              return (
                <tr
                  key={item.resource_id}
                  data-clickable
                  data-skill-row={item.resource_id}
                  tabIndex={0}
                  aria-label={t("skills.open", { id: item.resource_id })}
                  onClick={() => setOpenId(item.resource_id)}
                  onKeyDown={(event) => event.key === "Enter" && setOpenId(item.resource_id)}
                  className={ROW}
                >
                  <td className={TD}>
                    <div>{item.discoverability?.display_name || skillId}</div>
                    <Mono className="text-muted-foreground">{skillId}</Mono>
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

      <SkillSheet resourceId={openId} onClose={() => setOpenId(null)} onChanged={skills.reload} />
      <PublishDialog
        open={publishing}
        onOpenChange={setPublishing}
        onPublished={(skill) => {
          skills.reload();
          setOpenId(skill.resource_id);
        }}
      />
    </AdminPage>
  );
}

function SkillSheet({
  resourceId,
  onClose,
  onChanged,
}: {
  resourceId: string | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useT("admin");
  const target = resourceId ? split(resourceId) : null;
  const skill = useAdminQuery(target ? () => adminApi.getSkill(target.skillId, target.version) : null, `skill:${resourceId}`);
  // A version published and never activated has no status yet: the API answers 404 until then.
  const status = useAdminQuery(
    target ? () => adminApi.getSkillStatus(target.skillId, target.version) : null,
    `skill-status:${resourceId}`,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AdminError | null>(null);
  const record = skill.data?.resource_id === resourceId ? skill.data : null;
  const never = status.state.phase === "error" && status.state.error === "missing";
  const current = never ? "published" : status.data?.resource_id === resourceId ? status.data.status : undefined;
  // The status change's precondition: the last status change, or the publication itself.
  const expected = never ? record?.created_at : status.data?.updated_at;

  const change = async (next: "active" | "inactive") => {
    if (!target || !expected) return;
    setBusy(true);
    setError(null);
    const result = await adminApi.setSkillStatus(target.skillId, target.version, next, expected);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      if (result.error === "conflict") status.reload();
      return;
    }
    toast.success(t(next === "active" ? "skills.activated" : "skills.deactivated", { id: resourceId ?? "" }));
    status.reload();
    onChanged();
  };

  return (
    <Sheet
      open={resourceId !== null}
      onOpenChange={(next) => {
        if (next) return;
        setError(null);
        onClose();
      }}
    >
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="gap-2 px-6 pt-8">
          <div>{current && <StatusBadge status={current} />}</div>
          <SheetTitle className="font-display text-3xl font-light tracking-[-.015em]">
            {record?.manifest.display_name ?? resourceId}
          </SheetTitle>
          <SheetDescription asChild>
            <Mono className="text-muted-foreground">{resourceId}</Mono>
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-8 px-6 pb-8">
          {skill.state.phase === "error" ? (
            <ErrorNote error={skill.state.error} onRetry={skill.reload} />
          ) : !record ? (
            <p className="text-muted-foreground">{t("common.loading")}</p>
          ) : (
            <>
              <p className="text-[15px] text-[var(--text-2)]">{record.manifest.description}</p>
              {error && <ErrorNote error={error} />}
              {current && (
                <div className="flex flex-wrap gap-2">
                  {current === "active" ? (
                    <Button variant="outline" onClick={() => void change("inactive")} disabled={busy || !expected}>
                      {t("skills.deactivate")}
                    </Button>
                  ) : (
                    <Button onClick={() => void change("active")} disabled={busy || !expected}>
                      {t("skills.activate")}
                    </Button>
                  )}
                </div>
              )}
              <Facts
                rows={[
                  [t("skills.d.owner"), <Mono>{record.owner_id}</Mono>],
                  [t("skills.d.published"), <Timestamp iso={record.created_at} />],
                  [
                    t("skills.d.dependencies"),
                    record.manifest.dependencies.length ? (
                      <Mono>{record.manifest.dependencies.map((dep) => `${dep.skill_id}@${dep.version}`).join(", ")}</Mono>
                    ) : (
                      t("skills.d.noDependencies")
                    ),
                  ],
                  [t("skills.d.digest"), <Mono className="text-muted-foreground">{record.content_sha256.slice(0, 16)}…</Mono>],
                ]}
              />
              <section className="flex flex-col gap-3">
                <h3 className="font-mono text-[11px] tracking-[.08em] text-muted-foreground uppercase">{t("skills.d.instructions")}</h3>
                <pre
                  data-skill-instructions
                  className="max-h-[28rem] overflow-auto rounded-xl border bg-[var(--code)] px-4 py-3 font-mono text-[13px] leading-relaxed whitespace-pre-wrap"
                >
                  {record.manifest.instructions}
                </pre>
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function PublishDialog({
  open,
  onOpenChange,
  onPublished,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPublished: (skill: SkillVersion) => void;
}) {
  const t = useT("admin");
  // The version is published in the name of the identity this session is connected as.
  const me = useAdminQuery(open ? adminApi.whoami : null, `skill-owner:${open}`);
  const [skillId, setSkillId] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [dependencies, setDependencies] = useState("");
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<AdminError | "local" | null>(null);
  const [busy, setBusy] = useState(false);
  const retry = useRetryKey("skill-publish");

  const ownerId = me.data?.principal_id ?? "";
  const deps = parseDependencies(dependencies);
  const ok = {
    id: SKILL_ID.test(skillId.trim()),
    version: SEMVER.test(version.trim()),
    owner: ownerId !== "",
    name: name.trim().length >= 1 && name.trim().length <= 200,
    description: description.trim().length >= 1 && description.trim().length <= 500,
    instructions: instructions.trim().length >= 1 && new TextEncoder().encode(instructions).length <= 16_384,
    dependencies: deps !== null,
  };

  const close = (next: boolean) => {
    if (busy) return;
    if (!next) {
      setSkillId("");
      setVersion("1.0.0");
      setName("");
      setDescription("");
      setInstructions("");
      setDependencies("");
      setUploadNote(null);
      setChecked(false);
      setError(null);
    }
    onOpenChange(next);
  };

  // A Skill archive (or its SKILL.md alone) fills the form: the manifest keeps only the instructions.
  const load = async (files: File[]) => {
    let upload;
    try {
      upload = await readUpload(files);
    } catch {
      setUploadNote(t("skills.uploadUnreadable"));
      return;
    }
    const byDepth = [...upload.texts].sort((a, b) => a.path.split("/").length - b.path.split("/").length);
    const skill =
      byDepth.find(({ path }) => /(^|\/)skill\.md$/i.test(path)) ?? (upload.texts.length === 1 ? upload.texts[0] : undefined);
    if (!skill) {
      setUploadNote(t("skills.uploadNoSkill"));
      return;
    }
    const { fields, body } = frontMatter(skill.text);
    const id = (fields.name ?? baseName(files[0].name))
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64);
    setSkillId(id);
    setName((firstHeading(body) ?? fields.name ?? id).slice(0, 200));
    setDescription((fields.description ?? "").slice(0, 500));
    setInstructions(body.trim());
    const left = [...upload.texts.filter((text) => text !== skill).map((text) => text.path), ...upload.skipped];
    setUploadNote(
      [
        t("skills.uploadLoaded", { file: skill.path }),
        left.length ? t("skills.uploadLeftOut", { files: left.slice(0, 5).join(", ") + (left.length > 5 ? "…" : "") }) : "",
      ]
        .filter(Boolean)
        .join(" "),
    );
  };

  const submit = async () => {
    setChecked(true);
    if (!Object.values(ok).every(Boolean) || !deps) {
      setError("local");
      return;
    }
    const body = {
      skill_id: skillId.trim(),
      version: version.trim(),
      owner_id: ownerId,
      manifest: { display_name: name.trim(), description: description.trim(), instructions, dependencies: deps },
    };
    setBusy(true);
    setError(null);
    const result = await adminApi.publishSkill(body, retry.keyFor(body));
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    retry.settle();
    toast.success(t("skills.published", { id: result.body.resource_id }));
    onPublished(result.body);
    close(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-normal">{t("skills.publish")}</DialogTitle>
          <DialogDescription>{t("skills.publishLead")}</DialogDescription>
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
              {t("skills.invalid")}
            </p>
          ) : error === "conflict" ? (
            <p role="alert" className="text-sm text-critical">
              {t("skills.conflict")}
            </p>
          ) : (
            error && <ErrorNote error={error} />
          )}
          <div className="flex flex-wrap items-center gap-3">
            <UploadButton id="skill-upload" label={t("skills.upload")} accept=".zip,.md" onFiles={(files) => void load(files)} />
            <p className="text-sm text-muted-foreground" data-skill-upload-note>
              {uploadNote ?? t("skills.uploadHint")}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_9rem]">
            <Field id="skill-id" label={t("skills.field.id")} hint={t("skills.field.idHint")}>
              <Input
                id="skill-id"
                className="font-mono"
                autoComplete="off"
                spellCheck={false}
                maxLength={64}
                placeholder="incident-triage"
                aria-describedby="skill-id-hint"
                aria-invalid={checked && !ok.id}
                value={skillId}
                onChange={(event) => setSkillId(event.target.value)}
                autoFocus
              />
            </Field>
            <Field id="skill-version" label={t("skills.field.version")}>
              <Input
                id="skill-version"
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
          <Field id="skill-name" label={t("skills.field.name")}>
            <Input
              id="skill-name"
              autoComplete="off"
              maxLength={200}
              aria-invalid={checked && !ok.name}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field id="skill-description" label={t("skills.field.description")}>
            <Input
              id="skill-description"
              autoComplete="off"
              maxLength={500}
              aria-invalid={checked && !ok.description}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
          <Field id="skill-instructions" label={t("skills.field.instructions")} hint={t("skills.field.instructionsHint")}>
            <Textarea
              id="skill-instructions"
              className="max-h-72 min-h-36 font-mono text-[13px]"
              spellCheck={false}
              aria-describedby="skill-instructions-hint"
              aria-invalid={checked && !ok.instructions}
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
            />
          </Field>
          <Field id="skill-dependencies" label={t("skills.field.dependencies")} hint={t("skills.field.dependenciesHint")}>
            <Input
              id="skill-dependencies"
              className="font-mono"
              autoComplete="off"
              spellCheck={false}
              placeholder="incident-triage@1.0.0"
              aria-describedby="skill-dependencies-hint"
              aria-invalid={checked && !ok.dependencies}
              value={dependencies}
              onChange={(event) => setDependencies(event.target.value)}
            />
          </Field>
          {ownerId && (
            <p className="text-sm text-muted-foreground" data-skill-owner>
              {t("skills.ownerNote", { id: ownerId })}
            </p>
          )}
          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={() => close(false)} disabled={busy}>
              {t("common.cancel")}
            </Button>
            {/* Nothing is checked before the session's identity, the owner, is known. */}
            <Button type="submit" disabled={busy || !me.data}>
              {t("skills.publishSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
