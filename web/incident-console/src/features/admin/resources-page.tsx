import { RefreshCwIcon } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useT } from "@/i18n";
import { adminApi, CONCRETE_MODEL, type AdminError, type ModelAlias } from "@/lib/admin-api";
import { useAdminQuery } from "./use-admin-query";
import { AdminPage, Empty, ErrorNote, Facts, Field, Mono, Panel, ROW, StatusBadge, TD, TH, Table, Timestamp, useResourceType } from "./ui";

const aliasIdOf = (alias: ModelAlias) => alias.model_alias_id || alias.alias;

export function ResourcesPage() {
  const t = useT("admin");
  const typeLabel = useResourceType();
  const aliases = useAdminQuery(adminApi.listModelAliases, "aliases");
  const catalog = useAdminQuery(() => adminApi.listCatalogResources(), "catalog");
  const [openId, setOpenId] = useState<string | null>(null);
  const aliasItems = aliases.data?.items ?? [];
  const catalogItems = catalog.data?.items ?? [];
  const open = aliasItems.find((item) => aliasIdOf(item) === openId) ?? null;

  const refresh = () => {
    aliases.reload();
    catalog.reload();
  };

  return (
    <AdminPage
      title={t("resources.title")}
      lead={t("resources.lead")}
      actions={
        <Button variant="outline" onClick={refresh}>
          <RefreshCwIcon /> {t("common.refresh")}
        </Button>
      }
    >
      <Panel
        flush
        title={t("aliases.title")}
        description={aliases.data ? t("common.count", { count: aliasItems.length }) : undefined}
      >
        {aliases.state.phase === "error" ? (
          <div className="px-6 py-5">
            <ErrorNote error={aliases.state.error} onRetry={aliases.reload} />
          </div>
        ) : !aliases.data ? (
          <Empty>{t("common.loading")}</Empty>
        ) : aliasItems.length === 0 ? (
          <Empty>{t("aliases.empty")}</Empty>
        ) : (
          <Table
            label={t("aliases.title")}
            head={
              <>
                <th className={TH}>{t("aliases.col.alias")}</th>
                <th className={TH}>{t("aliases.col.model")}</th>
                <th className={TH}>{t("aliases.col.router")}</th>
                <th className={TH}>{t("aliases.col.provider")}</th>
                <th className={TH}>{t("aliases.col.status")}</th>
                <th className={TH}>{t("aliases.col.updated")}</th>
              </>
            }
          >
            {aliasItems.map((item) => (
              <tr
                key={aliasIdOf(item)}
                data-clickable
                data-alias-row={aliasIdOf(item)}
                tabIndex={0}
                aria-label={t("aliases.open", { alias: item.alias })}
                onClick={() => setOpenId(aliasIdOf(item))}
                onKeyDown={(event) => event.key === "Enter" && setOpenId(aliasIdOf(item))}
                className={ROW}
              >
                <td className={TD}>
                  <Mono className="font-medium">{item.alias}</Mono>
                </td>
                <td className={TD}>
                  <Mono>{item.concrete_model}</Mono>
                </td>
                <td className={TD}>
                  <Mono className="text-muted-foreground">{item.router}</Mono>
                </td>
                <td className={TD}>
                  <Mono className="text-muted-foreground">{item.inference_provider}</Mono>
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

      <Panel
        flush
        title={t("catalog.title")}
        description={
          <>
            {t("catalog.lead")}
            {catalog.data?.truncated && ` ${t("common.truncated")}`}
          </>
        }
      >
        {catalog.state.phase === "error" ? (
          <div className="px-6 py-5">
            <ErrorNote error={catalog.state.error} onRetry={catalog.reload} />
          </div>
        ) : !catalog.data ? (
          <Empty>{t("common.loading")}</Empty>
        ) : catalogItems.length === 0 ? (
          <Empty>{t("catalog.empty")}</Empty>
        ) : (
          <Table
            label={t("catalog.title")}
            head={
              <>
                <th className={TH}>{t("catalog.col.type")}</th>
                <th className={TH}>{t("catalog.col.name")}</th>
                <th className={TH}>{t("catalog.col.id")}</th>
                <th className={TH}>{t("catalog.col.status")}</th>
                <th className={TH}>{t("catalog.col.source")}</th>
              </>
            }
          >
            {catalogItems.map((item) => (
              <tr key={`${item.resource_type}/${item.resource_id}`} className={ROW} data-resource-row={`${item.resource_type}/${item.resource_id}`}>
                <td className={`${TD} text-[var(--text-2)]`}>{typeLabel(item.resource_type)}</td>
                <td className={TD}>{item.discoverability?.display_name || "—"}</td>
                <td className={TD}>
                  <Mono>{item.resource_id}</Mono>
                </td>
                <td className={TD}>
                  <StatusBadge status={item.status} />
                </td>
                <td className={TD}>
                  <Mono className="text-muted-foreground">{item.source || "—"}</Mono>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>

      <AliasSheet aliasId={openId} listed={open} onClose={() => setOpenId(null)} onChanged={aliases.reload} />
    </AdminPage>
  );
}

function AliasSheet({
  aliasId,
  listed,
  onClose,
  onChanged,
}: {
  aliasId: string | null;
  listed: ModelAlias | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useT("admin");
  // The detail is read fresh: its updated_at is the precondition of every change made here.
  const detail = useAdminQuery(aliasId ? () => adminApi.getModelAlias(aliasId) : null, `alias:${aliasId}`);
  const alias = detail.data ?? listed;
  const [editing, setEditing] = useState(false);
  const [deactivating, setDeactivating] = useState(false);

  const close = () => {
    setEditing(false);
    onClose();
  };

  return (
    <Sheet open={aliasId !== null} onOpenChange={(next) => !next && close()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        {alias && (
          <>
            <SheetHeader className="gap-2 px-6 pt-8">
              <div>
                <StatusBadge status={alias.status} />
              </div>
              <SheetTitle className="font-mono text-2xl font-normal break-all">{alias.alias}</SheetTitle>
              <SheetDescription>{t("aliases.title")}</SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-8 px-6 pb-8">
              {detail.state.phase === "error" && <ErrorNote error={detail.state.error} onRetry={detail.reload} />}
              {editing && detail.data ? (
                <AssignmentForm
                  alias={detail.data}
                  onCancel={() => setEditing(false)}
                  onSaved={() => {
                    setEditing(false);
                    detail.reload();
                    onChanged();
                  }}
                  onConflict={() => {
                    detail.reload();
                    onChanged();
                  }}
                />
              ) : (
                <Facts
                  rows={[
                    [t("aliases.id"), <Mono>{alias.model_alias_id}</Mono>],
                    [t("aliases.col.model"), <Mono>{alias.concrete_model}</Mono>],
                    [t("aliases.col.router"), <Mono>{alias.router}</Mono>],
                    [t("aliases.col.provider"), <Mono>{alias.inference_provider}</Mono>],
                    [t("aliases.col.updated"), <Timestamp iso={alias.updated_at} />],
                  ]}
                />
              )}
              {!editing &&
                (alias.status === "active" ? (
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => setEditing(true)} disabled={!detail.data}>
                      {t("aliases.edit")}
                    </Button>
                    <Button variant="outline" onClick={() => setDeactivating(true)} disabled={!detail.data}>
                      {t("aliases.deactivate")}
                    </Button>
                  </div>
                ) : (
                  <p className="text-[15px] text-muted-foreground">{t("aliases.inactiveNote")}</p>
                ))}
            </div>
            {detail.data && (
              <DeactivateAliasDialog
                alias={detail.data}
                open={deactivating}
                onOpenChange={setDeactivating}
                onDone={() => {
                  detail.reload();
                  onChanged();
                }}
              />
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function AssignmentForm({
  alias,
  onCancel,
  onSaved,
  onConflict,
}: {
  alias: ModelAlias;
  onCancel: () => void;
  onSaved: () => void;
  onConflict: () => void;
}) {
  const t = useT("admin");
  const [model, setModel] = useState(alias.concrete_model);
  const [router, setRouter] = useState(alias.router);
  const [provider, setProvider] = useState(alias.inference_provider);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<AdminError | "local" | null>(null);
  const [busy, setBusy] = useState(false);

  const modelOk = CONCRETE_MODEL.test(model.trim());
  const routerOk = router.trim() === "openrouter";
  const providerOk = provider.trim() !== "";

  const submit = async () => {
    setChecked(true);
    if (!modelOk || !routerOk || !providerOk) {
      setError("local");
      return;
    }
    setBusy(true);
    setError(null);
    const result = await adminApi.replaceAssignment(aliasIdOf(alias), {
      concrete_model: model.trim(),
      router: router.trim(),
      inference_provider: provider.trim(),
      expected_updated_at: alias.updated_at,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      if (result.error === "conflict") onConflict();
      return;
    }
    toast.success(t("aliases.saved", { alias: alias.alias }));
    onSaved();
  };

  return (
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
          {t("aliases.invalid")}
        </p>
      ) : (
        error && <ErrorNote error={error} />
      )}
      <Field id="alias-model" label={t("aliases.field.model")} hint={t("aliases.field.modelHint")}>
        <Input
          id="alias-model"
          className="font-mono"
          autoComplete="off"
          spellCheck={false}
          aria-describedby="alias-model-hint"
          aria-invalid={checked && !modelOk}
          value={model}
          onChange={(event) => setModel(event.target.value)}
          autoFocus
        />
      </Field>
      <Field id="alias-router" label={t("aliases.field.router")} hint={t("aliases.field.routerHint")}>
        <Input
          id="alias-router"
          className="font-mono"
          autoComplete="off"
          spellCheck={false}
          aria-describedby="alias-router-hint"
          aria-invalid={checked && !routerOk}
          value={router}
          onChange={(event) => setRouter(event.target.value)}
        />
      </Field>
      <Field id="alias-provider" label={t("aliases.field.provider")}>
        <Input
          id="alias-provider"
          className="font-mono"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={checked && !providerOk}
          value={provider}
          onChange={(event) => setProvider(event.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          {t("aliases.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function DeactivateAliasDialog({
  alias,
  open,
  onOpenChange,
  onDone,
}: {
  alias: ModelAlias;
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
    const result = await adminApi.deactivateAlias(aliasIdOf(alias), alias.updated_at);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      if (result.error === "conflict") onDone();
      return;
    }
    toast.success(t("aliases.deactivated", { alias: alias.alias }));
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
          <AlertDialogTitle>{t("aliases.deactivateTitle", { alias: alias.alias })}</AlertDialogTitle>
          <AlertDialogDescription>{t("aliases.deactivateLead")}</AlertDialogDescription>
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
            {t("aliases.deactivate")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
