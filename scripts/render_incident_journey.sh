#!/usr/bin/env bash
set -euo pipefail

# Render issue #150 Mermaid sources without adding a repository dependency.
: "${CHROME_PATH:?Set CHROME_PATH to a local Chrome/Chromium executable.}"
MMDC_PATH="${MMDC_PATH:-/tmp/issue150-render/node_modules/.bin/mmdc}"
CONFIG="docs/diagrams/mermaid-config.json"
FLOW="docs/diagrams/incident-operator-flow.mmd"
JOURNEY="docs/diagrams/incident-operator-journey.mmd"
RESPONSIBILITIES="docs/design/ht-inc-07-ux-journey/user-journey.mmd"

[[ -x "$MMDC_PATH" ]] || { echo "mmdc not executable: $MMDC_PATH" >&2; exit 1; }
TMPDIR_RENDER="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RENDER"' EXIT
printf '{"executablePath":"%s"}' "$CHROME_PATH" > "$TMPDIR_RENDER/puppeteer.json"

render() {
  local source="$1" output="$2"
  "$MMDC_PATH" -p "$TMPDIR_RENDER/puppeteer.json" -c "$CONFIG" -b white -s 2 \
    -i "$source" -o "$output"
}

for source in "$FLOW" "$JOURNEY" "$RESPONSIBILITIES"; do
  stem="${source%.mmd}"
  render "$source" "$stem.svg"
  render "$source" "$stem.png"
done

python - "$FLOW" "$TMPDIR_RENDER" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text().splitlines()
out = Path(sys.argv[2])
classes = [line for line in source if line.lstrip().startswith("classDef ")]
cross_phase_edges = {"ALERT": {"    X03 --> J04"}, "RESPONSE": {"    R08 --> J08"}}
for index, group in enumerate(("ALERT", "RESPONSE", "RECOVERY"), start=1):
    start = next(i for i, line in enumerate(source) if line.startswith(f"  subgraph {group}["))
    end = next(i for i in range(start + 1, len(source)) if source[i] == "  end")
    body = [line for line in source[start + 1 : end] if line not in cross_phase_edges.get(group, set())]
    Path(out / f"phase{index}.mmd").write_text(
        "flowchart TB\n" + "\n".join(body + [""] + classes) + "\n"
    )
PY

for phase in 1 2 3; do
  render "$TMPDIR_RENDER/phase$phase.mmd" "docs/diagrams/incident-operator-flow-phase$phase.png"
done
