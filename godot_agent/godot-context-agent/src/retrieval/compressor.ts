import * as vscode from "vscode";
import type { GdScriptFile } from "../types/index.js";
import { estimateTokens, trimToTokens } from "./tokenizer.js";

/**
 * Compression strategy:
 *  1. For each ranked script, keep its `class_name`/`extends` declaration.
 *  2. For functions whose name overlaps the query, include the full body.
 *  3. For other functions, include only the signature with `# ...` body.
 *  4. Strip comments and blank-line runs.
 *  5. Hard-cap output per file to ~maxPerFile tokens.
 */
export interface CompressedSnippet {
  relPath: string;
  body: string;
  tokens: number;
}

export class Compressor {
  async compress(
    file: GdScriptFile,
    matchedTerms: Set<string>,
    maxTokensPerFile = 400,
  ): Promise<CompressedSnippet> {
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.parse(file.uri));
    const lines = doc.getText().split("\n");
    const out: string[] = [];

    // Preserve `extends` and `class_name` lines verbatim — they anchor type info.
    for (let i = 0; i < Math.min(lines.length, 8); i++) {
      const t = (lines[i] ?? "").trim();
      if (t.startsWith("extends ") || t.startsWith("class_name ")) out.push(lines[i]!);
    }

    // Signals first — they're cheap and high-signal.
    const signalSyms = file.symbols.filter(s => s.kind === "signal");
    for (const s of signalSyms) out.push(s.signature);

    if (signalSyms.length) out.push("");

    // Functions: full body for matched, signature-only for the rest.
    for (const sym of file.symbols.filter(s => s.kind === "function")) {
      const isMatch =
        matchedTerms.has(sym.name.toLowerCase()) ||
        [...matchedTerms].some(t => sym.signature.toLowerCase().includes(t));
      if (isMatch) {
        const start = sym.line;
        const end   = Math.min(sym.endLine + 1, lines.length);
        const body  = lines.slice(start, end).map(stripCommentLine).filter(l => l.trim().length > 0).join("\n");
        out.push(body);
      } else {
        out.push(`${sym.signature}:\n\t# ...`);
      }
      out.push("");
    }

    let body = collapseBlankRuns(out.join("\n")).trim();
    let tokens = estimateTokens(body);
    if (tokens > maxTokensPerFile) {
      body = trimToTokens(body, maxTokensPerFile);
      tokens = estimateTokens(body);
    }
    return { relPath: file.relPath, body, tokens };
  }
}

function stripCommentLine(line: string): string {
  const i = line.indexOf("#");
  return i === -1 ? line : line.slice(0, i).trimEnd();
}

function collapseBlankRuns(s: string): string {
  return s.replace(/\n{3,}/g, "\n\n");
}
