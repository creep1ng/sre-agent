import { useState } from "react";
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
import { Label } from "@/components/ui/label";
import { useLive } from "@/lib/live";

/**
 * The API key lives only in memory for this tab: it is never written to URLs,
 * cookies, Web Storage, logs or telemetry, and it is cleared when the dialog closes.
 */
export function ConnectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const connect = useLive((state) => state.connect);
  const [key, setKey] = useState("");

  const close = (next: boolean) => {
    if (!next) setKey("");
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Conectar con la API</DialogTitle>
          <DialogDescription>
            Pega una clave con permiso para ver alertas. Vive solo en esta pestaña y se borra al recargar.
          </DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const value = key.trim();
            if (!value) return;
            connect(value);
            close(false);
          }}
        >
          <Label htmlFor="api-key">Clave de API</Label>
          <Input
            id="api-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={key}
            onChange={(event) => setKey(event.target.value)}
            autoFocus
          />
          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!key.trim()}>
              Conectar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
