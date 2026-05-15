import * as vscode from "vscode";
import type {
  RetrievalResult, ContextBlock, GodotApiClass,
  RankedHit,
} from "../types/index.js";
import type { GodotApiIndex } from "../indexing/godotApi/apiIndex.js";
import { Compressor, type CompressedSnippet } from "../retrieval/compressor.js";
import { estimateTokens } from "../retrieval/tokenizer.js";

/**
 * Turns retrieval results into a single Markdown block. The block follows a
 * deliberate structure that tracks well with how Copilot weighs context:
 *
 *   1. ENGINE BANNER  — explicit Godot 4.x assertion (kills 3.x hallucination)
 *   2. AUTOLOADS      — short list of available singletons in this project
 *   3. API REFERENCE  — only the methods/signals that match the query
 *   4. PROJECT CODE   — compressed snippets from matched .gd files
 *   5. SCENE CONTEXT  — node trees if relevant
 *   6. MIGRATION NOTES — Godot 3 idents found in retrieved code (if enabled)
 *
 * Each section is delimited so Copilot treats them as distinct evidence.
 */
export class ContextBuilder {
  private compressor = new Compressor();

  constructor(private readonly api: GodotApiIndex) {}

  async build(result: RetrievalResult, query: string, maxTokens: number): Promise<ContextBlock> {
    const parts: string[] = [];
    const references: vscode.Uri[] = [];
    const compressedSnippets: CompressedSnippet[] = [];

    parts.push(this.banner());
    let used = estimateTokens(parts.join("\n\n"));

    // Autoloads — small, always include if any.
    if (result.autoloadHits.length) {
      const block = this.autoloadsBlock(result.autoloadHits);
      const cost = estimateTokens(block);
      if (used + cost < maxTokens) { parts.push(block); used += cost; }
    }

    // API hits — bound to ~30% of budget
    const apiBudget = Math.floor(maxTokens * 0.35);
    for (const hit of result.apiHits) {
      const block = this.apiClassBlock(hit, query);
      const cost = estimateTokens(block);
      if (used + cost > maxTokens) break;
      if (cost > apiBudget && parts.length > 2) break;
      parts.push(block);
      used += cost;
    }

    // Project scripts — the highest-leverage section
    const matchedTerms = new Set<string>();
    for (const h of result.apiHits) matchedTerms.add(h.item.name.toLowerCase());
    for (const term of query.toLowerCase().split(/[^a-z0-9_]+/)) if (term) matchedTerms.add(term);

    const projectHeader = "## Project code (most relevant)";
    let pushedProjectHeader = false;
    for (const hit of result.scriptHits) {
      const snippet = await this.compressor.compress(hit.item, matchedTerms);
      const heading = `### ${snippet.relPath}\n*Reasons: ${hit.reasons.join("; ")}*`;
      const block = `${heading}\n\n\`\`\`gdscript\n${snippet.body}\n\`\`\``;
      const cost = estimateTokens(block) + (pushedProjectHeader ? 0 : 6);
      if (used + cost > maxTokens) break;
      if (!pushedProjectHeader) { parts.push(projectHeader); pushedProjectHeader = true; used += 6; }
      parts.push(block);
      used += cost - (pushedProjectHeader ? 0 : 6);
      references.push(vscode.Uri.parse(hit.item.uri));
      compressedSnippets.push(snippet);
    }

    // Scenes — node tree summary, cheap
    if (result.sceneHits.length) {
      const block = this.scenesBlock(result.sceneHits);
      const cost = estimateTokens(block);
      if (used + cost < maxTokens) {
        parts.push(block);
        used += cost;
        for (const hit of result.sceneHits) references.push(vscode.Uri.parse(hit.item.uri));
      }
    }

    // Migration notes — if retrieved code references Godot 3 identifiers,
    // tell Copilot explicitly to use the 4.x equivalent. Gated by setting.
    const cfg = vscode.workspace.getConfiguration("godotContext");
    if (cfg.get<boolean>("warnOnGodot3Api", true)) {
      const migration = this.migrationBlock(compressedSnippets);
      if (migration) {
        const cost = estimateTokens(migration);
        if (used + cost < maxTokens) { parts.push(migration); used += cost; }
      }
    }

    parts.push(this.footer());

    const markdown = parts.join("\n\n");
    return {
      markdown,
      references,
      estimatedTokens: estimateTokens(markdown),
      summary: this.summaryLine(result),
    };
  }

  private banner(): string {
    const cfg = vscode.workspace.getConfiguration("godotContext");
    const ver = cfg.get<string>("godotVersion", "4.x");
    return [
      `## Engine context`,
      `**Target engine:** Godot **${ver}**. Use **GDScript 2** syntax exclusively.`,
      `- Use \`CharacterBody2D\`/\`CharacterBody3D\` (not \`KinematicBody*\`).`,
      `- Use \`@export var foo: Type\` (not \`export var foo\`).`,
      `- Use \`signal.connect(callable)\` (not \`connect("signal", target, "method")\`).`,
      `- Use \`PackedStringArray\` (not \`PoolStringArray\`).`,
      `- Use \`await\` on signals (not yield).`,
    ].join("\n");
  }

  private autoloadsBlock(autoloads: RetrievalResult["autoloadHits"]): string {
    const rows = autoloads.map(a =>
      `- \`${a.name}\` ${a.singleton ? "(singleton)" : ""} → \`${a.path}\``
    ).join("\n");
    return `## Available autoloads in this project\n${rows}`;
  }

  private apiClassBlock(hit: RankedHit<GodotApiClass>, _query: string): string {
    const c = hit.item;
    const lines: string[] = [];
    lines.push(`### Godot API · \`${c.name}\` extends \`${c.inherits ?? "Object"}\``);
    lines.push(`> ${c.brief}`);

    if (c.methods.length) {
      lines.push(`**Key methods (Godot ${c.since}+):**`);
      for (const m of c.methods.slice(0, 6)) {
        const args = m.args.map(a => `${a.name}: ${a.type}${a.default ? " = " + a.default : ""}`).join(", ");
        const dep = m.deprecated ? " ⚠️ deprecated" : "";
        lines.push(`- \`${m.name}(${args}) -> ${m.returnType}\`${dep} — ${m.description}`);
      }
    }
    if (c.signals.length) {
      lines.push(`**Signals:**`);
      for (const s of c.signals.slice(0, 4)) {
        const args = s.args.map(a => `${a.name}: ${a.type}`).join(", ");
        lines.push(`- \`${s.name}(${args})\` — ${s.description}`);
      }
    }
    if (c.properties.length) {
      lines.push(`**Properties:**`);
      for (const p of c.properties.slice(0, 4)) {
        lines.push(`- \`${p.name}: ${p.type}${p.default ? " = " + p.default : ""}\``);
      }
    }
    return lines.join("\n");
  }

  private scenesBlock(scenes: RetrievalResult["sceneHits"]): string {
    const out: string[] = [`## Related scenes`];
    for (const hit of scenes) {
      out.push(`### ${hit.item.relPath}  *(root: ${hit.item.rootType ?? "?"})*`);
      out.push("```");
      for (const node of hit.item.nodes.slice(0, 12)) {
        const indent = (node.parent ?? "").split("/").length - 1;
        out.push(`${"  ".repeat(Math.max(0, indent))}${node.name} : ${node.type}${node.script ? "  ← " + node.script : ""}`);
      }
      out.push("```");
    }
    return out.join("\n");
  }

  /**
   * Scan retrieved snippets for Godot 3 identifiers. When found, surface a
   * migration block so Copilot knows that even if it sees `KinematicBody2D`
   * in project code, the project is mid-migration and 4.x replacements are
   * the correct target. Without this, Copilot can mirror the legacy idiom.
   */
  private migrationBlock(snippets: CompressedSnippet[]): string | null {
    const found = new Map<string, { replacement: string; note: string; files: Set<string> }>();
    // Match identifier-like tokens at word boundaries.
    const idRe = /\b[A-Za-z_][A-Za-z0-9_]*\b/g;
    for (const s of snippets) {
      const seenInFile = new Set<string>();
      let m: RegExpExecArray | null;
      while ((m = idRe.exec(s.body)) !== null) {
        const tok = m[0];
        if (seenInFile.has(tok)) continue;
        const hit = this.api.isGodot3Identifier(tok);
        if (!hit) continue;
        seenInFile.add(tok);
        let entry = found.get(tok);
        if (!entry) {
          entry = { replacement: hit.replacement, note: hit.note, files: new Set() };
          found.set(tok, entry);
        }
        entry.files.add(s.relPath);
      }
    }
    if (found.size === 0) return null;

    const lines = [
      `## ⚠️ Godot 3 → 4 migration notes`,
      `The retrieved code references legacy identifiers. **Generate Godot 4.x replacements, not the legacy forms below:**`,
    ];
    for (const [legacy, info] of found) {
      const files = [...info.files].slice(0, 3).join(", ");
      lines.push(`- \`${legacy}\` → \`${info.replacement}\` — ${info.note}. *Seen in: ${files}*`);
    }
    return lines.join("\n");
  }

  private footer(): string {
    return [
      `---`,
      `*This context was assembled by Godot Context Agent. Treat the engine version banner as authoritative — prefer the symbols and patterns shown above over any Godot 3.x recollection.*`,
    ].join("\n");
  }

  private summaryLine(r: RetrievalResult): string {
    return `Found ${r.apiHits.length} API class(es), ${r.scriptHits.length} project file(s), ${r.sceneHits.length} scene(s), ${r.autoloadHits.length} autoload(s).`;
  }
}
