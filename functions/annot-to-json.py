import inngest
import os
import argparse
import json
import nibabel as nb
import numpy as np

from utilities.inngest import client as inngest_client
from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file

FUNCTION_NAME = "annot_to_json"

def annot_to_json(annot_file_path, output_path=None, **kwargs):
    """
    Convert FreeSurfer annotation (.annot) file to JSON format
    
    Args:
        annot_file_path (str): Path to the .annot file
        output_path (str, optional): Output JSON file path. If None, generates one.
        **kwargs: Additional parameters
        
    Returns:
        dict: Results with file paths and processing info
    """
    
    print(f"Processing annotation file: {annot_file_path}")
    
    # Generate output path if not provided
    if output_path is None:
        base_name = os.path.splitext(annot_file_path)[0]
        output_path = f"{base_name}.json"
    
    ########## FUNCTION LOGIC STARTS ##########
    
    # Read the annotation file
    labels, ctab, names = nb.freesurfer.read_annot(annot_file_path)

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

    # Save to JSON file
    with open(output_path, 'w') as f:
        json.dump(output, f)

    # Prepare result
    result = {
        "annot_file_path": annot_file_path,
        "output_path": output_path,
        "num_vertices": len(vertex_labels),
        "num_regions": len(regions),
        "unique_labels": len(set(vertex_labels)),
        "status": "processed"
    }
    
    ########## FUNCTION LOGIC ENDS ##########
    
    print(f"\nFile saved successfully to: {output_path}")
    return result


@inngest_client.create_function(
    fn_id=FUNCTION_NAME,
    trigger=inngest.TriggerEvent(event=f"{FUNCTION_NAME}_requested"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    """Inngest function wrapper for workflow automation"""
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    result = await step.run("execute-function", lambda: annot_to_json(**parameters))
    
    # TODO: Optionally trigger next step in pipeline
    # await inngest_client.send(
    #     inngest.Event(name="next_function_requested", data={"output_path": result["output_path"]})
    # )
    
    return result


# Command line interface for scientists
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert FreeSurfer annotation (.annot) file to JSON format')
    parser.add_argument('annot_file', help='Path to the .annot file to convert')
    parser.add_argument('--output', '-o', help='Output JSON file path (optional, will generate if not provided)')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.annot_file):
        print(f"❌ Error: File not found: {args.annot_file}")
        print("Please check the file path and try again.")
        os._exit(1)
    
    print("=== ANNOTATION TO JSON CONVERTER ===")
    print(f"Converting annotation file: {args.annot_file}")
    if args.output:
        print(f"Output will be saved to: {args.output}")
    else:
        print("Output path will be auto-generated")
    print("This will convert FreeSurfer annotation data to JSON format...")
    print("Please wait...\n")
    
    try:
        result = annot_to_json(args.annot_file, args.output)
        
        print(f"\n=== CONVERSION COMPLETE ===")
        print("✅ Annotation file converted successfully")
        print(f"📄 Input file: {result['annot_file_path']}")
        print(f"📄 Output file: {result['output_path']}")
        print(f"📊 Vertices processed: {result['num_vertices']:,}")
        print(f"🧠 Brain regions: {result['num_regions']}")
        print(f"🏷️  Unique labels: {result['unique_labels']}")
        
    except Exception as e:
        print(f"❌ Error during conversion: {str(e)}")
        print("Please check your file format and try again.")
        os._exit(1)
    
    # Force exit to prevent hanging
    os._exit(0)
