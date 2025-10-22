"""
Generate static label metadata (names + colors) for supported atlases.

This keeps the engine as the single source of truth for ROI labels while
producing JSON that the web app can consume for visualization (e.g., Niivue).

Usage:
    python -m functions.export_atlas_labels --output-dir ../app/public/atlases
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from utilities.volume_labels import hcpex_labels, ho_cortical

# Harvard-Oxford atlas (as distributed) encodes cortical labels 1-48.
# We keep subcortical entries out of the generated file until those volumes
# are included in visualization outputs.
HARVARD_LABELS = ho_cortical


@dataclass(frozen=True)
class Label:
    """Container for a single atlas label entry."""

    id: int
    name: str
    color: Tuple[int, int, int, int]

    def to_json(self) -> Dict[str, object]:
        r, g, b, a = self.color
        return {"id": self.id, "name": self.name, "color": [r, g, b, a]}


def generate_color(index: int, total: int) -> Tuple[int, int, int, int]:
    """
    Generate a visually distinct RGBA color using golden-ratio spacing in HSV space.

    Args:
        index: zero-based position
        total: total number of labels (used to balance saturation on very large atlases)
    """
    # Golden ratio conjugate spacing keeps hues evenly distributed.
    golden_ratio = 0.61803398875
    hue = (index * golden_ratio) % 1.0

    # Adjust saturation/value so that very large atlases (e.g., HCPex) do not wash out.
    saturation = 0.60 if total <= 100 else 0.72
    value = 0.92

    import colorsys

    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


def build_labels(label_map: Dict[int, str]) -> List[Label]:
    """
    Convert an atlas label dictionary into a list of Label entries with colors.

    A transparent background entry (ID 0) is prepended so Niivue treats zero voxels
    correctly when using the generated LUT.
    """
    sorted_items = sorted(label_map.items())
    labels: List[Label] = []

    if 0 in label_map:
        labels.append(Label(id=0, name=label_map[0], color=(0, 0, 0, 0)))
        sorted_items = [item for item in sorted_items if item[0] != 0]
    else:
        labels.append(Label(id=0, name="Background", color=(0, 0, 0, 0)))

    total = len(sorted_items)

    for idx, (label_id, label_name) in enumerate(sorted_items):
        color = generate_color(idx, total)
        labels.append(Label(id=label_id, name=label_name, color=color))
    return labels


def export_atlas(atlas: str, label_map: Dict[int, str], output_dir: str) -> str:
    """Write a JSON file for a specific atlas and return the path."""
    labels = build_labels(label_map)
    payload = {
        "atlas": atlas,
        "generated_by": "functions/export_atlas_labels.py",
        "labels": [label.to_json() for label in labels],
    }

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{atlas}.labels.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return output_path


def export_all(output_dir: str) -> List[str]:
    """Export supported atlases and return the list of generated file paths."""
    outputs = []
    outputs.append(export_atlas("harvard-oxford", HARVARD_LABELS, output_dir))
    outputs.append(export_atlas("hcpex", hcpex_labels, output_dir))
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export atlas labels (names + colors) to JSON for visualization clients."
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "artifacts", "atlas-labels"),
        help="Directory to write JSON files. Defaults to engine/artifacts/atlas-labels.",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    outputs = export_all(output_dir)

    print("Generated atlas label JSON:")
    for path in outputs:
        print(f" - {path}")


if __name__ == "__main__":
    main()
