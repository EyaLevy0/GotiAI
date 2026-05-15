import * as vscode from "vscode";
import type { WorkspaceIndexer } from "../indexing/workspace/workspaceIndexer.js";

/**
 * Status-bar indicator. Lives bottom-right, click opens the sidebar.
 *
 *   $(godot-icon) Godot 4.3 · 42 scripts
 *
 * Updates on every index change. We keep this minimal — the sidebar is where
 * detail lives; the status bar is presence and a click target.
 */
export class StatusBar implements vscode.Disposable {
  private readonly item: vscode.StatusBarItem;

  constructor(private readonly workspace: WorkspaceIndexer) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.command = "godotContext.openSidebar";
    this.item.tooltip = "Godot Context Agent — click to open sidebar";
    this.update();
    workspace.onChange(() => this.update());
  }

  private update(): void {
    const idx = this.workspace.getIndex();
    if (idx.scripts.size === 0 && idx.scenes.size === 0) {
      this.item.text = "$(circle-slash) Godot Context: no scripts";
    } else {
      const ver = idx.projectGodotVersion ?? "4.x";
      this.item.text = `$(symbol-class) Godot ${ver} · ${idx.scripts.size} scripts`;
    }
    this.item.show();
  }

  dispose(): void { this.item.dispose(); }
}
