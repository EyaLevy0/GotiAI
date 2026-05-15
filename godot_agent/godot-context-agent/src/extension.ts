import * as vscode from "vscode";
import { Logger } from "./util/logger.js";
import { DisposableBag } from "./util/disposables.js";
import { GodotApiIndex } from "./indexing/godotApi/apiIndex.js";
import { WorkspaceIndexer } from "./indexing/workspace/workspaceIndexer.js";
import { Retriever } from "./retrieval/retriever.js";
import { ContextBuilder } from "./context/contextBuilder.js";
import { FileGenerator } from "./generation/fileGenerator.js";
import { SidebarProvider } from "./ui/sidebarProvider.js";
import { StatusBar } from "./ui/statusBar.js";
import { registerChatParticipant } from "./chat/participant.js";
import { registerCommands } from "./chat/commands.js";
import type { Services } from "./types/index.js";

/**
 * Activation contract: construct all services, register UI and chat surfaces,
 * and return one Disposable bag. No top-level globals, no singletons outside
 * the closure. Hot-reload survives this layout cleanly.
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const bag = new DisposableBag();
  const logger = new Logger();
  bag.push(logger);

  logger.info("Godot Context Agent activating…");

  // 1. Load static API index
  const api = new GodotApiIndex(logger);
  try {
    await api.load(context.extensionPath);
  } catch (e) {
    vscode.window.showErrorMessage(
      "Godot Context Agent: failed to load API index. Some features will be limited.",
    );
    logger.error("API index load failed", e);
  }

  // 2. Build workspace index (async, but we want to await first pass)
  const workspace = new WorkspaceIndexer(logger);
  await workspace.initialize();
  bag.push({ dispose: () => workspace.dispose() });

  // 3. Retrieval + context formatting
  const retriever = new Retriever(api, workspace);
  const builder   = new ContextBuilder(api);

  // 4. Compose service container — explicit, no DI magic
  const services: Services = { api, workspace, retriever, builder, logger };

  // 5. Generator (optional file output)
  const generator = new FileGenerator(logger);

  // 6. Register surfaces
  bag.push(registerChatParticipant(services, context));
  for (const d of registerCommands(services, generator)) bag.push(d);

  const sidebar = new SidebarProvider(services, context.extensionUri);
  bag.push(vscode.window.registerWebviewViewProvider(
    SidebarProvider.viewType,
    sidebar,
    { webviewOptions: { retainContextWhenHidden: true } },
  ));

  const statusBar = new StatusBar(workspace);
  bag.push(statusBar);

  context.subscriptions.push(bag);
  logger.info("Godot Context Agent ready.");
}

export function deactivate(): void {
  // All disposables are owned by context.subscriptions — VS Code will dispose them.
}
