"""
excel_merge/loader.py

Responsible for:
- Scanning a folder for valid Excel (.xlsx) files (filtering out temporary lock files starting with ~$ or non-xlsx files)
- Loading each workbook using openpyxl in data_only=True mode (to get computed cell values instead of raw formulas)
- Extracting the first visible worksheet of each workbook
- Providing helpers to determine visible vs hidden rows.
"""
import os
import logging
import openpyxl
from typing import List, Tuple

logger = logging.getLogger(__name__)


def list_xlsx_files(folder_path: str) -> List[str]:
    """Scan the given folder and return sorted paths of valid .xlsx files."""
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    files = []
    for f in os.listdir(folder_path):
        # Scan only for .xlsx, ignore temporary lock files (~$filename.xlsx)
        if f.endswith('.xlsx') and not f.startswith('~$'):
            files.append(os.path.join(folder_path, f))
    
    # Sort files alphabetically to ensure deterministic merge order
    return sorted(files)


def get_first_visible_sheet(wb: openpyxl.Workbook) -> openpyxl.worksheet.worksheet.Worksheet:
    """Find the first visible worksheet in the workbook. Fallback to active sheet if none visible."""
    for name in wb.sheetnames:
        ws = wb[name]
        # In openpyxl, sheet_state can be 'visible', 'hidden', or 'veryHidden'
        # Default is usually 'visible' or None (which implies visible)
        if ws.sheet_state is None or ws.sheet_state == 'visible':
            return ws
    return wb.active


def is_row_hidden(ws: openpyxl.worksheet.worksheet.Worksheet, row_idx: int) -> bool:
    """Check if a specific row is hidden in the worksheet."""
    dim = ws.row_dimensions.get(row_idx)
    return dim is not None and dim.hidden


def load_valid_sheets(folder_path: str) -> List[Tuple[str, openpyxl.Workbook, openpyxl.worksheet.worksheet.Worksheet]]:
    """
    Load all valid xlsx files in folder_path.
    Returns list of tuples: (filename, workbook, first_visible_worksheet)
    """
    file_paths = list_xlsx_files(folder_path)
    loaded = []
    
    for path in file_paths:
        filename = os.path.basename(path)
        try:
            # data_only=True loads cell values instead of Excel formulas
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = get_first_visible_sheet(wb)
            loaded.append((filename, wb, ws))
            logger.info("Successfully loaded file: %s, active sheet: %s", filename, ws.title)
        except Exception as e:
            logger.error("Failed to load Excel file %s: %s", filename, e)
            raise e

    return loaded
