import { createHash } from "node:crypto";
import type { GdScriptFile, GdScriptSymbol } from "../../types/index.js";

/**
 * Lightweight GDScript extractor. We do NOT build an AST — only enough to
 * answer: what does this file extend, what is its class_name, what functions
 * does it define, what signals does it emit. That's all retrieval needs.
 *
 * GDScript is whitespace-sensitive and line-oriented; regex is sufficient
 * when applied to stripped, comment-free lines.
 */
export class GdScriptParser {
  parse(uri: string, relPath: string, source: string): GdScriptFile {
    const lines = source.split("\n");
    const symbols: GdScriptSymbol[] = [];
    let extendsName: string | null = null;
    let className: string | null = null;

    // Single-pass scan. Track function boundaries by indentation.
    let openFn: { idx: number; indent: number } | null = null;

    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i]!;
      const line = stripComment(raw);
      if (!line.trim()) {
        if (openFn && raw.length === 0) continue;
        continue;
      }

      // Close pending function when we leave its indent block.
      if (openFn) {
        const indent = leadingSpaces(raw);
        if (line.trim().length > 0 && indent <= openFn.indent && !/^\s*$/.test(raw)) {
          symbols[openFn.idx]!.endLine = i - 1;
          openFn = null;
        }
      }

      let m: RegExpMatchArray | null;

      if ((m = line.match(/^\s*extends\s+([A-Za-z_][\w]*)/))) {
        extendsName = m[1]!;
        continue;
      }
      if ((m = line.match(/^\s*class_name\s+([A-Za-z_][\w]*)/))) {
        className = m[1]!;
        symbols.push({ kind: "class_name", name: m[1]!, signature: line.trim(), line: i, endLine: i });
        continue;
      }
      if ((m = line.match(/^\s*signal\s+([A-Za-z_][\w]*)\s*(\([^)]*\))?/))) {
        symbols.push({
          kind: "signal", name: m[1]!,
          signature: line.trim(), line: i, endLine: i,
        });
        continue;
      }
      if ((m = line.match(/^(\s*)func\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)\s*(->\s*[^:]+)?\s*:/))) {
        const idx = symbols.push({
          kind: "function", name: m[2]!,
          signature: `func ${m[2]}(${m[3]?.trim() ?? ""})${m[4] ? " " + m[4].trim() : ""}`,
          line: i, endLine: i,
        }) - 1;
        openFn = { idx, indent: m[1]!.length };
        continue;
      }
      if ((m = line.match(/^\s*(?:@export\s+(?:var|@export.*var)|var|const)\s+([A-Za-z_][\w]*)\s*(?::\s*[A-Za-z_][\w\[\],\s]*)?\s*(?:=\s*(.+))?$/))) {
        const isConst = /^\s*const\s/.test(line);
        symbols.push({
          kind: isConst ? "constant" : "variable", name: m[1]!,
          signature: line.trim(), line: i, endLine: i,
        });
        continue;
      }
    }

    if (openFn) symbols[openFn.idx]!.endLine = lines.length - 1;

    return {
      uri, relPath,
      extends: extendsName,
      className,
      symbols,
      hash: createHash("sha256").update(source).digest("hex").slice(0, 16),
      size: source.length,
      indexedAt: Date.now(),
    };
  }
}

function stripComment(line: string): string {
  // Naive — fine for our purposes since we never enter a string before parsing.
  const i = line.indexOf("#");
  return i === -1 ? line : line.slice(0, i);
}

function leadingSpaces(s: string): number {
  let n = 0;
  while (n < s.length && (s[n] === " " || s[n] === "\t")) n++;
  return n;
}
