// All shared types live here. Keeping them centralized prevents circular imports
// between indexing/retrieval/context modules, which all reference these shapes.

import type * as vscode from "vscode";

// ─── Godot API index ─────────────────────────────────────────────────────────

export interface GodotApiClass {
  name: string;
  inherits: string | null;
  brief: string;
  description: string;
  /** Top-level since-version, e.g. "4.0". Used for filtering on godotVersion. */
  since: string;
  methods: GodotApiMethod[];
  signals: GodotApiSignal[];
  properties: GodotApiProperty[];
  /** True when the official docs list this class as deprecated. */
  deprecated?: boolean;
}

export interface GodotApiMethod {
  name: string;
  returnType: string;
  args: Array<{ name: string; type: string; default?: string }>;
  description: string;
  qualifiers?: string; // "static", "const", "virtual"
  deprecated?: boolean;
}

export interface GodotApiSignal {
  name: string;
  args: Array<{ name: string; type: string }>;
  description: string;
}

export interface GodotApiProperty {
  name: string;
  type: string;
  default: string;
  description: string;
  deprecated?: boolean;
}

// ─── Workspace index ─────────────────────────────────────────────────────────

export interface GdScriptSymbol {
  kind: "function" | "signal" | "variable" | "constant" | "class_name";
  name: string;
  signature: string;
  line: number;
  /** Approximate end line of the body, used to slice snippets. */
  endLine: number;
  comment?: string;
}

export interface GdScriptFile {
  uri: string;
  relPath: string;
  extends: string | null;
  className: string | null;
  symbols: GdScriptSymbol[];
  /** sha256 of file contents — cheap change detection. */
  hash: string;
  size: number;
  /** ms epoch */
  indexedAt: number;
}

export interface TscnNode {
  name: string;
  type: string;
  parent: string | null;
  script?: string;
}

export interface TscnFile {
  uri: string;
  relPath: string;
  rootType: string | null;
  nodes: TscnNode[];
  scripts: string[]; // referenced .gd paths
  hash: string;
}

export interface Autoload {
  name: string;
  path: string;
  singleton: boolean;
}

export interface WorkspaceIndex {
  scripts: Map<string, GdScriptFile>; // key: relPath
  scenes:  Map<string, TscnFile>;
  autoloads: Autoload[];
  /** Inferred Godot version from project.godot, or null if unknown. */
  projectGodotVersion: string | null;
  lastFullScan: number;
}

// ─── Retrieval ───────────────────────────────────────────────────────────────

export interface RetrievalQuery {
  /** The raw user request (e.g. "create a 2d enemy ai"). */
  text: string;
  /** Extracted symbol-ish tokens used for matching. */
  terms: string[];
  /** Active editor URI if any — boosts same-directory results. */
  activeUri?: string;
  /** Caller can hint at intent — affects template/doc preference. */
  intent?: "implementation" | "lookup" | "template" | "explain";
}

export interface RankedHit<T> {
  item: T;
  score: number;
  /** Human-readable explanation, surfaced in the sidebar. */
  reasons: string[];
}

export interface RetrievalResult {
  apiHits: RankedHit<GodotApiClass>[];
  scriptHits: RankedHit<GdScriptFile>[];
  sceneHits: RankedHit<TscnFile>[];
  autoloadHits: Autoload[];
  /** Aggregate token budget used by the formatted context block. */
  estimatedTokens: number;
}

// ─── Context block (what we hand to Copilot) ─────────────────────────────────

export interface ContextBlock {
  /** Markdown-formatted, ready to inject. */
  markdown: string;
  /** Structured references for vscode.chat. */
  references: vscode.Uri[];
  estimatedTokens: number;
  /** Brief outline shown to the user before Copilot generates. */
  summary: string;
}

// ─── DI container ────────────────────────────────────────────────────────────

export interface Services {
  api:       import("../indexing/godotApi/apiIndex.js").GodotApiIndex;
  workspace: import("../indexing/workspace/workspaceIndexer.js").WorkspaceIndexer;
  retriever: import("../retrieval/retriever.js").Retriever;
  builder:   import("../context/contextBuilder.js").ContextBuilder;
  logger:    import("../util/logger.js").Logger;
}
