/**
 * Offline tool. Run with: pnpm build:index -- <path/to/godot/doc/classes>
 *
 * Godot ships its class reference as one XML file per class, e.g.:
 *   doc/classes/CharacterBody2D.xml
 *
 * We parse those and emit resources/godot-api-4.x.json containing only what
 * the extension needs at runtime: name, inherits, brief, methods, signals,
 * properties. Long-form descriptions are trimmed to ~400 chars to keep the
 * shipped index small (~2-4 MB).
 *
 * Not run at extension runtime — output is committed to the repo.
 */

import * as fs from "node:fs/promises";
import * as path from "node:path";

// Minimal XML extraction. We avoid heavyweight parsers — Godot's XML schema
// is stable and shallow. This is intentionally regex-based: simpler to audit
// and faster to run on ~1500 files than spinning up sax/fast-xml-parser.

interface OutClass {
  name: string;
  inherits: string | null;
  brief: string;
  description: string;
  since: string;
  deprecated?: boolean;
  methods: Array<{ name: string; returnType: string; args: Array<{ name: string; type: string; default?: string }>; description: string; qualifiers?: string }>;
  signals: Array<{ name: string; args: Array<{ name: string; type: string }>; description: string }>;
  properties: Array<{ name: string; type: string; default: string; description: string }>;
}

const MAX_DESC = 400;
const trim = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, MAX_DESC);

function attr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`${name}="([^"]*)"`));
  return m ? m[1]! : null;
}

function* matchAll(xml: string, re: RegExp): IterableIterator<RegExpExecArray> {
  let m: RegExpExecArray | null;
  while ((m = re.exec(xml))) yield m;
}

async function parseClassFile(file: string): Promise<OutClass | null> {
  const xml = await fs.readFile(file, "utf8");
  const classTag = xml.match(/<class\b[^>]*>/);
  if (!classTag) return null;

  const name = attr(classTag[0], "name");
  if (!name) return null;

  const out: OutClass = {
    name,
    inherits: attr(classTag[0], "inherits"),
    brief: trim(xml.match(/<brief_description>([\s\S]*?)<\/brief_description>/)?.[1] ?? ""),
    description: trim(xml.match(/<description>([\s\S]*?)<\/description>/)?.[1] ?? ""),
    since: attr(classTag[0], "version") ?? "4.0",
    methods: [],
    signals: [],
    properties: [],
  };
  if (/deprecated="[^"]*"/.test(classTag[0])) out.deprecated = true;

  for (const m of matchAll(xml, /<method\b[^>]*>([\s\S]*?)<\/method>/g)) {
    const tag = m[0].match(/<method\b[^>]*>/)![0];
    const mname = attr(tag, "name"); if (!mname) continue;
    const ret = m[1]!.match(/<return\b[^/]*type="([^"]+)"/)?.[1] ?? "void";
    const args: OutClass["methods"][0]["args"] = [];
    for (const a of matchAll(m[1]!, /<param\b[^/]*\/>/g)) {
      const an = attr(a[0], "name"); const at = attr(a[0], "type");
      if (an && at) {
        const def = attr(a[0], "default");
        args.push(def != null ? { name: an, type: at, default: def } : { name: an, type: at });
      }
    }
    const desc = trim(m[1]!.match(/<description>([\s\S]*?)<\/description>/)?.[1] ?? "");
    const entry: OutClass["methods"][0] = { name: mname, returnType: ret, args, description: desc };
    const q = attr(tag, "qualifiers"); if (q) entry.qualifiers = q;
    out.methods.push(entry);
  }

  for (const s of matchAll(xml, /<signal\b[^>]*>([\s\S]*?)<\/signal>/g)) {
    const tag = s[0].match(/<signal\b[^>]*>/)![0];
    const sname = attr(tag, "name"); if (!sname) continue;
    const args: OutClass["signals"][0]["args"] = [];
    for (const a of matchAll(s[1]!, /<param\b[^/]*\/>/g)) {
      const an = attr(a[0], "name"); const at = attr(a[0], "type");
      if (an && at) args.push({ name: an, type: at });
    }
    out.signals.push({
      name: sname, args,
      description: trim(s[1]!.match(/<description>([\s\S]*?)<\/description>/)?.[1] ?? ""),
    });
  }

  for (const p of matchAll(xml, /<member\b[^/]*\/>/g)) {
    const pname = attr(p[0], "name"); const ptype = attr(p[0], "type");
    if (!pname || !ptype) continue;
    out.properties.push({
      name: pname, type: ptype,
      default: attr(p[0], "default") ?? "",
      description: "",
    });
  }

  return out;
}

async function main(): Promise<void> {
  const docDir = process.argv[2];
  if (!docDir) {
    console.error("Usage: build-api-index <path/to/godot/doc/classes>");
    process.exit(1);
  }
  const files = (await fs.readdir(docDir)).filter(f => f.endsWith(".xml"));
  const classes: OutClass[] = [];
  for (const f of files) {
    try {
      const c = await parseClassFile(path.join(docDir, f));
      if (c) classes.push(c);
    } catch (e) {
      console.warn(`skip ${f}: ${(e as Error).message}`);
    }
  }
  const out = path.join("resources", "godot-api-4.x.json");
  await fs.mkdir("resources", { recursive: true });
  await fs.writeFile(out, JSON.stringify({ classes }, null, 0));
  console.log(`Wrote ${classes.length} classes → ${out}`);
}

main().catch(e => { console.error(e); process.exit(1); });
