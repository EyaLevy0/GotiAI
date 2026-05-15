import * as path from "node:path";
import type {
  GdScriptFile, TscnFile, GodotApiClass,
  RankedHit, RetrievalQuery, WorkspaceIndex,
} from "../types/index.js";
import type { GodotApiIndex } from "../indexing/godotApi/apiIndex.js";

/**
 * Hybrid ranker — see the README architecture section for the math. In short:
 *  score(c) = Σ_t lex(c, t) + α·struct(c, T) + β·prox(c)
 *
 * α and β are deliberately small. The dominant signal is lexical match on
 * symbol names, because GDScript is typed and developers name things
 * meaningfully — "enemy.gd" really is about enemies.
 */
export class Ranker {
  constructor(private readonly api: GodotApiIndex) {}

  rankApi(q: RetrievalQuery, limit = 6): RankedHit<GodotApiClass>[] {
    const reasons: Map<GodotApiClass, string[]> = new Map();
    const scores: Map<GodotApiClass, number> = new Map();

    for (const term of q.terms) {
      const exact = this.api.getClass(term);
      if (exact) {
        scores.set(exact, (scores.get(exact) ?? 0) + 100);
        push(reasons, exact, `exact class match: ${term}`);
      }
      for (const klass of this.api.search(term, 5)) {
        scores.set(klass, (scores.get(klass) ?? 0) + 30);
        push(reasons, klass, `name/member match: ${term}`);
      }
      for (const hit of this.api.findMethod(term)) {
        scores.set(hit.klass, (scores.get(hit.klass) ?? 0) + 50);
        push(reasons, hit.klass, `method: ${hit.klass.name}.${hit.method.name}`);
      }
    }

    return [...scores.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([item, score]) => ({ item, score, reasons: reasons.get(item) ?? [] }));
  }

  rankScripts(q: RetrievalQuery, idx: WorkspaceIndex, limit = 6): RankedHit<GdScriptFile>[] {
    const N = idx.scripts.size;
    const df = this.documentFrequency(q.terms, idx);
    const activeDir = q.activeUri ? path.dirname(q.activeUri) : null;
    const results: RankedHit<GdScriptFile>[] = [];

    for (const file of idx.scripts.values()) {
      let score = 0;
      const reasons: string[] = [];

      const names = new Set<string>();
      if (file.className) names.add(file.className.toLowerCase());
      if (file.extends)   names.add(file.extends.toLowerCase());
      for (const s of file.symbols) names.add(s.name.toLowerCase());
      names.add(path.basename(file.relPath, ".gd").toLowerCase());

      for (const term of q.terms) {
        if (names.has(term)) {
          const idf = Math.log(1 + N / (1 + (df.get(term) ?? 0)));
          score += idf * 10;
          reasons.push(`matches "${term}"`);
        }
      }
      if (score === 0) continue;

      // Structural boosts
      if (file.extends && q.terms.includes(file.extends.toLowerCase())) {
        score += 15;
        reasons.push(`extends ${file.extends}`);
      }
      const isAutoload = idx.autoloads.some(a => a.path.endsWith(file.relPath) || a.path.includes(file.relPath));
      if (isAutoload) {
        score += 8;
        reasons.push("autoload singleton");
      }

      // Proximity
      if (activeDir && file.uri.includes(activeDir)) {
        score += 5;
        reasons.push("same directory as active editor");
      }

      results.push({ item: file, score, reasons });
    }

    return results.sort((a, b) => b.score - a.score).slice(0, limit);
  }

  rankScenes(q: RetrievalQuery, idx: WorkspaceIndex, limit = 3): RankedHit<TscnFile>[] {
    const results: RankedHit<TscnFile>[] = [];
    for (const scene of idx.scenes.values()) {
      let score = 0;
      const reasons: string[] = [];
      const types = new Set(scene.nodes.map(n => n.type.toLowerCase()));
      const names = new Set(scene.nodes.map(n => n.name.toLowerCase()));

      for (const term of q.terms) {
        if (types.has(term)) { score += 12; reasons.push(`scene uses ${term}`); }
        if (names.has(term)) { score += 8;  reasons.push(`scene has node "${term}"`); }
      }
      if (score === 0) continue;
      results.push({ item: scene, score, reasons });
    }
    return results.sort((a, b) => b.score - a.score).slice(0, limit);
  }

  private documentFrequency(terms: string[], idx: WorkspaceIndex): Map<string, number> {
    const df = new Map<string, number>();
    for (const t of terms) df.set(t, 0);
    for (const f of idx.scripts.values()) {
      const present = new Set<string>();
      if (f.className) present.add(f.className.toLowerCase());
      if (f.extends)   present.add(f.extends.toLowerCase());
      for (const s of f.symbols) present.add(s.name.toLowerCase());
      for (const t of terms) if (present.has(t)) df.set(t, (df.get(t) ?? 0) + 1);
    }
    return df;
  }
}

function push<K>(m: Map<K, string[]>, k: K, r: string): void {
  let arr = m.get(k);
  if (!arr) { arr = []; m.set(k, arr); }
  arr.push(r);
}
