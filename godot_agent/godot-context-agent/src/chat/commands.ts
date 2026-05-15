import * as vscode from "vscode";
import type { Services } from "../types/index.js";
import { FileGenerator } from "../generation/fileGenerator.js";

export function registerCommands(
  services: Services,
  generator: FileGenerator,
): vscode.Disposable[] {
  const out: vscode.Disposable[] = [];

  out.push(vscode.commands.registerCommand("godotContext.reindex", async () => {
    await services.workspace.fullScan();
    const idx = services.workspace.getIndex();
    vscode.window.showInformationMessage(
      `Godot Context: re-indexed ${idx.scripts.size} scripts, ${idx.scenes.size} scenes.`,
    );
  }));

  out.push(vscode.commands.registerCommand("godotContext.openSidebar", async () => {
    await vscode.commands.executeCommand("workbench.view.extension.godot-context-agent");
  }));

  out.push(vscode.commands.registerCommand("godotContext.searchApi", async () => {
    const q = await vscode.window.showInputBox({
      prompt: "Search Godot 4.x API (class, method, signal)",
      placeHolder: "e.g. CharacterBody2D or move_and_slide",
    });
    if (!q) return;
    const classes = services.api.search(q, 12);
    if (!classes.length) { vscode.window.showInformationMessage("No matches."); return; }

    interface ApiPickItem extends vscode.QuickPickItem { url: string; }
    const items: ApiPickItem[] = classes.map(c => {
      const item: ApiPickItem = {
        label: c.name,
        detail: c.brief,
        url: services.api.toGodotDocsUrl(c.name),
      };
      if (c.inherits) item.description = `extends ${c.inherits}`;
      return item;
    });

    const pick = await vscode.window.showQuickPick<ApiPickItem>(items, {
      placeHolder: `${classes.length} match(es) — pick to open docs`,
    });
    if (pick) vscode.env.openExternal(vscode.Uri.parse(pick.url));
  }));

  out.push(vscode.commands.registerCommand("godotContext.generateScript", async (templateId?: string) => {
    if (typeof templateId === "string" && templateId.length > 0) {
      await generator.writeTemplateById(templateId);
    } else {
      await generator.pickAndGenerate();
    }
  }));

  return out;
}
