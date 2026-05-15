"""Local entry point. Loads two frontend-like JSON files and runs the pipeline.

Usage:
  python main.py \
      --mechanics ./samples/mechanics.json \
      --art ./samples/art.json \
      --out ./generated_game
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from frontend_adapter import to_contract
from pipeline import Pipeline


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mechanics", required=True, type=Path, help="Path to mechanics JSON"
    )
    ap.add_argument("--art", required=True, type=Path, help="Path to art JSON")
    ap.add_argument("--out", required=True, type=Path, help="Output Godot project dir")
    args = ap.parse_args()

    mechanics_obj = _load_json(args.mechanics)
    art_obj = _load_json(args.art)

    contract = to_contract(
        mechanics_obj=mechanics_obj,
        art_obj=art_obj,
        project_directory_path=args.out,
    )

    print(f"[main] Project dir: {contract.project_directory_path}")
    pipeline = Pipeline()
    result = pipeline.run(contract)

    print(f"[main] Planned {len(result.plan.files)} files:")
    for f in result.plan.files:
        print(f"  - {f.kind.value:14s}  {f.path}")
    print(f"[main] Wrote {len(result.written_paths)} files to disk.")


if __name__ == "__main__":
    main()
