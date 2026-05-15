# Changelog

## 0.1.0 — Initial release

- `@godot` Copilot Chat participant with `/docs`, `/scan`, `/template`, `/explain`
- Godot 4.x API index (prebuilt JSON, ~1500 classes when rebuilt from source)
- Workspace indexing for `.gd`, `.tscn`, and `project.godot` with incremental watcher
- Hybrid retrieval (lexical IDF + structural + proximity)
- Context compression with hard token budget
- Godot 3 → 4 migration warnings on retrieved code
- Sidebar with index stats, autoload list, API browser, and context preview
- Status-bar indicator
- Four vetted starter templates (CharacterBody2D, state machine, EventBus, Area2D pickup)
- Persistent on-disk cache (`.vscode/godot-context-cache.json`)
