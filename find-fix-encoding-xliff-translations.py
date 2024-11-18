from xml.etree import ElementTree as ET
import html
import sys


def normalize_encoding(text):
    """Normalize HTML encoded characters to a consistent format."""
    if text is None:
        return ""
    # First decode any HTML entities
    text = html.unescape(text)
    # Then encode specific characters consistently
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text


def find_encoding_mismatches(tree):
    """Find targets with encoding mismatches."""
    mismatches = []

    for trans_unit in tree.findall('.//trans-unit'):
        target = trans_unit.find('target')

        if target is not None and target.text:
            target_text = target.text
            trans_id = trans_unit.get('id')

            # Compare raw text for common encoding issues
            target_encoded = normalize_encoding(target_text)

            if target_encoded != target_text:
                mismatches.append({
                    'trans_id': trans_id,
                    'target_old': target_text,
                    'target_new': target_encoded
                })

    return mismatches


def fix_encoding_mismatches(input_file, output_file):
    """Find and fix encoding mismatches in the XLIFF file."""
    tree = ET.parse(input_file)
    mismatches = find_encoding_mismatches(tree)
    if not mismatches:
        print("No encoding mismatches found.")
        return

    print(f"\nFound {len(mismatches)} strings with encoding mismatches:")

    # Fix the mismatches
    for mismatch in mismatches:
        print(f"Trans-unit ID: {mismatch['trans_id']}")

        if mismatch['target_old'] != mismatch['target_new']:
            print("\nTarget encoding fixed:")
            print(f"Old: {mismatch['target_old']}")
            print(f"New: {mismatch['target_new']}")

        # Update the tree with fixed encodings
        for trans_unit in tree.findall('.//trans-unit'):
            if trans_unit.get('id') == mismatch['trans_id']:
                target = trans_unit.find('target')
                if target is not None:
                    # this was supposed to be from "target_new", but
                    # python xml library is already encoding while writing the file.
                    # so instead, we put the correct decoded html tags, python xml will encode them altogether.
                    target.text = mismatch['target_old']

    # Write the fixed file
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"\nFixed file written to: {output_file}")


def main():
    if len(sys.argv) != 3:
        print("Usage: script.py input.xlf output.xlf")
        input_file = "/Users/oytuntez/Downloads/burcu-translated-es-mx-fixed.xlf"
        output_file = "/Users/oytuntez/Downloads/burcu-translated-es-mx-fixed-encoding.xlf"
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
    try:
        fix_encoding_mismatches(input_file, output_file)
    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()