import { PlusIcon, RefreshCwIcon } from "lucide-react";
import { useMemo, useState } from "react";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useT } from "@/i18n";
import {
  ADMIN_RESOURCES,
  adminApi,
  GRANT_ACTIONS,
  SLUG,
  type CatalogResource,
  type Grant,
  type Principal,
  type ResourceRef,
} from "@/lib/admin-api";
import { useAdminMutation, useAdminQuery, useRetryKey } from "./use-admin-query";
import { AdminPage, Empty, ErrorNote, Field, Mono, Panel, ROW, Select, StatusBadge, TD, TH, Table, useResourceType } from "./ui";

type By = "principal" | "resource";

const refKey = (ref: ResourceRef) => `${ref.resource_type}/${ref.resource_id}`;

export function PermissionsPage() {
  const t = useT("admin");
  const typeLabel = useResourceType();
  const principals = useAdminQuery(adminApi.listPrincipals, "principals");
  const catalog = useAdminQuery(() => adminApi.listCatalogResources(), "catalog");
  const [by, setBy] = useState<By>("principal");
  const [principalId, setPrincipalId] = useState("");
  const [resourceId, setResourceId] = useState("");
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<Grant | null>(null);

  const selected = by === "principal" ? principalId : resourceId;
  const grants = useAdminQuery(
    selected
      ? () => adminApi.listGrants(by === "principal" ? { principal_id: selected } : { resource_id: selected })
      : null,
    `grants:${by}:${selected}`,
  );
  const items = grants.data?.items ?? [];

  const principalName = useMemo(() => {
    const names = new Map((principals.data?.items ?? []).map((item) => [item.principal_id, item.display_name]));
    return (id: string) => names.get(id) || id;
  }, [principals.data]);

  const resources = catalog.data?.items ?? [];

  return (
    <AdminPage
      title={t("permissions.title")}
      lead={t("permissions.lead")}
      actions={
        <>
          <Button variant="outline" onClick={grants.reload} disabled={!selected}>
            <RefreshCwIcon /> {t("common.refresh")}
          </Button>
          <Button onClick={() => setCreating(true)} disabled={!principals.data}>
            <PlusIcon /> {t("permissions.create")}
          </Button>
        </>
      }
    >
      {principals.state.phase === "error" && <ErrorNote error={principals.state.error} onRetry={principals.reload} />}

      <Panel
        flush
        description={
          grants.data
            ? `${t("common.count", { count: items.length })}${grants.data.truncated ? ` · ${t("common.truncated")}` : ""}`
            : undefined
        }
      >
        <div className="flex flex-col gap-4 border-b px-6 py-5 md:flex-row md:items-end">
          <div className="grid gap-1.5">
            <span className="text-sm font-medium">{t("permissions.by")}</span>
            <Tabs value={by} onValueChange={(value) => setBy(value as By)}>
              <TabsList>
                <TabsTrigger value="principal">{t("permissions.byPrincipal")}</TabsTrigger>
                <TabsTrigger value="resource">{t("permissions.byResource")}</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          {by === "principal" ? (
            <Field id="grants-principal" label={t("permissions.byPrincipal")} className="md:w-96">
              <Select
                id="grants-principal"
                value={principalId}
                disabled={!principals.data}
                onChange={(event) => setPrincipalId(event.target.value)}
              >
                <option value="">{t("permissions.pickPrincipal")}</option>
                {(principals.data?.items ?? []).map((item) => (
                  <option key={item.principal_id} value={item.principal_id}>
                    {item.display_name || item.principal_id} ({item.principal_id})
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <Field id="grants-resource" label={t("permissions.byResource")} className="md:w-96">
              <Select
                id="grants-resource"
                value={resourceId}
                disabled={!catalog.data}
                onChange={(event) => setResourceId(event.target.value)}
              >
                <option value="">{t("permissions.pickResource")}</option>
                {resources.map((item) => (
                  <option key={refKey(item)} value={item.resource_id}>
                    {item.discoverability?.display_name || item.resource_id} · {typeLabel(item.resource_type)}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
        {by === "resource" && catalog.state.phase === "error" && (
          <p className="border-b px-6 py-3 text-sm text-muted-foreground">{t("permissions.catalogUnavailable")}</p>
        )}

        {grants.state.phase === "error" ? (
          <div className="px-6 py-5">
            <ErrorNote error={grants.state.error} onRetry={grants.reload} />
          </div>
        ) : !selected ? (
          <Empty>{t("permissions.pickFirst")}</Empty>
        ) : !grants.data ? (
          <Empty>{t("common.loading")}</Empty>
        ) : items.length === 0 ? (
          <Empty>{t("permissions.empty")}</Empty>
        ) : (
          <Table
            label={t("permissions.title")}
            head={
              <>
                <th className={TH}>{t("permissions.col.grant")}</th>
                <th className={TH}>{t("permissions.col.principal")}</th>
                <th className={TH}>{t("permissions.col.action")}</th>
                <th className={TH}>{t("permissions.col.resource")}</th>
                <th className={TH}>{t("permissions.col.status")}</th>
                <th className={TH}>
                  <span className="sr-only">{t("permissions.revoke")}</span>
                </th>
              </>
            }
          >
            {items.map((grant) => (
              <tr key={grant.grant_id} className={ROW} data-grant-row={grant.grant_id}>
                <td className={TD}>
                  <Mono>{grant.grant_id}</Mono>
                </td>
                <td className={TD}>
                  <div>{principalName(grant.principal_id)}</div>
                  <Mono className="text-muted-foreground">{grant.principal_id}</Mono>
                </td>
                <td className={TD}>
                  <Mono className="rounded-md bg-[var(--code)] px-1.5 py-0.5 whitespace-nowrap">{grant.action}</Mono>
                </td>
                <td className={TD}>
                  <div>{typeLabel(grant.resource.resource_type)}</div>
                  <Mono className="text-muted-foreground">{grant.resource.resource_id}</Mono>
                </td>
                <td className={TD}>
                  <StatusBadge status={grant.status} />
                </td>
                <td className={`${TD} text-right`}>
                  {grant.status === "active" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={t("permissions.revokeLabel", { id: grant.grant_id })}
                      onClick={() => setRevoking(grant)}
                    >
                      {t("permissions.revoke")}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>

      <CreateGrantDialog
        open={creating}
        onOpenChange={setCreating}
        principals={principals.data?.items ?? []}
        resources={resources}
        catalogError={catalog.state.phase === "error"}
        onCreated={(grant) => {
          setBy("principal");
          setPrincipalId(grant.principal_id);
          grants.reload();
        }}
      />
      <RevokeDialog
        grant={revoking}
        principalName={principalName}
        onClose={() => setRevoking(null)}
        onDone={grants.reload}
      />
    </AdminPage>
  );
}

function CreateGrantDialog({
  open,
  onOpenChange,
  principals,
  resources,
  catalogError,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  principals: Principal[];
  resources: CatalogResource[];
  catalogError: boolean;
  onCreated: (grant: Grant) => void;
}) {
  const t = useT("admin");
  const typeLabel = useResourceType();
  const [grantId, setGrantId] = useState("");
  const [principalId, setPrincipalId] = useState("");
  const [resource, setResource] = useState("");
  const [action, setAction] = useState("");
  const [checked, setChecked] = useState(false);
  const { busy, error, setError, run } = useAdminMutation<"local">();
  const retry = useRetryKey("grant-create");

  // Active catalog entries plus the seeded administrative resources the catalog never lists.
  const targets = useMemo<ResourceRef[]>(
    () => [
      ...resources.filter((item) => item.status === "active").map(({ resource_type, resource_id }) => ({ resource_type, resource_id })),
      ...ADMIN_RESOURCES,
    ],
    [resources],
  );
  const target = targets.find((item) => refKey(item) === resource);
  const actions = target ? (GRANT_ACTIONS[target.resource_type] ?? []) : [];
  const active = principals.filter((item) => item.status === "active");
  const names = new Map(resources.map((item) => [refKey(item), item.discoverability?.display_name]));

  const idOk = SLUG.test(grantId.trim());
  const valid = idOk && principalId && target && actions.includes(action);

  const close = (next: boolean) => {
    if (busy) return;
    if (!next) {
      setGrantId("");
      setPrincipalId("");
      setResource("");
      setAction("");
      setChecked(false);
      setError(null);
    }
    onOpenChange(next);
  };

  const submit = async () => {
    setChecked(true);
    if (!valid || !target) {
      setError("local");
      return;
    }
    const body = { grant_id: grantId.trim(), principal_id: principalId, action, resource: target };
    const result = await run(() => adminApi.createGrant(body, retry.keyFor(body)));
    if (!result.ok) return;
    retry.settle();
    toast.success(t("permissions.created", { id: body.grant_id }));
    onCreated({ ...body, ...result.body });
    close(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-normal">{t("permissions.create")}</DialogTitle>
          <DialogDescription>{t("permissions.createLead")}</DialogDescription>
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
              {t("permissions.invalid")}
            </p>
          ) : (
            error && <ErrorNote error={error} />
          )}
          <Field id="grant-id" label={t("permissions.field.id")} hint={t("identities.field.idHint")}>
            <Input
              id="grant-id"
              className="font-mono"
              autoComplete="off"
              spellCheck={false}
              maxLength={64}
              placeholder="grant-triage-agent-invoke"
              aria-describedby="grant-id-hint"
              aria-invalid={checked && !idOk}
              value={grantId}
              onChange={(event) => setGrantId(event.target.value)}
              autoFocus
            />
          </Field>
          <Field id="grant-principal" label={t("permissions.field.principal")}>
            <Select
              id="grant-principal"
              value={principalId}
              aria-invalid={checked && !principalId}
              onChange={(event) => setPrincipalId(event.target.value)}
            >
              <option value="">{t("permissions.pickPrincipal")}</option>
              {active.map((item) => (
                <option key={item.principal_id} value={item.principal_id}>
                  {item.display_name || item.principal_id} ({item.principal_id})
                </option>
              ))}
            </Select>
          </Field>
          <Field id="grant-resource" label={t("permissions.field.resource")}>
            <Select
              id="grant-resource"
              value={resource}
              aria-invalid={checked && !target}
              onChange={(event) => {
                setResource(event.target.value);
                setAction("");
              }}
            >
              <option value="">{t("permissions.pickResource")}</option>
              {targets.map((item) => (
                <option key={refKey(item)} value={refKey(item)}>
                  {names.get(refKey(item)) || item.resource_id} · {typeLabel(item.resource_type)}
                </option>
              ))}
            </Select>
            {catalogError && <p className="text-[13px] text-muted-foreground">{t("permissions.catalogUnavailable")}</p>}
          </Field>
          <Field id="grant-action" label={t("permissions.field.action")} hint={t("permissions.field.actionHint")}>
            <Select
              id="grant-action"
              className="font-mono"
              value={action}
              disabled={!target}
              aria-describedby="grant-action-hint"
              aria-invalid={checked && !actions.includes(action)}
              onChange={(event) => setAction(event.target.value)}
            >
              <option value="">{target ? t("permissions.pickAction") : t("permissions.pickResourceFirst")}</option>
              {actions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </Field>
          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={() => close(false)} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={busy}>
              {t("permissions.createSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RevokeDialog({
  grant,
  principalName,
  onClose,
  onDone,
}: {
  grant: Grant | null;
  principalName: (id: string) => string;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useT("admin");
  const typeLabel = useResourceType();
  const { busy, error, setError, run } = useAdminMutation();

  const confirm = async () => {
    if (!grant) return;
    const result = await run(() => adminApi.revokeGrant(grant.grant_id));
    if (!result.ok) return;
    toast.success(t("permissions.revoked", { id: grant.grant_id }));
    onClose();
    onDone();
  };

  return (
    <AlertDialog
      open={grant !== null}
      onOpenChange={(next) => {
        if (busy || next) return;
        setError(null);
        onClose();
      }}
    >
      <AlertDialogContent>
        {grant && (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("permissions.revokeTitle", { id: grant.grant_id })}</AlertDialogTitle>
              <AlertDialogDescription>
                {t("permissions.revokeLead", {
                  principal: principalName(grant.principal_id),
                  action: grant.action,
                  resource: `${typeLabel(grant.resource.resource_type)} ${grant.resource.resource_id}`,
                })}
              </AlertDialogDescription>
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
                {t("permissions.revoke")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </>
        )}
      </AlertDialogContent>
    </AlertDialog>
  );
}
