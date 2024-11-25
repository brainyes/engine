import tempfile
import os
import gzip
import io
from matplotlib import pyplot as plt


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


def cast_value(value):
    """
    Cast a string value to its appropriate Python data type. Typically used for things like DB-accessed meta values.

    Args:
        value: The value to cast (usually a string from database)

    Returns:
        The value cast to its appropriate type (int, float, bool, or str)
    """
    # Handle None/null values
    if value is None:
        return None

    # Convert to string first to handle any input
    str_value = str(value).strip().lower()

    # Handle boolean values
    if str_value in ('true', 'false'):
        return str_value == 'true'

    # Try casting to numeric types
    try:
        # Check if it's an integer
        if str_value.isdigit() or (str_value.startswith('-') and str_value[1:].isdigit()):
            return int(str_value)

        # Check if it's a float
        float_value = float(str_value)
        # Check if it's actually an integer
        if float_value.is_integer():
            return int(float_value)
        return float_value

    except ValueError:
        # If all else fails, return as string
        return value


def plot_to_image():
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    return buffer.getvalue()