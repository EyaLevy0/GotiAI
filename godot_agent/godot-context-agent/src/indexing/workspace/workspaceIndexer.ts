import * as vscode from "vscode";
import * as path from "node:path";
import { GdScriptParser } from "./gdscriptParser.js";
import { TscnParser } from "./tscnParser.js";
import { ProjectGodotParser } from "./projectGodotParser.js";
import { IndexCache } from "../cache.js";
import type { WorkspaceIndex } from "../../types/index.js";
import type { Logger } from "../../util/logger.js";

/**
 * Orchestrates building and maintaining the workspace index.
 *
 * Strategy:
 *  - On activation, attempt to load cached index from .vscode/godot-context-cache.json.
 *  - In parallel, find changed files (by hash) and re-parse only those.
 *  - Register FileSystemWatchers for incremental updates after that.
 *  - Honor a file count budget (workspaceFileLimit) — huge projects might have
 *    addon dirs we don't need to touch.
 */
export class WorkspaceIndexer {
  private gdParser = new GdScriptParser();
  private tscnParser = new TscnParser();
  private projParser = new ProjectGodotParser();

  private index: WorkspaceIndex = emptyIndex();
  private root: vscode.WorkspaceFolder | null = null;
  private cache: IndexCache | null = null;
  private watcher: vscode.FileSystemWatcher | null = null;

  private readonly onChangeEmitter = new vscode.EventEmitter<void>();
  /** Fires when the index changes. The sidebar listens. */
  readonly onChange = this.onChangeEmitter.event;

  constructor(private readonly logger: Logger) {}

  getIndex(): WorkspaceIndex { return this.index; }

  async initialize(): Promise<void> {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
      this.logger.info("No workspace folder; workspace indexing skipped.");
      return;
    }
    this.root = folders[0]!;
    this.cache = new IndexCache(this.root);

    const cached = await this.cache.load();
    if (cached) {
      this.index = cached;
      this.logger.info(`Loaded cached index: ${cached.scripts.size} scripts, ${cached.scenes.size} scenes`);
    }

    await this.fullScan();
    this.installWatcher();
  }

  /** Re-scan everything. Cheap if cache is warm (only re-parses changed files). */
  async fullScan(): Promise<void> {
    if (!this.root) return;
    const config = vscode.workspace.getConfiguration("godotContext");
    const fileLimit = config.get<number>("workspaceFileLimit", 200);

    // project.godot first — autoloads inform later ranking.
    const projUri = vscode.Uri.joinPath(this.root.uri, "project.godot");
    try {
      const bytes = await vscode.workspace.fs.readFile(projUri);
      const info = this.projParser.parse(Buffer.from(bytes).toString("utf8"));
      this.index.autoloads = info.autoloads;
      this.index.projectGodotVersion = info.godotVersion;
    } catch { /* not a Godot project root, that's fine */ }

    const gdFiles   = await vscode.workspace.findFiles("**/*.gd",   "**/{node_modules,.godot,addons/**/test}/**", fileLimit);
    const tscnFiles = await vscode.workspace.findFiles("**/*.tscn", "**/{node_modules,.godot}/**",                fileLimit);

    let parsed = 0, skipped = 0;
    for (const uri of gdFiles) {
      const relPath = vscode.workspace.asRelativePath(uri);
      try {
        const bytes = await vscode.workspace.fs.readFile(uri);
        const src = Buffer.from(bytes).toString("utf8");
        const existing = this.index.scripts.get(relPath);
        const newFile = this.gdParser.parse(uri.toString(), relPath, src);
        if (existing && existing.hash === newFile.hash) { skipped++; continue; }
        this.index.scripts.set(relPath, newFile);
        parsed++;
      } catch (e) {
        this.logger.warn(`Failed to parse ${relPath}`, (e as Error).message);
      }
    }

    for (const uri of tscnFiles) {
      const relPath = vscode.workspace.asRelativePath(uri);
      try {
        const bytes = await vscode.workspace.fs.readFile(uri);
        const src = Buffer.from(bytes).toString("utf8");
        const existing = this.index.scenes.get(relPath);
        const newFile = this.tscnParser.parse(uri.toString(), relPath, src);
        if (existing && existing.hash === newFile.hash) continue;
        this.index.scenes.set(relPath, newFile);
      } catch (e) {
        this.logger.warn(`Failed to parse ${relPath}`, (e as Error).message);
      }
    }

    this.index.lastFullScan = Date.now();
    await this.cache?.save(this.index);
    this.logger.info(`Workspace scan: parsed=${parsed} skipped=${skipped} scenes=${this.index.scenes.size}`);
    this.onChangeEmitter.fire();
  }

  private installWatcher(): void {
    if (!this.root) return;
    this.watcher?.dispose();
    const pattern = new vscode.RelativePattern(this.root, "**/*.{gd,tscn,godot}");
    const watcher = vscode.workspace.createFileSystemWatcher(pattern);
    watcher.onDidCreate(uri => void this.onFileTouched(uri));
    watcher.onDidChange(uri => void this.onFileTouched(uri));
    watcher.onDidDelete(uri => void this.onFileDeleted(uri));
    this.watcher = watcher;
  }

  private async onFileTouched(uri: vscode.Uri): Promise<void> {
    const rel = vscode.workspace.asRelativePath(uri);
    const ext = path.extname(rel);
    try {
      const bytes = await vscode.workspace.fs.readFile(uri);
      const src = Buffer.from(bytes).toString("utf8");
      if (ext === ".gd") {
        const parsed = this.gdParser.parse(uri.toString(), rel, src);
        this.index.scripts.set(rel, parsed);
      } else if (ext === ".tscn") {
        const parsed = this.tscnParser.parse(uri.toString(), rel, src);
        this.index.scenes.set(rel, parsed);
      } else if (rel === "project.godot") {
        const info = this.projParser.parse(src);
        this.index.autoloads = info.autoloads;
        this.index.projectGodotVersion = info.godotVersion;
      }
      await this.cache?.save(this.index);
      this.onChangeEmitter.fire();
    } catch (e) {
      this.logger.warn(`watcher: failed on ${rel}`, (e as Error).message);
    }
  }

  private async onFileDeleted(uri: vscode.Uri): Promise<void> {
    const rel = vscode.workspace.asRelativePath(uri);
    this.index.scripts.delete(rel);
    this.index.scenes.delete(rel);
    await this.cache?.save(this.index);
    this.onChangeEmitter.fire();
  }

  dispose(): void {
    this.watcher?.dispose();
    this.onChangeEmitter.dispose();
  }
}

function emptyIndex(): WorkspaceIndex {
  return {
    scripts: new Map(),
    scenes: new Map(),
    autoloads: [],
    projectGodotVersion: null,
    lastFullScan: 0,
  };
}
