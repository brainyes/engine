"""
FreeSurfer Statistics File Parsers

Parses various FreeSurfer .stats files into structured data for database storage.
"""

import re
import os
from typing import Dict, List, Tuple, Optional, Any


def parse_freesurfer_measure_line(line: str) -> Optional[Tuple[str, str, float, str]]:
    """
    Parse a FreeSurfer "# Measure" line.
    
    Format: # Measure <name>, <field>, <description>, <value>, <unit>
    
    Returns:
        Tuple of (name, field, value, unit) or None if not a measure line
    """
    if not line.startswith("# Measure "):
        return None
    
    # Remove "# Measure " prefix and split by comma
    content = line[10:].strip()
    parts = [p.strip() for p in content.split(',')]
    
    if len(parts) >= 4:
        name = parts[0]
        field = parts[1] 
        # Description is parts[2], but we don't need it for storage
        value = float(parts[3])
        unit = parts[4] if len(parts) > 4 else ""
        return (name, field, value, unit)
    
    return None


def parse_aseg_stats(file_path: str) -> Dict[str, Any]:
    """
    Parse aseg.stats file containing subcortical segmentation statistics.
    
    Returns:
        Dictionary with global measures and segmentation data
    """
    result = {
        "global_measures": {},
        "segmentations": [],
        "metadata": {}
    }
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Parse header metadata
    for line in lines:
        line = line.strip()
        
        # Parse global measures
        measure = parse_freesurfer_measure_line(line)
        if measure:
            name, field, value, unit = measure
            result["global_measures"][name] = {
                "field": field,
                "value": value,
                "unit": unit
            }
        
        # Parse other metadata
        elif line.startswith("# subjectname "):
            result["metadata"]["subject_name"] = line.split()[-1]
        elif line.startswith("# cvs_version "):
            result["metadata"]["freesurfer_version"] = line.split()[-1]
        elif line.startswith("# anatomy_type "):
            result["metadata"]["anatomy_type"] = line.split()[-1]
    
    # Parse segmentation data table
    data_lines = [line.strip() for line in lines if not line.startswith('#') and line.strip()]
    
    for line in data_lines:
        parts = line.split()
        if len(parts) >= 6:
            try:
                seg_data = {
                    "index": int(parts[0]),
                    "seg_id": int(parts[1]),
                    "nvoxels": int(parts[2]),
                    "volume_mm3": float(parts[3]),
                    "structure_name": parts[4],
                    "norm_mean": float(parts[5]) if len(parts) > 5 else None,
                    "norm_stddev": float(parts[6]) if len(parts) > 6 else None,
                    "norm_min": float(parts[7]) if len(parts) > 7 else None,
                    "norm_max": float(parts[8]) if len(parts) > 8 else None,
                    "norm_range": float(parts[9]) if len(parts) > 9 else None
                }
                result["segmentations"].append(seg_data)
            except (ValueError, IndexError):
                continue
    
    return result


def parse_aparc_stats(file_path: str) -> Dict[str, Any]:
    """
    Parse cortical parcellation stats (aparc.stats, aparc.DKTatlas.stats, etc.).
    
    Returns:
        Dictionary with global measures and regional data
    """
    result = {
        "global_measures": {},
        "regions": [],
        "metadata": {}
    }
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Determine hemisphere from filename
    hemisphere = "lh" if "lh." in os.path.basename(file_path) else "rh"
    result["metadata"]["hemisphere"] = hemisphere
    
    # Parse header metadata and measures
    for line in lines:
        line = line.strip()
        
        # Parse global measures
        measure = parse_freesurfer_measure_line(line)
        if measure:
            name, field, value, unit = measure
            result["global_measures"][name] = {
                "field": field,
                "value": value,
                "unit": unit
            }
        
        # Parse other metadata
        elif line.startswith("# subjectname "):
            result["metadata"]["subject_name"] = line.split()[-1]
        elif line.startswith("# hemi "):
            result["metadata"]["hemisphere"] = line.split()[-1]
        elif line.startswith("# AnnotationFile "):
            result["metadata"]["annotation_file"] = line.split()[-1]
    
    # Parse regional data table
    data_lines = [line.strip() for line in lines if not line.startswith('#') and line.strip()]
    
    for line in data_lines:
        parts = line.split()
        if len(parts) >= 5:
            try:
                region_data = {
                    "structure_name": parts[0],
                    "num_vertices": int(parts[1]) if parts[1] != '0' else 0,
                    "surface_area": float(parts[2]) if parts[2] != '0' else 0.0,
                    "gray_vol": float(parts[3]) if parts[3] != '0' else 0.0,
                    "thick_avg": float(parts[4]) if len(parts) > 4 and parts[4] != '0' else None,
                    "thick_std": float(parts[5]) if len(parts) > 5 and parts[5] != '0' else None,
                    "mean_curv": float(parts[6]) if len(parts) > 6 and parts[6] != '0' else None,
                    "gauss_curv": float(parts[7]) if len(parts) > 7 and parts[7] != '0' else None,
                    "fold_ind": int(parts[8]) if len(parts) > 8 and parts[8] != '0' else None,
                    "curv_ind": float(parts[9]) if len(parts) > 9 and parts[9] != '0' else None
                }
                result["regions"].append(region_data)
            except (ValueError, IndexError):
                continue
    
    return result


def parse_curv_stats(file_path: str) -> Dict[str, Any]:
    """
    Parse curvature statistics files (lh.curv.stats, rh.curv.stats).
    
    Returns:
        Dictionary with curvature measurements
    """
    result = {
        "curvature_stats": {},
        "metadata": {}
    }
    
    # Determine hemisphere from filename
    hemisphere = "lh" if "lh." in os.path.basename(file_path) else "rh"
    result["metadata"]["hemisphere"] = hemisphere
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Parse curvature statistics using regex patterns
    patterns = {
        "mean": r"Raw <mean> \+- <std> \(using '[lr]h\.curv'\):\s+([-\d\.]+) \+- ([\d\.]+)",
        "min": r"Raw Min:\s+([-\d\.]+) at vertex (\d+)",
        "max": r"Raw Max:\s+([-\d\.]+) at vertex (\d+)",
        "surface_area": r"Raw Total Surface Area:\s+([\d\.]+) mm\^2",
        "num_vertices": r"Raw Total Number of Vertices:\s+(\d+)",
        "vertex_area": r"Raw Average Vertex Area \(Whole Surface\):\s+([\d\.]+) mm\^2",
        "vertex_separation": r"Raw Mean Vertex Separation \(Whole Surface\):\s+([\d\.]+) \+- ([\d\.]+) mm"
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            if key == "mean":
                result["curvature_stats"]["curv_mean"] = float(match.group(1))
                result["curvature_stats"]["curv_std"] = float(match.group(2))
            elif key == "min":
                result["curvature_stats"]["curv_min"] = float(match.group(1))
                result["curvature_stats"]["curv_min_vertex"] = int(match.group(2))
            elif key == "max":
                result["curvature_stats"]["curv_max"] = float(match.group(1))
                result["curvature_stats"]["curv_max_vertex"] = int(match.group(2))
            elif key == "vertex_separation":
                result["curvature_stats"]["vertex_separation_mean"] = float(match.group(1))
                result["curvature_stats"]["vertex_separation_std"] = float(match.group(2))
            else:
                value = float(match.group(1))
                # Convert to int for specific fields that should be integers
                if key in ["num_vertices"]:
                    value = int(value)
                result["curvature_stats"][key] = value
    
    return result


def parse_freesurfer_stats_directory(stats_dir: str) -> Dict[str, Any]:
    """
    Parse all statistics files in a FreeSurfer stats directory.
    
    Args:
        stats_dir: Path to the stats directory
        
    Returns:
        Dictionary with all parsed statistics organized by type
    """
    result = {
        "aseg": None,
        "brainvol": None,
        "wmparc": None,
        "lh_aparc": None,
        "rh_aparc": None,
        "lh_aparc_DKT": None,
        "rh_aparc_DKT": None,
        "lh_aparc_a2009s": None,
        "rh_aparc_a2009s": None,
        "lh_curv": None,
        "rh_curv": None,
        "all_files": []
    }
    
    if not os.path.exists(stats_dir):
        return result
    
    # Map file patterns to parsing functions
    file_patterns = {
        "aseg.stats": ("aseg", parse_aseg_stats),
        "brainvol.stats": ("brainvol", parse_aseg_stats),  # Same format as aseg
        "wmparc.stats": ("wmparc", parse_aseg_stats),  # Same format as aseg
        "lh.aparc.stats": ("lh_aparc", parse_aparc_stats),
        "rh.aparc.stats": ("rh_aparc", parse_aparc_stats),
        "lh.aparc.DKTatlas.stats": ("lh_aparc_DKT", parse_aparc_stats),
        "rh.aparc.DKTatlas.stats": ("rh_aparc_DKT", parse_aparc_stats),
        "lh.aparc.a2009s.stats": ("lh_aparc_a2009s", parse_aparc_stats),
        "rh.aparc.a2009s.stats": ("rh_aparc_a2009s", parse_aparc_stats),
        "lh.curv.stats": ("lh_curv", parse_curv_stats),
        "rh.curv.stats": ("rh_curv", parse_curv_stats)
    }
    
    # Parse each file that exists
    for filename, (key, parser_func) in file_patterns.items():
        file_path = os.path.join(stats_dir, filename)
        if os.path.exists(file_path):
            try:
                result[key] = parser_func(file_path)
                result["all_files"].append(filename)
            except Exception as e:
                print(f"Error parsing {filename}: {e}")
                result[key] = {"error": str(e)}
    
    return result


def get_summary_statistics(parsed_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key summary statistics from parsed FreeSurfer data.

    Returns:
        Dictionary with the most important measurements for quick analysis
    """
    summary = {}

    # Global brain measures from aseg
    if parsed_stats.get("aseg") and "global_measures" in parsed_stats["aseg"]:
        measures = parsed_stats["aseg"]["global_measures"]
        summary.update({
            "total_brain_volume": measures.get("BrainSeg", {}).get("value"),
            "total_cortex_volume": measures.get("Cortex", {}).get("value"),
            "total_white_matter": measures.get("CerebralWhiteMatter", {}).get("value"),
            "estimated_total_intracranial_volume": measures.get("EstimatedTotalIntraCranialVol", {}).get("value")
        })

    # Hemisphere volumes from aparc
    for hemi in ["lh", "rh"]:
        aparc_key = f"{hemi}_aparc"
        if parsed_stats.get(aparc_key) and "global_measures" in parsed_stats[aparc_key]:
            measures = parsed_stats[aparc_key]["global_measures"]
            summary[f"{hemi}_cortex_volume"] = measures.get("Cortex", {}).get("value")
            summary[f"{hemi}_surface_area"] = measures.get("WhiteSurfArea", {}).get("value")
            summary[f"{hemi}_mean_thickness"] = measures.get("MeanThickness", {}).get("value")

    # Curvature summary
    for hemi in ["lh", "rh"]:
        curv_key = f"{hemi}_curv"
        if parsed_stats.get(curv_key) and "curvature_stats" in parsed_stats[curv_key]:
            curv = parsed_stats[curv_key]["curvature_stats"]
            summary[f"{hemi}_mean_curvature"] = curv.get("curv_mean")
            summary[f"{hemi}_surface_area_from_curv"] = curv.get("surface_area")

    return summary


def parse_annot_file(annot_file_path: str) -> Dict[str, Any]:
    """
    Convert FreeSurfer annotation (.annot) file to structured dictionary format.
    Core utility function for annotation parsing and conversion.

    Args:
        annot_file_path: Path to the .annot file

    Returns:
        Dictionary with vertex labels and region definitions
    """
    import nibabel as nb
    import numpy as np

    # Read the annotation file
    labels, ctab, names = nb.freesurfer.read_annot(annot_file_path)

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
    vertex_labels = [int(l) for l in labels]

    return {
        "labels": vertex_labels,
        "regions": regions,
        "num_vertices": len(vertex_labels),
        "num_regions": len(regions),
        "unique_labels": len(set(vertex_labels))
    }