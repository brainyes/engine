from xml.etree import ElementTree as ET
import sys
import copy

# This script takes 2 files: original and translated XLIFF files.
# It copies the <source> tags from original into the translated XLIFF's <source> tags for the strings with the same ID.

def create_id_map(root):
    """Create a mapping of group_id + trans_unit_id to source element."""
    id_map = {}
    for group in root.findall(".//group"):
        group_id = group.get('id')
        for trans_unit in group.findall(".//trans-unit"):
            trans_id = trans_unit.get('id')
            key = f"{group_id}_{trans_id}"
            source = trans_unit.find(".//source")
            if source is not None:
                id_map[key] = source
    return id_map


def update_sources(original_file, translated_file, output_file):
    """Update source tags in translated file to match original file."""
    # Parse both files
    original_tree = ET.parse(original_file)
    translated_tree = ET.parse(translated_file)

    # Create maps for both files
    original_map = create_id_map(original_tree.getroot())
    translated_map = create_id_map(translated_tree.getroot())

    # Track updates
    updates = []
    not_found = []

    # Update sources in translated file
    for key, orig_source in original_map.items():
        if key in translated_map:
            trans_source = translated_map[key]
            if trans_source.text != orig_source.text:
                old_text = trans_source.text
                trans_source.text = orig_source.text
                updates.append(f"Updated {key}:")
                updates.append(f"  Old: {old_text}")
                updates.append(f"  New: {orig_source.text}")
        else:
            not_found.append(key)

    # Write updated translated file
    translated_tree.write(output_file, encoding='utf-8', xml_declaration=True)

    return updates, not_found


def main():
    if len(sys.argv) != 4:
        original_file = "/Users/oytuntez/Downloads/burcu-original.xlf"
        translated_file = "/Users/oytuntez/Downloads/burcu-translated-es-mx.xlf"
        output_file = "/Users/oytuntez/Downloads/burcu-translated-es-mx-fixed.xlf"
        print("Usage: script.py file1.xlf file2.xlf output.xlf")
    else:
        original_file = sys.argv[1]
        translated_file = sys.argv[2]
        output_file = sys.argv[3]

    try:
        updates, not_found = update_sources(original_file, translated_file, output_file)

        print("\nSource Update Report:")
        print("-------------------")

        if updates:
            print("\nUpdated entries:")
            for update in updates:
                print(update)
        else:
            print("\nNo source texts needed updating.")

        if not_found:
            print("\nEntries in original not found in translated file:")
            for entry in not_found:
                print(f"  {entry}")

        print(f"\nUpdated file written to: {output_file}")

    except Exception as e:
        print(f"Error processing files: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()