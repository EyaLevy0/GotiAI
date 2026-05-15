import * as fs from "node:fs/promises";
import * as path from "node:path";
import type { GodotApiClass, GodotApiMethod } from "../../types/index.js";
import type { Logger } from "../../util/logger.js";

/**
 * The API index is loaded once at activation. It is shipped as a static JSON
 * resource produced by scripts/build-api-index.ts from Godot's official XML
 * class docs. Doing the parsing offline (a) keeps the runtime dependency-free
 * and (b) lets us ship a deterministic, version-pinned index.
 */
export class GodotApiIndex {
  private classes: Map<string, GodotApiClass> = new Map();
  /** Reverse index: method/signal/property name → class names that own it. */
  private memberIndex: Map<string, Set<string>> = new Map();
  /** Lowercased class name → canonical name, for case-insensitive matching. */
  private nameLookup: Map<string, string> = new Map();
  private loaded = false;

  constructor(private readonly logger: Logger) {}

  async load(extensionPath: string): Promise<void> {
    const file = path.join(extensionPath, "resources", "godot-api-4.x.json");
    try {
      const raw = await fs.readFile(file, "utf8");
      const data = JSON.parse(raw) as { classes: GodotApiClass[] };
      for (const c of data.classes) {
        this.classes.set(c.name, c);
        this.nameLookup.set(c.name.toLowerCase(), c.name);
        for (const m of c.methods)    this.addMember(m.name, c.name);
        for (const s of c.signals)    this.addMember(s.name, c.name);
        for (const p of c.properties) this.addMember(p.name, c.name);
      }
      this.loaded = true;
      this.logger.info(`API index loaded: ${this.classes.size} classes`);
    } catch (err) {
      this.logger.error("Failed to load Godot API index", err);
      throw err;
    }
  }

  private addMember(member: string, klass: string): void {
    let set = this.memberIndex.get(member);
    if (!set) { set = new Set(); this.memberIndex.set(member, set); }
    set.add(klass);
  }

  isReady(): boolean { return this.loaded; }

  /** Case-insensitive exact lookup. */
  getClass(name: string): GodotApiClass | undefined {
    const canonical = this.nameLookup.get(name.toLowerCase());
    return canonical ? this.classes.get(canonical) : undefined;
  }

  /**
   * Search by free-text query. Returns classes scored by:
   *  - exact name match (highest)
   *  - prefix match
   *  - member-name match (e.g. "move_and_slide" → CharacterBody2D)
   *  - description token overlap (lowest)
   */
  search(query: string, limit = 8): GodotApiClass[] {
    const terms = tokenize(query);
    if (terms.length === 0) return [];
    const scores = new Map<string, number>();

    for (const term of terms) {
      // exact class
      const exact = this.nameLookup.get(term);
      if (exact) bump(scores, exact, 100);
      // prefix class
      for (const [lc, canonical] of this.nameLookup) {
        if (lc.startsWith(term) && lc !== term) bump(scores, canonical, 25);
      }
      // members
      const owners = this.memberIndex.get(term);
      if (owners) for (const o of owners) bump(scores, o, 40);
      // description (cheap contains check)
      for (const c of this.classes.values()) {
        if (c.brief.toLowerCase().includes(term)) bump(scores, c.name, 5);
      }
    }

    return [...scores.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([n]) => this.classes.get(n)!)
      .filter(Boolean);
  }

  /** Resolve "ClassName.method" or just "method" → method definitions. */
  findMethod(query: string): Array<{ klass: GodotApiClass; method: GodotApiMethod }> {
    const out: Array<{ klass: GodotApiClass; method: GodotApiMethod }> = [];
    if (query.includes(".")) {
      const [className, methodName] = query.split(".", 2) as [string, string];
      const klass = this.getClass(className);
      if (!klass) return out;
      for (const m of klass.methods) if (m.name === methodName) out.push({ klass, method: m });
      return out;
    }
    const owners = this.memberIndex.get(query);
    if (!owners) return out;
    for (const owner of owners) {
      const klass = this.classes.get(owner);
      if (!klass) continue;
      for (const m of klass.methods) if (m.name === query) out.push({ klass, method: m });
    }
    return out;
  }

  /** Detect Godot 3 → 4 renames. Used by the warnOnGodot3Api setting. */
  isGodot3Identifier(name: string): { replacement: string; note: string } | null {
    return GODOT_3_RENAMES[name] ?? null;
  }

  /** Bytes-cheap iterator for the sidebar's "all classes" view. */
  *iterClasses(): IterableIterator<GodotApiClass> {
    yield* this.classes.values();
  }

  toGodotDocsUrl(className: string, version: string = "stable"): string {
    return `https://docs.godotengine.org/en/${version}/classes/class_${className.toLowerCase()}.html`;
  }
}

function bump(m: Map<string, number>, k: string, by: number): void {
  m.set(k, (m.get(k) ?? 0) + by);
}

function tokenize(s: string): string[] {
  return s
    .toLowerCase()
    .split(/[^a-z0-9_]+/)
    .filter(t => t.length > 1);
}

// Hardcoded subset — full list lives in the JSON build script's `renames.json`.
// These are the renames most likely to bite Copilot output for Godot 4.
const GODOT_3_RENAMES: Record<string, { replacement: string; note: string }> = {
  KinematicBody2D:        { replacement: "CharacterBody2D",     note: "Renamed in Godot 4.0" },
  KinematicBody:          { replacement: "CharacterBody3D",     note: "Renamed in Godot 4.0" },
  RigidBody:              { replacement: "RigidBody3D",         note: "All 3D physics nodes gained the '3D' suffix in 4.0" },
  Spatial:                { replacement: "Node3D",              note: "Renamed in Godot 4.0" },
  Area:                   { replacement: "Area3D",              note: "All 3D nodes gained the '3D' suffix in 4.0" },
  StaticBody:             { replacement: "StaticBody3D",        note: "Renamed in Godot 4.0" },
  CollisionShape:         { replacement: "CollisionShape3D",    note: "Renamed in Godot 4.0" },
  YSort:                  { replacement: "Node2D.y_sort_enabled", note: "YSort node removed; use y_sort_enabled property on Node2D in 4.0" },
  ToolButton:             { replacement: "Button",              note: "Merged into Button in 4.0" },
  PoolStringArray:        { replacement: "PackedStringArray",   note: "All Pool*Array types renamed to Packed*Array in 4.0" },
  PoolIntArray:           { replacement: "PackedInt32Array",    note: "All Pool*Array types renamed to Packed*Array in 4.0" },
  PoolByteArray:          { replacement: "PackedByteArray",     note: "All Pool*Array types renamed to Packed*Array in 4.0" },
  move_and_slide_with_snap:{ replacement: "move_and_slide()",   note: "Snap is now configured via floor_snap_length on CharacterBody2D/3D" },
  is_on_floor:            { replacement: "is_on_floor",         note: "Still valid in 4.x, but is_on_floor_only() was renamed to is_on_floor() with stricter semantics" },
};
