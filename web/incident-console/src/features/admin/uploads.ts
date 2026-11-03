import { unzipSync } from "fflate";

/** A Markdown file read from an upload, by its path inside the archive or its file name. */
export interface UploadedText {
  path: string;
  text: string;
}

export interface Upload {
  texts: UploadedText[];
  /** Files left out: not Markdown, too large, or past the archive's limit. */
  skipped: string[];
}

const MARKDOWN = /\.(md|markdown)$/i;
// An archive may not unpack into more than this, so a crafted .zip cannot exhaust the tab.
const MAX_UNPACKED = 4 * 1024 * 1024;
const MAX_FILE = 512 * 1024;

const decode = (bytes: Uint8Array) => new TextDecoder("utf-8").decode(bytes);
const hidden = (path: string) => path.split("/").some((part) => part.startsWith(".") || part === "__MACOSX");

/** Reads .md files and .zip archives of them; everything else is listed as skipped, never read. */
export async function readUpload(files: Iterable<File>): Promise<Upload> {
  const texts: UploadedText[] = [];
  const skipped: string[] = [];
  for (const file of files) {
    if (MARKDOWN.test(file.name)) {
      if (file.size > MAX_FILE) skipped.push(file.name);
      else texts.push({ path: file.name, text: await file.text() });
      continue;
    }
    if (!/\.zip$/i.test(file.name)) {
      skipped.push(file.name);
      continue;
    }
    let budget = MAX_UNPACKED;
    const entries = unzipSync(new Uint8Array(await file.arrayBuffer()), {
      filter: (entry) => {
        if (entry.name.endsWith("/") || hidden(entry.name)) return false;
        const wanted = MARKDOWN.test(entry.name) && entry.originalSize <= MAX_FILE && entry.originalSize <= budget;
        if (wanted) budget -= entry.originalSize;
        else skipped.push(entry.name);
        return wanted;
      },
    });
    for (const [path, bytes] of Object.entries(entries).sort(([a], [b]) => a.localeCompare(b))) {
      texts.push({ path, text: decode(bytes) });
    }
  }
  return { texts, skipped };
}

/** The text after a leading `---` YAML block, and that block's simple `key: value` lines. */
export function frontMatter(text: string): { fields: Record<string, string>; body: string } {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!match) return { fields: {}, body: text };
  const fields: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const pair = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
    if (pair) fields[pair[1]] = pair[2].replace(/^["']|["']$/g, "").trim();
  }
  return { fields, body: text.slice(match[0].length) };
}

/** The first `# Title` of a Markdown text, if it has one. */
export const firstHeading = (text: string) => /^#\s+(.+)$/m.exec(text)?.[1].trim();

/** "runbooks/checkout-rollback.md" → "checkout-rollback". */
export const baseName = (path: string) => path.replace(/^.*\//, "").replace(/\.[^.]+$/, "");
