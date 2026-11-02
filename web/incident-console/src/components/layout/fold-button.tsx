import { PanelLeftCloseIcon, PanelLeftOpenIcon, PanelRightCloseIcon, PanelRightOpenIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS = {
  left: { fold: PanelLeftCloseIcon, unfold: PanelLeftOpenIcon },
  right: { fold: PanelRightCloseIcon, unfold: PanelRightOpenIcon },
};

/** Folds or unfolds a side panel; pair it with useFolded(panel) and the panel's id. */
export function FoldButton({
  side,
  folded,
  onFoldedChange,
  controls,
  label,
  className,
}: {
  side: "left" | "right";
  folded: boolean;
  onFoldedChange: (folded: boolean) => void;
  controls: string;
  label: string;
  className?: string;
}) {
  const Icon = ICONS[side][folded ? "unfold" : "fold"];
  return (
    <button
      type="button"
      aria-expanded={!folded}
      aria-controls={controls}
      aria-label={label}
      title={label}
      onClick={() => onFoldedChange(!folded)}
      className={cn(
        "grid size-9 shrink-0 place-items-center rounded-lg border border-sidebar-border text-muted-foreground transition-colors outline-none hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
        className,
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
    </button>
  );
}
