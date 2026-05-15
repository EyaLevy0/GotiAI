import * as vscode from "vscode";
import * as path from "node:path";
import { TEMPLATES, findTemplate, type Template } from "../context/templates/index.js";
import type { Logger } from "../util/logger.js";

/**
 * Optional file generation. The extension is NOT a code generator — that's
 * Copilot's job. But for known-good patterns (state machines, autoloads),
 * giving the user a vetted starter is much more reliable than asking an LLM
 * to reinvent them. Anything else stays in Copilot's lane.
 */
export class FileGenerator {
  constructor(private readonly logger: Logger) {}

  async pickAndGenerate(): Promise<void> {
    const pick = await vscode.window.showQuickPick(
      TEMPLATES.map(t => ({
        label: t.title,
        description: t.id,
        detail: t.description,
        template: t,
      })),
      { placeHolder: "Choose a Godot 4.x template to insert" },
    );
    if (!pick) return;
    await this.writeTemplate(pick.template);
  }

  async writeTemplateById(id: string): Promise<vscode.Uri | null> {
    const t = findTemplate(id);
    if (!t) {
      vscode.window.showWarningMessage(`Unknown template: ${id}`);
      return null;
    }
    return this.writeTemplate(t);
  }

  private async writeTemplate(t: Template): Promise<vscode.Uri | null> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      vscode.window.showErrorMessage("Open a Godot project folder first.");
      return null;
    }

    const defaultName = `${t.id}.gd`;
    const uri = await vscode.window.showSaveDialog({
      defaultUri: vscode.Uri.joinPath(folder.uri, defaultName),
      filters: { "GDScript": ["gd"] },
      saveLabel: "Create script",
    });
    if (!uri) return null;

    await vscode.workspace.fs.writeFile(uri, Buffer.from(t.body, "utf8"));
    const rel = vscode.workspace.asRelativePath(uri);
    this.logger.info(`Generated template ${t.id} → ${rel}`);
    vscode.window.showInformationMessage(`Created ${path.basename(rel)} from "${t.title}".`);
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);
    return uri;
  }
}
