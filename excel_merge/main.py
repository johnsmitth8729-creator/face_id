"""
excel_merge/main.py

Main entrypoint for the modular Excel Merge system.
Glues the loader, merger, numbering, and exporter components together.
"""
import os
import sys
import logging
import argparse

# Ensure parent directory is in path if executed directly
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from excel_merge.loader import load_valid_sheets
from excel_merge.merger import merge_worksheets, determine_header_rows
from excel_merge.numbering import renumber_tr_column
from excel_merge.exporter import save_merged_workbook

# Setup basic console logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("excel_merge.main")


def run_merge(folder_path: str, output_path: str = "Merged.xlsx"):
    """
    Load every xlsx workbook in folder_path, unmerge range values,
    merge them into one sheet preserving layout/style/widths/heights,
    renumber the 'T/r' column if present, and save as output_path.
    """
    logger.info("Starting Excel merge pipeline for folder: %s", folder_path)
    
    # 1. Load sheets
    loaded = load_valid_sheets(folder_path)
    if not loaded:
        logger.warning("No Excel (.xlsx) files found in %s. Exiting.", folder_path)
        return False
        
    logger.info("Found %d file(s) to merge.", len(loaded))

    # 2. Merge sheets
    merged_wb = merge_worksheets(loaded)
    
    # 3. Determine header size to perform renumbering
    header_size = determine_header_rows(loaded)
    
    # 4. Renumber the 'T/r' column
    merged_ws = merged_wb.active
    renumber_tr_column(merged_ws, header_size)
    
    # 5. Export to Merged.xlsx
    save_merged_workbook(merged_wb, output_path)
    logger.info("Excel merge pipeline successfully completed.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple Excel sheets preserving layout and formatting.")
    parser.add_argument("--folder", type=str, default="files", help="Path to folder containing .xlsx files (default: files)")
    parser.add_argument("--output", type=str, default="Merged.xlsx", help="Filename of the output merged file (default: Merged.xlsx)")
    
    args = parser.parse_args()
    
    # Resolve relative paths
    target_folder = os.path.abspath(args.folder)
    target_output = os.path.abspath(args.output)
    
    # Ensure default 'files' folder exists if running without arguments to prevent crash
    if args.folder == "files" and not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)
        logger.info("Created default folder: %s (put your .xlsx files here)", target_folder)

    run_merge(target_folder, target_output)
