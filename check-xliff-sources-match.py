from xml.etree import ElementTree as ET
import sys


def extract_source_tags(xml_string):
    """Extract all source tags and their corresponding group IDs from an XLIFF file."""
    try:
        root = ET.fromstring(xml_string)
        sources = {}

        # Find all trans-unit elements
        i = 0
        for trans_unit in root.findall(".//trans-unit"):
            # Get the source text
            source = trans_unit.find(".//source")
            if source is not None:
                source_text = ''.join(source.itertext())
                # if source_text.find("Exercise your free choice") > 0:
                #     print(source_text)
                sources[f"{i}_{trans_unit.get('id')}"] = source_text
                i = i + 1

        return sources
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return None


def compare_sources(sources1, sources2):
    """Compare two dictionaries of source tags and return differences."""
    all_keys = set(sources1.keys()) | set(sources2.keys())
    differences = []

    # Check for missing or different entries
    for key in sorted(all_keys):
        if key not in sources1:
            differences.append(f"Missing in first file: {key}")
        elif key not in sources2:
            differences.append(f"Missing in second file: {key}")
        elif sources1[key] != sources2[key]:
            differences.append(f"Different content for {key}:")
            differences.append(f"  File 1: {sources1[key]}")
            differences.append(f"  File 2: {sources2[key]}")

    return differences


def main(file1_content, file2_content):
    """Main function to compare two XLIFF files."""
    # Extract sources from both files
    sources1 = extract_source_tags(file1_content)
    sources2 = extract_source_tags(file2_content)

    if sources1 is None or sources2 is None:
        return ["Error: Failed to parse one or both XLIFF files"]

    # Compare the sources
    differences = compare_sources(sources1, sources2)

    # Prepare the report
    if not differences:
        return ["All source tags match perfectly between the two files."]
    else:
        return ["Found the following differences:"] + differences


if __name__ == "__main__":
    # Get file contents from command line arguments
    source_path = None
    target_path = None
    if len(sys.argv) != 3:
        source_path = "/Users/oytuntez/Downloads/burcu-original.xlf"
        target_path = "/Users/oytuntez/Downloads/burcu-translated-es-mx-fixed.xlf"
        print("Usage: script.py file1.xlf file2.xlf")
    else:
        source_path = sys.argv[1]
        target_path = sys.argv[2]


    with open(source_path, 'r', encoding='utf-8') as f1:
        file1_content = f1.read()
    with open(target_path, 'r', encoding='utf-8') as f2:
        file2_content = f2.read()

    report = main(file1_content, file2_content)
    for line in report:
        print(line)