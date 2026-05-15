import * as vscode from "vscode";
import * as fs from "node:fs/promises";
import * as path from "node:path";
import type { Services } from "../types/index.js";

/**
 * The sidebar exists for two reasons:
 *  1. Show the user what's indexed (counts, autoloads, project Godot version).
 *  2. Let them preview the context block that *would* be sent to Copilot
 *     for a given query — invaluable for debugging "why did Copilot do X".
 *
 * The webview talks to the extension via postMessage. State is held in the
 * extension; the webview is rendering only.
 */
export class SidebarProvider implements vscode.WebviewViewProvider {
  static readonly viewType = "godotContext.sidebar";
  private view: vscode.WebviewView | null = null;

  constructor(
    private readonly services: Services,
    private readonly extensionUri: vscode.Uri,
  ) {
    services.workspace.onChange(() => this.postIndexState());
  }

  async resolveWebviewView(view: vscode.WebviewView): Promise<void> {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "dist", "ui", "webview")],
    };
    view.webview.html = await this.html(view.webview);

    view.webview.onDidReceiveMessage(async (msg: InboundMessage) => {
      switch (msg.type) {
        case "ready":   this.postIndexState(); break;
        case "preview": await this.handlePreview(msg.query); break;
        case "reindex": await this.services.workspace.fullScan(); break;
        case "apiSearch": this.handleApiSearch(msg.query); break;
        case "openDocs": vscode.env.openExternal(vscode.Uri.parse(msg.url)); break;
        case "openFile": {
          const doc = await vscode.workspace.openTextDocument(vscode.Uri.parse(msg.uri));
          await vscode.window.showTextDocument(doc);
          break;
        }
      }
    });
  }

  private handleApiSearch(query: string): void {
    if (!this.view) return;
    let results: Array<{ name: string; brief: string; inherits: string | null; url: string }>;
    if (query.trim() === "") {
      // Browse mode — show a sample of the catalog
      const sample: typeof results = [];
      let n = 0;
      for (const c of this.services.api.iterClasses()) {
        if (n++ >= 25) break;
        sample.push({
          name: c.name, brief: c.brief, inherits: c.inherits,
          url: this.services.api.toGodotDocsUrl(c.name),
        });
      }
      results = sample;
    } else {
      results = this.services.api.search(query, 12).map(c => ({
        name: c.name, brief: c.brief, inherits: c.inherits,
        url: this.services.api.toGodotDocsUrl(c.name),
      }));
    }
    this.post({ type: "apiResults", results });
  }

  private async handlePreview(query: string): Promise<void> {
    if (!this.view) return;
    if (!query.trim()) {
      this.post({ type: "preview", markdown: "*Type a query above to preview the context block.*", tokens: 0 });
      return;
    }
    const cfg = vscode.workspace.getConfiguration("godotContext");
    const maxTokens = cfg.get<number>("maxContextTokens", 2000);
    const q = this.services.retriever.buildQuery(query);
    const result = await this.services.retriever.retrieve(q);
    const block = await this.services.builder.build(result, query, maxTokens);
    this.post({ type: "preview", markdown: block.markdown, tokens: block.estimatedTokens });
  }

  private postIndexState(): void {
    if (!this.view) return;
    const idx = this.services.workspace.getIndex();
    this.post({
      type: "index",
      data: {
        scripts: idx.scripts.size,
        scenes: idx.scenes.size,
        autoloads: idx.autoloads.map(a => ({ name: a.name, path: a.path, singleton: a.singleton })),
        projectGodotVersion: idx.projectGodotVersion,
        lastFullScan: idx.lastFullScan,
      },
    });
  }

  private post(msg: OutboundMessage): void {
    this.view?.webview.postMessage(msg);
  }

  private async html(webview: vscode.Webview): Promise<string> {
    const root = vscode.Uri.joinPath(this.extensionUri, "dist", "ui", "webview");
    const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(root, "panel.css"));
    const jsUri  = webview.asWebviewUri(vscode.Uri.joinPath(root, "panel.js"));
    const htmlPath = path.join(root.fsPath, "panel.html");
    let html = await fs.readFile(htmlPath, "utf8");
    const nonce = makeNonce();
    html = html
      .replace(/__CSP_SOURCE__/g, webview.cspSource)
      .replace(/__NONCE__/g, nonce)
      .replace(/__CSS_URI__/g, cssUri.toString())
      .replace(/__JS_URI__/g, jsUri.toString());
    return html;
  }
}

function makeNonce(): string {
  let s = "";
  const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  for (let i = 0; i < 32; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return s;
}

// ── messages ────────────────────────────────────────────────────────────────

type InboundMessage =
  | { type: "ready" }
  | { type: "preview"; query: string }
  | { type: "reindex" }
  | { type: "apiSearch"; query: string }
  | { type: "openDocs"; url: string }
  | { type: "openFile"; uri: string };

type OutboundMessage =
  | { type: "preview"; markdown: string; tokens: number }
  | { type: "apiResults"; results: Array<{ name: string; brief: string; inherits: string | null; url: string }> }
  | { type: "index"; data: {
      scripts: number;
      scenes: number;
      autoloads: Array<{ name: string; path: string; singleton: boolean }>;
      projectGodotVersion: string | null;
      lastFullScan: number;
    } };
