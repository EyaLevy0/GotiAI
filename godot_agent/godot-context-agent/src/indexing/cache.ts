import * as vscode from "vscode";
import * as fs from "node:fs/promises";
import * as path from "node:path";
import type { WorkspaceIndex } from "../types/index.js";

const CACHE_FILE = ".vscode/godot-context-cache.json";
const CACHE_VERSION = 1;

interface SerializedIndex {
  version: number;
  scripts:   Array<[string, ReturnType<typeof tagScript>]>;
  scenes:    Array<[string, unknown]>;
  autoloads: unknown[];
  projectGodotVersion: string | null;
  lastFullScan: number;
}

function tagScript<T>(s: T): T { return s; } // type marker only

export class IndexCache {
  constructor(private readonly root: vscode.WorkspaceFolder) {}

  private file(): string { return path.join(this.root.uri.fsPath, CACHE_FILE); }

  async load(): Promise<WorkspaceIndex | null> {
    try {
      const raw = await fs.readFile(this.file(), "utf8");
      const data = JSON.parse(raw) as SerializedIndex;
      if (data.version !== CACHE_VERSION) return null;
      return {
        scripts:   new Map(data.scripts as never),
        scenes:    new Map(data.scenes as never),
        autoloads: data.autoloads as never,
        projectGodotVersion: data.projectGodotVersion,
        lastFullScan: data.lastFullScan,
      };
    } catch {
      return null;
    }
  }

  async save(index: WorkspaceIndex): Promise<void> {
    const data: SerializedIndex = {
      version: CACHE_VERSION,
      scripts:   [...index.scripts.entries()],
      scenes:    [...index.scenes.entries()],
      autoloads: index.autoloads,
      projectGodotVersion: index.projectGodotVersion,
      lastFullScan: index.lastFullScan,
    };
    await fs.mkdir(path.dirname(this.file()), { recursive: true });
    await fs.writeFile(this.file(), JSON.stringify(data));
  }
}
