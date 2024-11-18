import tempfile
import os
import gzip
import io

def save_to_temp_file(nifti_gz_data, original_name_or_extension=".nii", prefix="cerebro_"):
    """
    Save downloaded Supabase file data to a temporary file.

    Args:
        nifti_gz_data: The binary data from Supabase storage
        prefix: Prefix for the temp filename (default: "cerebro_")
        suffix: Suffix for the temp filename (default: ".nii.gz")

    Returns:
        str: Path to the temporary file
    """
    extension = os.path.splitext(original_name_or_extension)[1] if '.' in original_name_or_extension else original_name_or_extension

    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(prefix=prefix,
                                            suffix=extension,
                                            delete=False)

    try:
        # Write the binary data to the temporary file
        temp_file.write(nifti_gz_data)
        temp_file.flush()  # Ensure all data is written
        return temp_file.name
    finally:
        temp_file.close()


def prefix_file_in_paths(prefix, path_list):
    if not prefix.endswith("-"):
        prefix = prefix + "-"
    path_list[-1] = f"{prefix}{path_list[-1]}"
    return path_list

def prefix_file_in_path(prefix, path_str):
    if not prefix.endswith("-"):
        prefix = prefix + "-"
    directory, filename = os.path.split(path_str)
    return os.path.join(directory, f"{prefix}{filename}")


def compress_in_memory(content):
    """
    Compress content in memory without writing to disk.

    Args:
        content (str or bytes): Content to compress

    Returns:
        bytes: Compressed content
    """
    # Convert to bytes if it's a string
    if isinstance(content, str):
        content = content.encode('utf-8')

    # Compress in memory
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode='wb') as f:
        f.write(content)

    return out.getvalue()