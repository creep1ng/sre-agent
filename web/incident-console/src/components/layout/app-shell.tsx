import { MenuIcon, SearchIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { Logo } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useNow } from "@/hooks/use-now";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { appMode } from "@/lib/mode";
import { useInbox, useLiveInbox } from "@/lib/selectors";
import { CommandMenu } from "./command-menu";
import { Sidebar } from "./sidebar";

export function AppShell() {
  const now = useNow();
  const mockInbox = useInbox(now);
  const liveInbox = useLiveInbox(now);
  const inbox = appMode === "live" ? liveInbox : mockInbox;
  const [menuOpen, setMenuOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  useEffect(() => {
    document.title = inbox.attention > 0 ? `(${inbox.attention}) midnight.agent` : "midnight.agent";
  }, [inbox.attention]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-dvh bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-sidebar-border bg-sidebar lg:block">
        <Sidebar inbox={inbox} onSearch={() => setCommandOpen(true)} onConnect={() => setConnectOpen(true)} />
      </aside>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetTitle className="sr-only">Navegación</SheetTitle>
          <SheetDescription className="sr-only">Secciones de la consola</SheetDescription>
          <Sidebar inbox={inbox} onSearch={() => setCommandOpen(true)} onConnect={() => setConnectOpen(true)} />
        </SheetContent>
      </Sheet>

      <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur lg:hidden">
        <Button variant="ghost" size="icon" onClick={() => setMenuOpen(true)} aria-label="Abrir menú">
          <MenuIcon />
        </Button>
        <Logo className="[&_span:last-child]:text-lg [&_svg]:size-7" />
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto"
          onClick={() => setCommandOpen(true)}
          aria-label="Buscar"
        >
          <SearchIcon />
        </Button>
      </header>

      <main className="lg:pl-64">
        <Outlet />
      </main>

      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} />
      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </div>
  );
}
