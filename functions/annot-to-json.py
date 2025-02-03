import nibabel as nb
import json
import numpy as np


def convert_annot_to_json(annot_path: str, output_path: str):
    # Read the annotation file
    labels, ctab, names = nb.freesurfer.read_annot(annot_path)

    # Debug raw labels
    print("\nDEBUG - Labels Analysis:")
    unique_labels = np.unique(labels)
    print(f"First few raw labels: {labels[:10]}")
    print(f"Unique labels in data: {unique_labels}")
    print(f"Labels value counts:")
    unique, counts = np.unique(labels, return_counts=True)
    for u, c in zip(unique, counts):
        print(f"Label {u}: {c} vertices")

    # Debug: Print raw annotation file contents
    print("\nDEBUG - Raw .annot file contents:")
    print(f"Labels shape: {labels.shape}")
    print(f"Labels range: {labels.min()} to {labels.max()}")
    print(f"Number of unique raw labels: {len(np.unique(labels))}")
    print("\nColor table contents:")
    for i, (r, g, b, a, label) in enumerate(ctab):
        name = names[i].decode('utf-8') if isinstance(names[i], bytes) else names[i]
        print(f"Region {i}: Label={label}, Name={name}, Color=rgb({int(r)},{int(g)},{int(b)})")
    print("\n" + "=" * 50 + "\n")

    # Initialize structures
    vertex_labels = []
    regions = {}

    # Process color table and create regions
    for i, (r, g, b, a, label) in enumerate(ctab):
        name = names[i].decode('utf-8') if isinstance(names[i], bytes) else names[i]
        regions[i] = {
            "id": i,
            "name": name,
            "color": {"r": int(r), "g": int(g), "b": int(b), "a": 255}
        }

    # The labels array already contains the correct indices (0 to N-1)
    # We just need to copy them directly
    vertex_labels = [int(l) for l in labels]

    output = {
        "labels": vertex_labels,
        "regions": regions
    }

    # Print validation info
    print("\nValidation:")
    print(f"Number of vertices: {len(vertex_labels)}")
    print(f"Number of regions: {len(regions)}")
    print(f"Number of unique labels in vertices: {len(set(vertex_labels))}")

    print("\nFirst few vertices and their regions:")
    for i in range(min(5, len(vertex_labels))):
        label = vertex_labels[i]
        region = regions[label]
        print(f"Vertex {i} -> Label {label} ({region['name']})")
        print(f"  Color: rgb({region['color']['r']},{region['color']['g']},{region['color']['b']})")

    with open(output_path, 'w') as f:
        json.dump(output, f)

    print("\nFile saved successfully!")


if __name__ == "__main__":
    annot_path = '/Users/oytuntez/dev/cerebro-oasis-test/research/input/raw/lh.custom_regions_de_ki.annot'
    output_path = '/Users/oytuntez/dev/cerebro-oasis-test/research/input/raw/lh.custom_regions_de_ki.json'
    convert_annot_to_json(annot_path, output_path)
