import * as vscode from "vscode";
import type {
  RetrievalQuery, RetrievalResult,
} from "../types/index.js";
import { Ranker } from "./ranker.js";
import type { GodotApiIndex } from "../indexing/godotApi/apiIndex.js";
import type { WorkspaceIndexer } from "../indexing/workspace/workspaceIndexer.js";

/**
 * The retrieval pipeline. Three jobs:
 *   1. Turn free-text prompt into a normalized RetrievalQuery (terms etc).
 *   2. Ask the Ranker to score API / scripts / scenes.
 *   3. Return a single RetrievalResult that the ContextBuilder formats.
 *
 * Intent-light: we don't try to "understand" the prompt beyond term extraction.
 * Copilot itself is the reasoner — we are a librarian, not an analyst.
 */
export class Retriever {
  private ranker: Ranker;

  constructor(
    api: GodotApiIndex,
    private readonly workspace: WorkspaceIndexer,
  ) {
    this.ranker = new Ranker(api);
  }

  buildQuery(text: string): RetrievalQuery {
    const terms = extractTerms(text);
    const activeUri = vscode.window.activeTextEditor?.document.uri.toString();
    const q: RetrievalQuery = { text, terms, intent: detectIntent(text) };
    if (activeUri) q.activeUri = activeUri;
    return q;
  }

  async retrieve(q: RetrievalQuery): Promise<RetrievalResult> {
    const idx = this.workspace.getIndex();
    const apiHits    = this.ranker.rankApi(q);
    const scriptHits = this.ranker.rankScripts(q, idx);
    const sceneHits  = this.ranker.rankScenes(q, idx);

    // Autoloads aren't ranked — if the user is doing anything project-wide,
    // every autoload is potentially relevant context. Cap at first 8.
    const autoloadHits = idx.autoloads.slice(0, 8);

    return {
      apiHits, scriptHits, sceneHits, autoloadHits,
      estimatedTokens: 0, // filled in by builder
    };
  }
}

/**
 * Pull plausibly meaningful tokens from the prompt. We:
 *   - lowercase
 *   - split on non-identifier
 *   - drop English stopwords
 *   - drop tokens shorter than 3 chars (except known short Godot terms)
 */
function extractTerms(text: string): string[] {
  const raw = text
    .toLowerCase()
    .split(/[^a-z0-9_]+/)
    .filter(Boolean);
  const out: string[] = [];
  const seen = new Set<string>();
  for (const t of raw) {
    if (STOPWORDS.has(t)) continue;
    if (t.length < 3 && !SHORT_OK.has(t)) continue;
    if (seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

function detectIntent(text: string): NonNullable<RetrievalQuery["intent"]> {
  const t = text.toLowerCase();
  if (/\b(what is|how does|explain)\b/.test(t)) return "explain";
  if (/\b(boilerplate|template|scaffold|starter)\b/.test(t)) return "template";
  if (/\b(docs?|reference|api)\b/.test(t)) return "lookup";
  return "implementation";
}

const STOPWORDS = new Set([
  "the","a","an","is","are","was","were","be","been","being","of","in","on","at","to","for","with","by","from",
  "and","or","but","not","no","yes","if","then","else","when","while","do","does","did","make","create",
  "want","need","please","help","me","my","i","you","your","we","our","this","that","these","those",
  "it","its","as","into","up","down","over","under","about","using","use","new","old",
]);
const SHORT_OK = new Set(["2d","3d","ai","ui","ux","fp","ws","fs","rb","sb"]);
