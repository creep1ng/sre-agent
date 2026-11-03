import { BotIcon, CheckIcon, CopyIcon, KeyRoundIcon, PlusIcon, RefreshCwIcon, UserIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useT } from "@/i18n";
import { adminApi, SLUG, type AdminError, type Principal, type PrincipalKind } from "@/lib/admin-api";
import { useAdminQuery, useRetryKey } from "./use-admin-query";
import {
  AdminPage,
  Empty,
  ErrorNote,
  Facts,
  Field,
  Mono,
  Panel,
  ROW,
  Select,
  StatusBadge,
  TD,
  TH,
  Table,
  Timestamp,
} from "./ui";

function KindLabel({ kind }: { kind: PrincipalKind }) {
  const t = useT("admin");
  const Icon = kind === "agent" ? BotIcon : UserIcon;
  return (
    <span className="inline-flex items-center gap-1.5 text-[var(--text-2)]">
      <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
      {t(kind === "agent" ? "kind.agent" : "kind.human")}
    </span>
  );
}

export function IdentitiesPage() {
  const t = useT("admin");
  const list = useAdminQuery(adminApi.listPrincipals, "principals");
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const items = list.data?.items ?? [];
  const open = items.find((item) => item.principal_id === openId) ?? null;

  return (
    <AdminPage
      title={t("identities.title")}
      lead={t("identities.lead")}
      actions={
        <>
          <Button variant="outline" onClick={list.reload}>
            <RefreshCwIcon /> {t("common.refresh")}
          </Button>
          <Button onClick={() => setCreating(true)}>
            <PlusIcon /> {t("identities.create")}
          </Button>
        </>
      }
    >
      {list.state.phase === "error" && <ErrorNote error={list.state.error} onRetry={list.reload} />}
      <Panel
        flush
        description={list.data ? `${t("common.count", { count: items.length })}${list.data.truncated ? ` · ${t("common.truncated")}` : ""}` : undefined}
        aria-busy={list.state.phase === "loading"}
      >
        {!list.data ? (
          <Empty>{list.state.phase === "loading" ? t("common.loading") : "—"}</Empty>
        ) : items.length === 0 ? (
          <Empty>{t("identities.empty")}</Empty>
        ) : (
          <Table
            label={t("identities.title")}
            head={
              <>
                <th className={TH}>{t("identities.col.identity")}</th>
                <th className={TH}>{t("identities.col.kind")}</th>
                <th className={TH}>{t("identities.col.status")}</th>
                <th className={TH}>{t("identities.col.updated")}</th>
              </>
            }
          >
            {items.map((item) => (
              <tr
                key={item.principal_id}
                data-clickable
                data-principal-row={item.principal_id}
                tabIndex={0}
                aria-label={t("identities.open", { name: item.display_name || item.principal_id })}
                onClick={() => setOpenId(item.principal_id)}
                onKeyDown={(event) => event.key === "Enter" && setOpenId(item.principal_id)}
                className={ROW}
              >
                <td className={TD}>
                  <div className="font-medium">{item.display_name || item.principal_id}</div>
                  <Mono className="text-muted-foreground">{item.principal_id}</Mono>
                </td>
                <td className={TD}>
                  <KindLabel kind={item.kind} />
                </td>
                <td className={TD}>
                  <StatusBadge status={item.status} />
                </td>
                <td className={TD}>
                  <Timestamp iso={item.updated_at} />
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>

      <PrincipalSheet principal={open} onClose={() => setOpenId(null)} onChanged={list.reload} />
      <CreatePrincipalDialog
        open={creating}
        onOpenChange={setCreating}
        onCreated={(principal) => {
          list.reload();
          setOpenId(principal.principal_id);
        }}
      />
    </AdminPage>
  );
}

function PrincipalSheet({
  principal,
  onClose,
  onChanged,
}: {
  principal: Principal | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useT("admin");
  const [issuing, setIssuing] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const principalId = principal?.principal_id ?? null;
  const credentials = useAdminQuery(
    principalId ? () => adminApi.listCredentials(principalId) : null,
    `credentials:${principalId}`,
  );

  return (
    <Sheet open={principal !== null} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        {principal && (
          <>
            <SheetHeader className="gap-2 px-6 pt-8">
              <div className="flex items-center gap-2">
                <KindLabel kind={principal.kind} />
                <StatusBadge status={principal.status} />
              </div>
              <SheetTitle className="font-display text-3xl font-light tracking-[-.015em]">
                {principal.display_name || principal.principal_id}
              </SheetTitle>
              <SheetDescription asChild>
                <Mono className="text-muted-foreground">{principal.principal_id}</Mono>
              </SheetDescription>
            </SheetHeader>

            <div className="flex flex-col gap-8 px-6 pb-8">
              <Facts
                rows={[
                  [t("identities.createdAt"), <Timestamp iso={principal.created_at} />],
                  [t("identities.updatedAt"), <Timestamp iso={principal.updated_at} />],
                ]}
              />

              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setIssuing(true)} disabled={principal.status !== "active"}>
                  <KeyRoundIcon /> {t("identities.issue")}
                </Button>
                {principal.status === "active" && (
                  <Button variant="outline" onClick={() => setDeactivating(true)}>
                    {t("identities.deactivate")}
                  </Button>
                )}
              </div>
              {principal.status !== "active" && (
                <p className="text-[15px] text-muted-foreground">{t("identities.inactiveNote")}</p>
              )}

              <section className="flex flex-col gap-3">
                <h3 className="font-display text-xl">{t("identities.credentials")}</h3>
                {credentials.state.phase === "error" ? (
                  <ErrorNote error={credentials.state.error} onRetry={credentials.reload} />
                ) : !credentials.data ? (
                  <p className="text-muted-foreground">{t("common.loading")}</p>
                ) : credentials.data.items.length === 0 ? (
                  <p className="text-muted-foreground">{t("identities.credentials.empty")}</p>
                ) : (
                  <ul className="flex flex-col divide-y rounded-xl border" data-credential-list={principal.principal_id}>
                    {credentials.data.items.map((credential) => (
                      <li key={credential.credential_id} className="flex flex-col gap-1 px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <Mono>{credential.prefix}…</Mono>
                          <StatusBadge status={credential.status} />
                        </div>
                        <Mono className="text-muted-foreground">{credential.credential_id}</Mono>
                        <div className="flex flex-wrap gap-x-4 text-sm text-muted-foreground">
                          <CredentialDate label="identities.credentials.issued" iso={credential.created_at} />
                          {credential.expires_at ? (
                            <CredentialDate label="identities.credentials.expires" iso={credential.expires_at} />
                          ) : (
                            <span>{t("identities.credentials.noExpiry")}</span>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <IssueDialog
              principalId={principal.principal_id}
              open={issuing}
              onOpenChange={setIssuing}
              onIssued={credentials.reload}
            />
            <DeactivateDialog
              principal={principal}
              open={deactivating}
              onOpenChange={setDeactivating}
              onDone={onChanged}
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function CredentialDate({ label, iso }: { label: "identities.credentials.issued" | "identities.credentials.expires"; iso: string }) {
  const t = useT("admin");
  const parts = t(label, { date: "\u0000" }).split("\u0000");
  return (
    <span>
      {parts[0]}
      <Timestamp iso={iso} />
      {parts[1]}
    </span>
  );
}

function CreatePrincipalDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (principal: Principal) => void;
}) {
  const t = useT("admin");
  const [principalId, setPrincipalId] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState<PrincipalKind>("agent");
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<AdminError | "local" | null>(null);
  const [busy, setBusy] = useState(false);
  const retry = useRetryKey("principal-create");

  const idOk = SLUG.test(principalId.trim());
  const nameOk = name.trim().length >= 1 && name.trim().length <= 200;

  const close = (next: boolean) => {
    if (busy) return;
    if (!next) {
      setPrincipalId("");
      setName("");
      setKind("agent");
      setChecked(false);
      setError(null);
    }
    onOpenChange(next);
  };

  const submit = async () => {
    setChecked(true);
    if (!idOk || !nameOk) {
      setError("local");
      return;
    }
    const body = { principal_id: principalId.trim(), kind, display_name: name.trim() };
    setBusy(true);
    setError(null);
    const result = await adminApi.createPrincipal(body, retry.keyFor(body));
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    retry.settle();
    toast.success(t("identities.created", { id: result.body.principal_id }));
    onCreated(result.body);
    close(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-normal">{t("identities.create")}</DialogTitle>
          <DialogDescription>{t("identities.createLead")}</DialogDescription>
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
              {t("identities.invalid")}
            </p>
          ) : (
            error && <ErrorNote error={error} />
          )}
          <Field id="principal-id" label={t("identities.field.id")} hint={t("identities.field.idHint")}>
            <Input
              id="principal-id"
              className="font-mono"
              autoComplete="off"
              spellCheck={false}
              maxLength={64}
              placeholder="triage-agent-01"
              aria-describedby="principal-id-hint"
              aria-invalid={checked && !idOk}
              value={principalId}
              onChange={(event) => setPrincipalId(event.target.value)}
              autoFocus
            />
          </Field>
          <Field id="principal-name" label={t("identities.field.name")}>
            <Input
              id="principal-name"
              autoComplete="off"
              maxLength={200}
              aria-invalid={checked && !nameOk}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field id="principal-kind" label={t("identities.field.kind")}>
            <Select id="principal-kind" value={kind} onChange={(event) => setKind(event.target.value as PrincipalKind)}>
              <option value="agent">{t("kind.agent")}</option>
              <option value="human">{t("kind.human")}</option>
            </Select>
          </Field>
          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={() => close(false)} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={busy}>
              {t("identities.createSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeactivateDialog({
  principal,
  open,
  onOpenChange,
  onDone,
}: {
  principal: Principal;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const t = useT("admin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AdminError | null>(null);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    // The precondition is the version the operator is looking at, read fresh when possible.
    const fresh = await adminApi.getPrincipal(principal.principal_id);
    const expected = fresh.ok ? fresh.body.updated_at : principal.updated_at;
    const result = await adminApi.deactivatePrincipal(principal.principal_id, expected);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      if (result.error === "conflict") onDone();
      return;
    }
    toast.success(t("identities.deactivated", { id: principal.principal_id }));
    onOpenChange(false);
    onDone();
  };

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        if (!next) setError(null);
        onOpenChange(next);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("identities.deactivateTitle", { id: principal.principal_id })}</AlertDialogTitle>
          <AlertDialogDescription>{t("identities.deactivateLead")}</AlertDialogDescription>
        </AlertDialogHeader>
        {error && <ErrorNote error={error} />}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={busy}
            onClick={(event) => {
              event.preventDefault();
              void confirm();
            }}
          >
            {t("identities.deactivate")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function IssueDialog({
  principalId,
  open,
  onOpenChange,
  onIssued,
}: {
  principalId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onIssued: () => void;
}) {
  const t = useT("admin");
  const [expires, setExpires] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AdminError | "replay" | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const retry = useRetryKey("credential-issue");

  const close = (next: boolean) => {
    if (busy) return;
    if (!next) {
      setExpires("");
      setError(null);
    }
    onOpenChange(next);
  };

  const submit = async () => {
    const body = expires.trim() ? { expires_at: expires.trim() } : {};
    setBusy(true);
    setError(null);
    const result = await adminApi.issueCredential(principalId, body, retry.keyFor({ principalId, body }));
    setBusy(false);
    onIssued();
    if (!result.ok) {
      setError(result.error);
      return;
    }
    retry.settle();
    if (result.body.secret_revealed === true && typeof result.body.key === "string") {
      setSecret(result.body.key);
      close(false);
    } else {
      setError("replay");
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display text-2xl font-normal">{t("identities.issueTitle", { id: principalId })}</DialogTitle>
            <DialogDescription>{t("identities.issueLead")}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            {error === "replay" ? (
              <p role="alert" className="text-sm text-critical">
                {t("identities.secretReplay")}
              </p>
            ) : (
              error && <ErrorNote error={error} />
            )}
            <Field id="credential-expires" label={t("identities.field.expires")} hint={t("identities.field.expiresHint")}>
              <Input
                id="credential-expires"
                className="font-mono"
                autoComplete="off"
                spellCheck={false}
                placeholder="2027-01-31T23:59:59Z"
                aria-describedby="credential-expires-hint"
                value={expires}
                onChange={(event) => setExpires(event.target.value)}
              />
            </Field>
            <DialogFooter className="mt-2">
              <Button type="button" variant="ghost" onClick={() => close(false)} disabled={busy}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={busy}>
                <KeyRoundIcon /> {t("identities.issueSubmit")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <SecretDialog secret={secret} onClose={() => setSecret(null)} />
    </>
  );
}

/** The one time a secret is on screen; closing the dialog drops it from memory. */
function SecretDialog({ secret, onClose }: { secret: string | null; onClose: () => void }) {
  const t = useT("admin");
  const [copied, setCopied] = useState(false);
  return (
    <Dialog
      open={secret !== null}
      onOpenChange={(next) => {
        if (!next) {
          setCopied(false);
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-normal">{t("identities.secretTitle")}</DialogTitle>
          <DialogDescription>{t("identities.secretLead")}</DialogDescription>
        </DialogHeader>
        <pre className="overflow-x-auto rounded-lg bg-[var(--code)] px-4 py-3 font-mono text-sm" data-secret>
          <code>{secret}</code>
        </pre>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              if (!secret) return;
              void navigator.clipboard?.writeText(secret).then(() => setCopied(true));
            }}
          >
            {copied ? <CheckIcon /> : <CopyIcon />} {t(copied ? "identities.copied" : "identities.copy")}
          </Button>
          <Button
            onClick={() => {
              setCopied(false);
              onClose();
            }}
          >
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
