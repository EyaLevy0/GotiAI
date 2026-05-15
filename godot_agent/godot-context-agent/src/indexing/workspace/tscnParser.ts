import { createHash } from "node:crypto";
import type { TscnFile, TscnNode } from "../../types/index.js";

/**
 * .tscn is a flat sectioned format:
 *   [node name="Player" type="CharacterBody2D" parent="."]
 *   script = ExtResource("1_xyz")
 *
 * We only need: the node list (name+type+parent), and any script resources
 * referenced. Scene retrieval relies on type matching — "user asked about
 * enemy AI" + this scene contains a CharacterBody2D named "Enemy" = relevant.
 */
export class TscnParser {
  parse(uri: string, relPath: string, source: string): TscnFile {
    const lines = source.split("\n");
    const nodes: TscnNode[] = [];
    const extResources = new Map<string, string>(); // id → path
    const scripts: string[] = [];
    let rootType: string | null = null;
    let current: TscnNode | null = null;

    for (const line of lines) {
      let m: RegExpMatchArray | null;

      if ((m = line.match(/^\[ext_resource\b([^\]]*)\]/))) {
        const attrs = m[1]!;
        const path = attrs.match(/path="([^"]+)"/)?.[1];
        const id   = attrs.match(/id="([^"]+)"/)?.[1] ?? attrs.match(/id=(\d+)/)?.[1];
        const type = attrs.match(/type="([^"]+)"/)?.[1];
        if (path && id) {
          extResources.set(id, path);
          if (type === "Script") scripts.push(path);
        }
        continue;
      }

      if ((m = line.match(/^\[node\b([^\]]*)\]/))) {
        if (current) nodes.push(current);
        const attrs = m[1]!;
        const name   = attrs.match(/name="([^"]+)"/)?.[1] ?? "?";
        const type   = attrs.match(/type="([^"]+)"/)?.[1] ?? "Node";
        const parent = attrs.match(/parent="([^"]+)"/)?.[1] ?? null;
        if (parent === null) rootType = type;
        current = { name, type, parent };
        continue;
      }

      if (current && (m = line.match(/^script\s*=\s*ExtResource\(\s*"?([^")]+)"?\s*\)/))) {
        const path = extResources.get(m[1]!);
        if (path) current.script = path;
      }
    }
    if (current) nodes.push(current);

    return {
      uri, relPath,
      rootType,
      nodes,
      scripts,
      hash: createHash("sha256").update(source).digest("hex").slice(0, 16),
    };
  }
}
