/**
 * Curated Godot 4.x snippets. Each one is hand-verified against the engine
 * docs. These are inserted when the user asks for a "template" or via the
 * /template slash command. They double as gold-standard examples that show
 * Copilot the modern idioms.
 */

export interface Template {
  id: string;
  title: string;
  description: string;
  language: "gdscript";
  body: string;
}

export const TEMPLATES: readonly Template[] = [
  {
    id: "character_body_2d",
    title: "CharacterBody2D with gravity & jump",
    description: "Idiomatic Godot 4.3+ player controller using move_and_slide and velocity property.",
    language: "gdscript",
    body: `extends CharacterBody2D

@export var speed:     float = 200.0
@export var jump_velocity: float = -400.0

func _physics_process(delta: float) -> void:
	# Apply gravity from project settings.
	if not is_on_floor():
		velocity += get_gravity() * delta

	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = jump_velocity

	var direction := Input.get_axis("ui_left", "ui_right")
	if direction:
		velocity.x = direction * speed
	else:
		velocity.x = move_toward(velocity.x, 0.0, speed)

	move_and_slide()
`,
  },
  {
    id: "state_machine",
    title: "Simple state machine (Node-based)",
    description: "Composition-friendly state machine pattern using child State nodes.",
    language: "gdscript",
    body: `class_name StateMachine
extends Node

@export var initial_state: State

var current_state: State

func _ready() -> void:
	for child in get_children():
		if child is State:
			child.transitioned.connect(_on_state_transition)
	if initial_state:
		initial_state.enter()
		current_state = initial_state

func _physics_process(delta: float) -> void:
	if current_state:
		current_state.physics_update(delta)

func _on_state_transition(new_state_name: StringName) -> void:
	var new_state := get_node_or_null(NodePath(new_state_name)) as State
	if new_state == null:
		return
	if current_state:
		current_state.exit()
	new_state.enter()
	current_state = new_state


class_name State
extends Node

signal transitioned(new_state_name: StringName)

func enter() -> void: pass
func exit()  -> void: pass
func physics_update(_delta: float) -> void: pass
`,
  },
  {
    id: "autoload_event_bus",
    title: "EventBus autoload",
    description: "Project-wide signal hub. Register as an autoload named EventBus.",
    language: "gdscript",
    body: `extends Node
## Project-wide event bus. Add as autoload named EventBus.

signal player_died
signal score_changed(new_score: int)
signal level_loaded(level_name: StringName)
`,
  },
  {
    id: "area2d_pickup",
    title: "Area2D pickup with body_entered",
    description: "Standard pickup pattern — signal-driven, no _physics_process polling.",
    language: "gdscript",
    body: `extends Area2D

@export var value: int = 1

func _ready() -> void:
	body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node2D) -> void:
	if body.is_in_group("player"):
		EventBus.score_changed.emit(value)
		queue_free()
`,
  },
];

export function findTemplate(id: string): Template | undefined {
  return TEMPLATES.find(t => t.id === id);
}
