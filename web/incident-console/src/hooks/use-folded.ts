import { useCallback, useState } from "react";

const PREFIX = "midnight.fold.";

function read(panel: string) {
  try {
    return localStorage.getItem(PREFIX + panel) === "1";
  } catch {
    return false;
  }
}

/**
 * Whether a side panel is folded, remembered per panel in this browser like an editor sidebar.
 * Panels start unfolded; storage errors only cost the memory, never the panel.
 */
export function useFolded(panel: string): [boolean, (folded: boolean) => void] {
  const [folded, setFolded] = useState(() => read(panel));
  const set = useCallback(
    (next: boolean) => {
      setFolded(next);
      try {
        localStorage.setItem(PREFIX + panel, next ? "1" : "0");
      } catch {
        // Private mode or a full quota: the panel still folds for this page.
      }
    },
    [panel],
  );
  return [folded, set];
}
