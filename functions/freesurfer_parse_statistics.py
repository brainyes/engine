import os
import argparse
from datetime import datetime

from utilities.data import supabase
from utilities.freesurfer_parsers import (
    parse_freesurfer_stats_directory,
    get_summary_statistics
)

FUNCTION_NAME = "freesurfer_parse_statistics"

def freesurfer_parse_statistics(nifti_file_id, freesurfer_output_directory, subject_id=None, processing_method=None, **kwargs):
    """
    Parse FreeSurfer/FastSurfer statistics files and store results in database.

    This function works with both FreeSurfer and FastSurfer outputs. FastSurfer produces
    FreeSurfer-compatible statistics files, so we can reuse the FreeSurfer parsers.
    The output format is identical.

    Args:
        nifti_file_id (str): The ID of the original NIFTI file
        freesurfer_output_directory (str): Path to FreeSurfer/FastSurfer subject output directory
        subject_id (str): Subject identifier
        processing_method (str): "freesurfer" or "fastsurfer". If None, auto-detects based on files present.
        **kwargs: Additional parameters

    Returns:
        dict: Results of parsing and storage
    """

    print(f"Parsing statistics for NIFTI file: {nifti_file_id}")
    print(f"Output directory: {freesurfer_output_directory}")

    if not os.path.exists(freesurfer_output_directory):
        raise FileNotFoundError(f"Output directory not found: {freesurfer_output_directory}")

    stats_directory = os.path.join(freesurfer_output_directory, "stats")
    if not os.path.exists(stats_directory):
        raise FileNotFoundError(f"Stats directory not found: {stats_directory}")

    # Auto-detect processing method if not specified
    if processing_method is None:
        # Check for FastSurfer-specific files
        fastsurfer_indicators = [
            os.path.join(stats_directory, "lh.aparc.DKTatlas.mapped.stats"),
            os.path.join(stats_directory, "rh.aparc.DKTatlas.mapped.stats"),
            os.path.join(freesurfer_output_directory, "mri", "aparc.DKTatlas+aseg.deep.mgz")
        ]

        if any(os.path.exists(f) for f in fastsurfer_indicators):
            processing_method = "fastsurfer"
            print("🔍 Auto-detected: FastSurfer output")
        else:
            processing_method = "freesurfer"
            print("🔍 Auto-detected: FreeSurfer output")
    else:
        print(f"📋 Processing method: {processing_method}")

    try:
        # Parse all statistics files using FreeSurfer parsers
        # FastSurfer produces FreeSurfer-compatible stats files
        print("📊 Parsing statistics files...")
        parsed_stats = parse_freesurfer_stats_directory(stats_directory)

        # Generate summary statistics
        summary_stats = get_summary_statistics(parsed_stats)

        print(f"✅ Successfully parsed {len(parsed_stats['all_files'])} statistics files")
        print(f"Files processed: {', '.join(parsed_stats['all_files'])}")

        # Store global brain measures
        # Note: We use the same database tables for both FreeSurfer and FastSurfer
        global_measures_stored = 0
        if parsed_stats.get("aseg") and "global_measures" in parsed_stats["aseg"]:
            print("💾 Storing global brain measures...")

            for measure_name, measure_data in parsed_stats["aseg"]["global_measures"].items():
                record = {
                    "nifti_file_id": nifti_file_id,
                    "measure_name": measure_name,
                    "measure_field": measure_data["field"],
                    "value": measure_data["value"],
                    "unit": measure_data["unit"],
                    "source_file": "aseg.stats",
                    "processing_method": processing_method,  # Distinguish FreeSurfer vs FastSurfer
                    "created_at": datetime.now().isoformat()
                }

                try:
                    # Store in freesurfer_global_measures table
                    # (We reuse the same table structure for compatibility)
                    response = supabase.table("freesurfer_global_measures").upsert(
                        record,
                        on_conflict="nifti_file_id,measure_name"
                    ).execute()
                    global_measures_stored += 1
                except Exception as e:
                    print(f"Warning: Failed to store global measure {measure_name}: {e}")

        # Store regional measurements (aparc data)
        regional_measures_stored = 0
        for hemisphere in ["lh", "rh"]:
            aparc_key = f"{hemisphere}_aparc"
            if parsed_stats.get(aparc_key) and "regions" in parsed_stats[aparc_key]:
                print(f"💾 Storing {hemisphere} cortical regional measures...")

                for region_data in parsed_stats[aparc_key]["regions"]:
                    record = {
                        "nifti_file_id": nifti_file_id,
                        "hemisphere": hemisphere,
                        "structure_name": region_data["structure_name"],
                        "num_vertices": region_data["num_vertices"],
                        "surface_area": region_data["surface_area"],
                        "gray_vol": region_data["gray_vol"],
                        "thick_avg": region_data["thick_avg"],
                        "thick_std": region_data["thick_std"],
                        "mean_curv": region_data["mean_curv"],
                        "gauss_curv": region_data["gauss_curv"],
                        "fold_ind": region_data["fold_ind"],
                        "curv_ind": region_data["curv_ind"],
                        "atlas": "aparc",
                        "processing_method": processing_method,  # Distinguish FreeSurfer vs FastSurfer
                        "created_at": datetime.now().isoformat()
                    }

                    try:
                        # Store in freesurfer_cortical_regions table
                        response = supabase.table("freesurfer_cortical_regions").upsert(
                            record,
                            on_conflict="nifti_file_id,hemisphere,structure_name,atlas"
                        ).execute()
                        regional_measures_stored += 1
                    except Exception as e:
                        print(f"Warning: Failed to store regional measure {hemisphere}.{region_data['structure_name']}: {e}")

        # Store subcortical segmentations
        subcortical_stored = 0
        if parsed_stats.get("aseg") and "segmentations" in parsed_stats["aseg"]:
            print("💾 Storing subcortical segmentation measures...")

            for seg_data in parsed_stats["aseg"]["segmentations"]:
                record = {
                    "nifti_file_id": nifti_file_id,
                    "seg_id": seg_data["seg_id"],
                    "structure_name": seg_data["structure_name"],
                    "nvoxels": seg_data["nvoxels"],
                    "volume_mm3": seg_data["volume_mm3"],
                    "norm_mean": seg_data["norm_mean"],
                    "norm_stddev": seg_data["norm_stddev"],
                    "norm_min": seg_data["norm_min"],
                    "norm_max": seg_data["norm_max"],
                    "norm_range": seg_data["norm_range"],
                    "processing_method": processing_method,  # Distinguish FreeSurfer vs FastSurfer
                    "created_at": datetime.now().isoformat()
                }

                try:
                    # Store in freesurfer_subcortical_segmentations table
                    response = supabase.table("freesurfer_subcortical_segmentations").upsert(
                        record,
                        on_conflict="nifti_file_id,seg_id"
                    ).execute()
                    subcortical_stored += 1
                except Exception as e:
                    print(f"Warning: Failed to store subcortical segmentation {seg_data['structure_name']}: {e}")

        # Store curvature statistics (only if surfaces were computed)
        curvature_stored = 0
        for hemisphere in ["lh", "rh"]:
            curv_key = f"{hemisphere}_curv"
            if parsed_stats.get(curv_key) and "curvature_stats" in parsed_stats[curv_key]:
                print(f"💾 Storing {hemisphere} curvature statistics...")

                curv_stats = parsed_stats[curv_key]["curvature_stats"]
                record = {
                    "nifti_file_id": nifti_file_id,
                    "hemisphere": hemisphere,
                    **curv_stats,
                    "processing_method": processing_method,  # Distinguish FreeSurfer vs FastSurfer
                    "created_at": datetime.now().isoformat()
                }

                try:
                    # Store in freesurfer_curvature_stats table
                    response = supabase.table("freesurfer_curvature_stats").upsert(
                        record,
                        on_conflict="nifti_file_id,hemisphere"
                    ).execute()
                    curvature_stored += 1
                except Exception as e:
                    print(f"Warning: Failed to store curvature stats for {hemisphere}: {e}")

        # Store summary statistics for quick access
        if summary_stats:
            print("💾 Storing summary statistics...")
            summary_record = {
                "nifti_file_id": nifti_file_id,
                **summary_stats,
                "processing_method": processing_method,  # Distinguish FreeSurfer vs FastSurfer
                "created_at": datetime.now().isoformat()
            }

            try:
                response = supabase.table("freesurfer_summary_stats").upsert(
                    summary_record,
                    on_conflict="nifti_file_id"
                ).execute()
            except Exception as e:
                print(f"Warning: Failed to store summary statistics: {e}")

        result = {
            "nifti_file_id": nifti_file_id,
            "freesurfer_output_directory": freesurfer_output_directory,
            "subject_id": subject_id,
            "status": "completed",
            "processing_method": processing_method,
            "statistics": {
                "files_parsed": len(parsed_stats['all_files']),
                "files_list": parsed_stats['all_files'],
                "global_measures_stored": global_measures_stored,
                "regional_measures_stored": regional_measures_stored,
                "subcortical_stored": subcortical_stored,
                "curvature_stored": curvature_stored
            },
            "summary_stats": summary_stats,
            "message": f"Successfully parsed and stored statistics for {len(parsed_stats['all_files'])} files"
        }

        print(f"✅ Statistics parsing completed successfully!")
        print(f"Stored: {global_measures_stored} global measures, {regional_measures_stored} regional measures")
        print(f"Stored: {subcortical_stored} subcortical segments, {curvature_stored} curvature stats")
        print(f"Processing method: {processing_method}")

        return result

    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "freesurfer_output_directory": freesurfer_output_directory,
            "subject_id": subject_id,
            "status": "failed",
            "error": str(e),
            "message": f"Statistics parsing failed: {str(e)}"
        }
        print(f"❌ Statistics parsing failed: {str(e)}")
        return error_result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parse FreeSurfer/FastSurfer statistics and store in database')
    parser.add_argument('nifti_file_id', help='NIFTI file ID')
    parser.add_argument('freesurfer_output_directory', help='Path to FreeSurfer/FastSurfer subject output directory')
    parser.add_argument('--subject-id', help='Subject identifier')
    parser.add_argument('--processing-method', choices=['freesurfer', 'fastsurfer'],
                       help='Processing method (auto-detects if not specified)')

    args = parser.parse_args()

    print(f"=== FREESURFER/FASTSURFER STATISTICS PARSING ===")
    print(f"NIFTI file ID: {args.nifti_file_id}")
    print(f"Output directory: {args.freesurfer_output_directory}")
    print("This will parse statistics files and store measurements in database")
    print("Works with both FreeSurfer and FastSurfer outputs")
    print("Please wait...\n")

    try:
        kwargs = {}
        if args.subject_id:
            kwargs['subject_id'] = args.subject_id
        if args.processing_method:
            kwargs['processing_method'] = args.processing_method

        result = freesurfer_parse_statistics(
            args.nifti_file_id,
            args.freesurfer_output_directory,
            **kwargs
        )

        print(f"\n=== PARSING COMPLETE ===")
        if result['status'] == 'completed':
            print("✅ Statistics parsed and stored successfully")
            print(f"Files processed: {result['statistics']['files_parsed']}")
            print(f"Global measures: {result['statistics']['global_measures_stored']}")
            print(f"Regional measures: {result['statistics']['regional_measures_stored']}")
            print(f"Processing method: {result['processing_method']}")
        else:
            print("❌ Statistics parsing failed")
            print(f"Error: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"❌ Error during parsing: {str(e)}")
        print("Please check your paths and database connection.")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)
