import * as vscode from "vscode";

/** Tiny aggregator so each module returns one disposable instead of many. */
export class DisposableBag implements vscode.Disposable {
  private readonly items: vscode.Disposable[] = [];

  push(...d: vscode.Disposable[]): void {
    this.items.push(...d);
  }

  dispose(): void {
    while (this.items.length) {
      try { this.items.pop()?.dispose(); } catch { /* swallow */ }
    }
  }
}
