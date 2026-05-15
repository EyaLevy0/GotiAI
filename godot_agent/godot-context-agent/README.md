# Godot Context Agent

A VS Code extension that **enhances GitHub Copilot for Godot 4.x development** by retrieving high-signal documentation and project context, then handing it to Copilot Chat as authoritative reference material.

This is not another LLM. It does no inference. Copilot remains the code generator — this extension just makes sure Copilot has the *right* Godot 4 context in its window before generating, so it stops emitting `KinematicBody2D` and `yield(...)` in 2025.

---

## How it works

```
┌──────────────────────┐
│  User asks @godot    │
│  in Copilot Chat     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐    ┌────────────────────────┐
│   Retriever          │◄───┤  Workspace Indexer     │
│   (term extraction,  │    │  (.gd, .tscn,          │
│    intent detection) │    │   project.godot)       │
└──────────┬───────────┘    └────────────────────────┘
           │
           ▼
┌──────────────────────┐    ┌────────────────────────┐
│   Ranker             │◄───┤  Godot 4.x API Index   │
│   (hybrid scoring)   │    │  (prebuilt JSON)       │
└──────────┬───────────┘    └────────────────────────┘
           │
           ▼
┌──────────────────────┐
│   Compressor         │  drops irrelevant function bodies,
│                      │  strips comments, enforces token budget
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   ContextBuilder     │  → Markdown block + vscode.Uri references
└──────────┬───────────┘     streamed into Copilot Chat
           │
           ▼
       Copilot writes correct Godot 4 code.
```

### Why retrieval, not fine-tuning

Copilot's training data is dominated by Godot 3 because that's what existed when most of the open-source Godot code was written. Retraining Copilot is not on the table. What *is* on the table: handing Copilot a markdown block that says, plainly and at the top:

> **Target engine:** Godot **4.x**. Use **GDScript 2** syntax exclusively.
> - Use `CharacterBody2D`/`CharacterBody3D` (not `KinematicBody*`).
> - Use `signal.connect(callable)` (not `connect("signal", target, "method")`).

…followed by exact method signatures pulled from Godot's own XML class docs. That alone cuts Godot-3-flavoured hallucinations dramatically.

### Ranking math

For a query with terms $T$ and a candidate file $c$:

$$\text{score}(c) = \sum_{t \in T} \mathbf{1}[t \in \text{symbols}(c)] \cdot \log\!\left(1 + \frac{N}{1 + \text{df}(t)}\right) + \alpha \cdot \text{struct}(c, T) + \beta \cdot \text{prox}(c)$$

- $N$ = total indexed files, $\text{df}(t)$ = document frequency of term $t$
- $\text{struct}$ rewards exact `class_name`/`extends` matches and autoload status
- $\text{prox}$ rewards files in the same directory as the active editor
- $\alpha, \beta$ small (≈ 1.5, 0.5) so lexical signal dominates

This is BM25's IDF term plus two handcrafted boosts. Embeddings would be a 5× cost increase for marginal gain on a typed identifier-rich language.

---

## Usage

### Chat participant

In Copilot Chat, type `@godot` followed by a request:

```
@godot create a 2D enemy that patrols and chases the player

@godot how do I detect when an Area2D is entered

@godot /docs CharacterBody2D

@godot /template state_machine

@godot /explain move_and_slide
```

### Commands

| Command                                    | Effect                                            |
|--------------------------------------------|---------------------------------------------------|
| `Godot Context: Re-index Workspace`        | Force a full scan                                  |
| `Godot Context: Search API`                | Quick-pick over the Godot 4.x class index         |
| `Godot Context: Generate Script…`          | Insert a vetted Godot 4 starter (state machine etc.) |
| `Godot Context: Open Sidebar`              | Show the index dashboard                          |

### Sidebar

Live counts (scripts / scenes / autoloads), detected project Godot version, and a **preview pane** where you can type any query and see exactly what would be sent to Copilot — including token usage against the configured budget.

---

## Example retrieval trace

User prompt: `@godot create a 2D enemy that follows the player using navigation`

Terms extracted: `enemy`, `2d`, `follows`, `player`, `navigation`

The agent emits to Copilot:

````markdown
## Engine context
**Target engine:** Godot **4.x**. Use **GDScript 2** syntax exclusively.
- Use `CharacterBody2D`/`CharacterBody3D` (not `KinematicBody*`).
- Use `@export var foo: Type` (not `export var foo`).
- Use `signal.connect(callable)` (not `connect("signal", target, "method")`).
- Use `PackedStringArray` (not `PoolStringArray`).
- Use `await` on signals (not yield).

## Available autoloads in this project
- `EventBus` (singleton) → `res://systems/event_bus.gd`
- `GameState` (singleton) → `res://systems/game_state.gd`

### Godot API · `CharacterBody2D` extends `PhysicsBody2D`
> A 2D physics body specialized for characters moved by script.

**Key methods (Godot 4.0+):**
- `move_and_slide() -> bool` — Moves the body using velocity. Auto-slides
  along walls and floors. Use velocity (Vector2 property) to control motion;
  do not pass a vector argument as in Godot 3.
- `is_on_floor() -> bool` — Returns true if the body collided with the floor
  on the last call to move_and_slide.
**Properties:**
- `velocity: Vector2 = Vector2(0, 0)`
- `floor_snap_length: float = 1.0`

## Project code (most relevant)
### scripts/entities/enemy_base.gd
*Reasons: matches "enemy"; extends CharacterBody2D; same directory as active editor*

```gdscript
class_name EnemyBase
extends CharacterBody2D

signal died

@export var speed: float = 80.0
@export var navigation: NavigationAgent2D

func _physics_process(delta: float) -> void:
	# ...

func take_damage(amount: int) -> void:
	# ...
```

## Related scenes
### scenes/enemies/slime.tscn  *(root: CharacterBody2D)*
```
Slime : CharacterBody2D  ← res://scripts/entities/enemy_base.gd
  CollisionShape2D : CollisionShape2D
  AnimatedSprite2D : AnimatedSprite2D
  NavigationAgent2D : NavigationAgent2D
```

---
*This context was assembled by Godot Context Agent. Treat the engine version banner as authoritative…*
````

Token usage: ~890 / 2000 budget. Copilot now has the project's actual `EnemyBase` class to extend, knows `NavigationAgent2D` is the in-use pattern, knows about the `EventBus` autoload it could emit through, and is anchored to Godot 4 syntax.

---

## Configuration

| Setting                              | Default | Description                                    |
|--------------------------------------|---------|------------------------------------------------|
| `godotContext.godotVersion`          | `4.x`   | Target Godot version                           |
| `godotContext.maxContextTokens`      | `2000`  | Hard budget for the context block              |
| `godotContext.workspaceFileLimit`    | `200`   | Cap on files indexed per pass                  |
| `godotContext.warnOnGodot3Api`       | `true`  | Flag Godot 3 idioms appearing in your scripts  |

---

## Building

```bash
npm install
npm run build      # compile TypeScript
npm run build:index -- /path/to/godot/doc/classes   # refresh API index from official XML
npm run package    # produce a .vsix
```

`resources/godot-api-4.x.json` is committed for convenience — re-run `build:index` against a fresh Godot checkout to bump it.

---

## What this extension does **not** do

- Generate code via its own LLM. *(That's Copilot's job.)*
- Replace your linter or LSP. *(godot-tools handles diagnostics.)*
- Run Godot. *(It's a static-analysis context tool.)*
- Send your code anywhere. *(All processing is local; the API index ships in the extension.)*

## License

MIT.
