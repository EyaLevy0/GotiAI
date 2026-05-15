import * as vscode from "vscode";
import type { Services } from "../types/index.js";
import { TEMPLATES, findTemplate } from "../context/templates/index.js";

/**
 * Registers the `@godot` chat participant.
 *
 * The participant does NOT generate code. It:
 *   1. Receives the user's prompt (with optional /command).
 *   2. Runs retrieval (API + workspace).
 *   3. Streams the formatted context block back into the chat panel using
 *      stream.markdown / stream.reference.
 *
 * Copilot Chat then has all of that context in-conversation when the user's
 * next message asks it to write code. The user can also re-invoke @godot
 * before each Copilot prompt to refresh context.
 */
export function registerChatParticipant(
  services: Services,
  context: vscode.ExtensionContext,
): vscode.Disposable {
  const handler: vscode.ChatRequestHandler = async (request, _chatContext, stream, token) => {
    const cfg = vscode.workspace.getConfiguration("godotContext");
    const maxTokens = cfg.get<number>("maxContextTokens", 2000);

    // Slash-command dispatch
    switch (request.command) {
      case "scan":     return handleScan(services, stream);
      case "template": return handleTemplate(request, stream);
      case "docs":     return handleDocs(request, services, stream, maxTokens);
      case "explain":  return handleExplain(request, services, stream, maxTokens);
      default:         return handleDefault(request, services, stream, maxTokens, token);
    }
  };

  const participant = vscode.chat.createChatParticipant("godot-context-agent.godot", handler);
  participant.iconPath = vscode.Uri.joinPath(context.extensionUri, "resources", "icon.svg");
  participant.followupProvider = {
    provideFollowups(_result, _chatContext, _token) {
      return [
        { prompt: "Now write the implementation using the context above.", label: "→ Ask Copilot to implement" },
        { prompt: "Insert a starter template instead.",                    label: "→ /template", command: "template" },
      ];
    },
  };
  return participant;
}

// ── default: full retrieval ─────────────────────────────────────────────────

async function handleDefault(
  request: vscode.ChatRequest,
  services: Services,
  stream: vscode.ChatResponseStream,
  maxTokens: number,
  _token: vscode.CancellationToken,
): Promise<void> {
  stream.progress("Indexing workspace…");
  const q = services.retriever.buildQuery(request.prompt);
  if (q.terms.length === 0) {
    stream.markdown("⚠️ Couldn't extract meaningful terms from your prompt. Try naming a Godot class, function, or feature.\n");
    return;
  }
  stream.progress(`Searching docs and project for: ${q.terms.join(", ")}`);
  const result = await services.retriever.retrieve(q);
  const block  = await services.builder.build(result, request.prompt, maxTokens);

  stream.markdown(`**${block.summary}** · ~${block.estimatedTokens} tokens.\n\n`);
  stream.markdown(block.markdown);

  for (const ref of block.references) stream.reference(ref);

  stream.markdown(
    "\n\n---\n*Use this context to prompt Copilot in your editor, or in chat ask: " +
    "\"Using the @godot context above, implement …\"*",
  );
}

// ── /scan: force a re-index ──────────────────────────────────────────────────

async function handleScan(services: Services, stream: vscode.ChatResponseStream): Promise<void> {
  stream.progress("Re-indexing workspace…");
  await services.workspace.fullScan();
  const idx = services.workspace.getIndex();
  stream.markdown([
    `✅ Re-indexed.`,
    ``,
    `- Scripts: **${idx.scripts.size}**`,
    `- Scenes: **${idx.scenes.size}**`,
    `- Autoloads: **${idx.autoloads.length}**`,
    `- Project Godot version: \`${idx.projectGodotVersion ?? "unknown"}\``,
  ].join("\n"));
}

// ── /template: insert a starter ──────────────────────────────────────────────

async function handleTemplate(request: vscode.ChatRequest, stream: vscode.ChatResponseStream): Promise<void> {
  const arg = request.prompt.trim();
  const t = arg ? findTemplate(arg) : null;
  if (!t) {
    stream.markdown(`Available Godot 4.x templates:\n`);
    for (const tpl of TEMPLATES) {
      stream.markdown(`- \`/template ${tpl.id}\` — ${tpl.title}: *${tpl.description}*\n`);
    }
    return;
  }
  stream.markdown(`### ${t.title}\n${t.description}\n\n\`\`\`gdscript\n${t.body}\n\`\`\``);
  stream.button({
    command: "godotContext.generateScript",
    title: `Save "${t.title}" to disk`,
    arguments: [t.id],
  });
}

// ── /docs: pure documentation lookup ────────────────────────────────────────

async function handleDocs(
  request: vscode.ChatRequest,
  services: Services,
  stream: vscode.ChatResponseStream,
  maxTokens: number,
): Promise<void> {
  const q = services.retriever.buildQuery(request.prompt);
  const result = await services.retriever.retrieve(q);
  // Force only-API mode: strip script/scene hits
  result.scriptHits = [];
  result.sceneHits = [];
  result.autoloadHits = [];
  const block = await services.builder.build(result, request.prompt, maxTokens);
  stream.markdown(block.markdown);
  for (const klass of result.apiHits.map(h => h.item)) {
    const url = services.api.toGodotDocsUrl(klass.name);
    stream.markdown(`\n\n[📖 Open ${klass.name} docs](${url})`);
  }
}

// ── /explain: docs + project usage ──────────────────────────────────────────

async function handleExplain(
  request: vscode.ChatRequest,
  services: Services,
  stream: vscode.ChatResponseStream,
  maxTokens: number,
): Promise<void> {
  const q = services.retriever.buildQuery(request.prompt);
  q.intent = "explain";
  const result = await services.retriever.retrieve(q);
  const block  = await services.builder.build(result, request.prompt, maxTokens);
  stream.markdown(`### Explaining: \`${request.prompt}\`\n\n`);
  stream.markdown(block.markdown);
  stream.markdown(
    `\n\n*Ask follow-ups like: "Using the @godot context, refactor my code to use this idiomatic Godot 4 pattern."*`,
  );
}
