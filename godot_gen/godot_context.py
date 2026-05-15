"""Static Godot 4 rules + deterministic scene templates.

Replaces live docs retrieval for MVP. Anything authoritative the LLM needs to
know about Godot 4 lives here.
"""

from __future__ import annotations

# ---------- Hard rules surfaced to the LLM ----------

GODOT4_RULES = r"""
GODOT 4 / GDSCRIPT 2.0 STRICT RULES (do not violate any of these):

Engine & language
- Target Godot 4.x. Never emit Godot 3.x syntax or APIs.
- GDScript 2.0 only. First non-comment line of a script is `extends <ClassName>`.
- Use `await` for async; never use `yield`.
- Use modern signal syntax: `signal foo(arg: int)` and `node.connected.connect(callable)`.
- Prefer typed variables and typed function signatures where reasonable:
  `var speed: float = 180.0`, `func _physics_process(delta: float) -> void:`
- Use `@onready var x := $Path` for node references.
- Use `@export` for inspector-exposed values.

Nodes & APIs
- Player root MUST be `CharacterBody2D`. Never `KinematicBody2D` (Godot 3).
- Movement uses `velocity` + `move_and_slide()` (no arguments in Godot 4).
- Gravity: `ProjectSettings.get_setting("physics/2d/default_gravity")` or a constant.
- Use `AnimatedSprite2D` + `SpriteFrames` for character animation.
- Use `CollisionShape2D` (with a `RectangleShape2D` / `CircleShape2D` / `CapsuleShape2D` resource).
- Use `Area2D` for trigger / hit / hurt boxes.
- Use `Camera2D` for camera. In Godot 4, `Camera2D.enabled = true` (no `current` setter on instance is needed; `make_current()` works too).
- Use `CanvasLayer` for HUD.
- Use `TileMap` + `TileSet` for tile environments.

Input
- Use `Input.is_action_pressed("move_left")` etc. Assume input actions exist
  (`move_left`, `move_right`, `jump`, `attack`); the generator registers them
  in project.godot.

Scenes & resources
- Use stable, predictable node names (e.g. `AnimatedSprite2D`, `CollisionShape2D`, `Camera2D`).
- Reference resources via `res://` paths.
- Never reference a file that has not been planned.
- Scripts attach to scenes only when the script path is a planned dependency.

Code quality
- One responsibility per script. Keep functions short.
- No print debugging in final files (use comments instead).
- Do not output markdown, code fences, or explanations — only raw file contents.
"""


# ---------- Canonical paths (mirror SpriteInjectionContract defaults) ----------

CANONICAL_PATHS = {
    "player_scene": "scenes/player/Player.tscn",
    "player_script": "scripts/player/player.gd",
    "player_sprite_frames": "assets/generated/player/player_sprite_frames.tres",
    "main_scene": "scenes/Main.tscn",
    "main_script": "scripts/main.gd",
    "enemy_script": "scripts/enemy/enemy.gd",
    "enemy_scene": "scenes/enemy/Enemy.tscn",
    "hud_scene": "scenes/ui/HUD.tscn",
    "hud_script": "scripts/ui/hud.gd",
    "project_godot": "project.godot",
}


# ---------- Deterministic templates ----------
# We render .tscn / project.godot / .tres ourselves to avoid letting the LLM
# invent malformed scene text. The LLM only writes .gd files.

PROJECT_GODOT_TEMPLATE = """; Engine configuration file.
; Generated. Safe to hand-edit afterward.

config_version=5

[application]

config/name="{project_name}"
run/main_scene="res://scenes/Main.tscn"
config/features=PackedStringArray("4.2", "GL Compatibility")
config/icon="res://icon.svg"

[input]

move_left={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":0,"echo":false,"script":null)
]
}}
move_right={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":68,"key_label":0,"unicode":0,"echo":false,"script":null)
]
}}
jump={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":0,"echo":false,"script":null)
]
}}
attack={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":74,"key_label":0,"unicode":0,"echo":false,"script":null)
]
}}

[rendering]

renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""


# Minimal, valid Godot 4 scene. Script attachment is optional.
PLAYER_SCENE_TEMPLATE = """[gd_scene load_steps={load_steps} format=3 uid="uid://b{uid_suffix}"]

{script_ext_resource}[sub_resource type="RectangleShape2D" id="RectangleShape2D_1"]
size = Vector2(32, 48)

[node name="Player" type="CharacterBody2D"]{script_attr}

[node name="CollisionShape2D" type="CollisionShape2D" parent="."]
shape = SubResource("RectangleShape2D_1")

[node name="AnimatedSprite2D" type="AnimatedSprite2D" parent="."]
"""

ENEMY_SCENE_TEMPLATE = """[gd_scene load_steps={load_steps} format=3 uid="uid://b{uid_suffix}"]

{script_ext_resource}[sub_resource type="RectangleShape2D" id="RectangleShape2D_1"]
size = Vector2(32, 32)

[node name="Enemy" type="CharacterBody2D"]{script_attr}

[node name="CollisionShape2D" type="CollisionShape2D" parent="."]
shape = SubResource("RectangleShape2D_1")

[node name="AnimatedSprite2D" type="AnimatedSprite2D" parent="."]
"""

MAIN_SCENE_TEMPLATE = """[gd_scene load_steps={load_steps} format=3 uid="uid://b{uid_suffix}"]

{script_ext_resource}{player_ext_resource}[node name="Main" type="Node2D"]{script_attr}

[node name="Camera2D" type="Camera2D" parent="."]
enabled = true

{player_node}"""

PLAYER_NODE_BLOCK = """[node name="Player" parent="." instance=ExtResource("player_scene")]
position = Vector2(0, 0)
"""

# Empty placeholder SpriteFrames resource. Sprite injection will populate it.
SPRITE_FRAMES_TEMPLATE = """[gd_resource type="SpriteFrames" format=3 uid="uid://b{uid_suffix}"]

[resource]
animations = [{{
"frames": [],
"loop": true,
"name": &"idle",
"speed": 5.0
}}]
"""


def render_project_godot(project_name: str) -> str:
    return PROJECT_GODOT_TEMPLATE.format(project_name=project_name)


def _uid(seed: str) -> str:
    # Stable, short, alphanumeric.
    import hashlib

    return hashlib.sha1(seed.encode()).hexdigest()[:12]


def render_player_scene(script_res_path: str | None) -> str:
    if script_res_path:
        script_ext_resource = f'[ext_resource type="Script" path="{script_res_path}" id="player_script"]\n\n'
        script_attr = '\nscript = ExtResource("player_script")'
        load_steps = 3
    else:
        script_ext_resource = ""
        script_attr = ""
        load_steps = 2
    return PLAYER_SCENE_TEMPLATE.format(
        load_steps=load_steps,
        uid_suffix=_uid("player_scene"),
        script_ext_resource=script_ext_resource,
        script_attr=script_attr,
    )


def render_enemy_scene(script_res_path: str | None) -> str:
    if script_res_path:
        script_ext_resource = f'[ext_resource type="Script" path="{script_res_path}" id="enemy_script"]\n\n'
        script_attr = '\nscript = ExtResource("enemy_script")'
        load_steps = 3
    else:
        script_ext_resource = ""
        script_attr = ""
        load_steps = 2
    return ENEMY_SCENE_TEMPLATE.format(
        load_steps=load_steps,
        uid_suffix=_uid("enemy_scene"),
        script_ext_resource=script_ext_resource,
        script_attr=script_attr,
    )


def render_main_scene(
    main_script_res_path: str | None,
    player_scene_res_path: str | None,
) -> str:
    parts = []
    load_steps = 1
    script_ext_resource = ""
    script_attr = ""
    player_ext_resource = ""
    player_node = ""

    if main_script_res_path:
        script_ext_resource = f'[ext_resource type="Script" path="{main_script_res_path}" id="main_script"]\n\n'
        script_attr = '\nscript = ExtResource("main_script")'
        load_steps += 1
    if player_scene_res_path:
        player_ext_resource = f'[ext_resource type="PackedScene" path="{player_scene_res_path}" id="player_scene"]\n\n'
        player_node = PLAYER_NODE_BLOCK
        load_steps += 1

    return MAIN_SCENE_TEMPLATE.format(
        load_steps=load_steps,
        uid_suffix=_uid("main_scene"),
        script_ext_resource=script_ext_resource,
        script_attr=script_attr,
        player_ext_resource=player_ext_resource,
        player_node=player_node,
    )


def render_sprite_frames_placeholder(seed: str) -> str:
    return SPRITE_FRAMES_TEMPLATE.format(uid_suffix=_uid("sf_" + seed))
