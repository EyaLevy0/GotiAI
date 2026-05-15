import type { Autoload } from "../../types/index.js";

/**
 * project.godot is INI-like with sections. We only need:
 *   [application] config/features=... → contains the engine version tag
 *   [autoload] Foo="*res://path/foo.gd"
 *
 * The leading "*" on autoload values means "singleton" (instanced at startup).
 * Knowing autoloads is critical: when a Godot project has e.g. an autoload
 * named `EventBus`, retrieved snippets should reference it by name, not
 * reinvent it.
 */
export interface ProjectInfo {
  autoloads: Autoload[];
  godotVersion: string | null;
}

export class ProjectGodotParser {
  parse(source: string): ProjectInfo {
    const lines = source.split("\n");
    const autoloads: Autoload[] = [];
    let godotVersion: string | null = null;
    let section: string | null = null;

    for (const raw of lines) {
      const line = raw.trim();
      if (!line || line.startsWith(";")) continue;

      const sec = line.match(/^\[([^\]]+)\]$/);
      if (sec) { section = sec[1]!; continue; }

      if (section === "application") {
        const m = line.match(/^config\/features\s*=\s*PackedStringArray\(([^)]*)\)/);
        if (m) {
          const features = m[1]!.split(",").map(s => s.trim().replace(/^"|"$/g, ""));
          const v = features.find(f => /^\d+\.\d+/.test(f));
          if (v) godotVersion = v;
        }
      }

      if (section === "autoload") {
        const m = line.match(/^([A-Za-z_][\w]*)\s*=\s*"([^"]+)"/);
        if (m) {
          const value = m[2]!;
          const singleton = value.startsWith("*");
          autoloads.push({
            name: m[1]!,
            path: singleton ? value.slice(1) : value,
            singleton,
          });
        }
      }
    }

    return { autoloads, godotVersion };
  }
}
