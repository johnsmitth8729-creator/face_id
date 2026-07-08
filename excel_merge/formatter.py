"""
excel_merge/formatter.py

Responsible for:
- Copying cell formatting (font, border, fill, alignment, number format)
- Copying row heights and column widths
"""
from copy import copy
import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

def copy_cell_style(src_cell: openpyxl.cell.Cell, dest_cell: openpyxl.cell.Cell):
    """Copy all styling from src_cell to dest_cell."""
    if src_cell.has_style:
        dest_cell.font = copy(src_cell.font)
        dest_cell.border = copy(src_cell.border)
        dest_cell.fill = copy(src_cell.fill)
        dest_cell.alignment = copy(src_cell.alignment)
        dest_cell.number_format = src_cell.number_format  # string assignment, no copy needed
        dest_cell.hyperlink = copy(src_cell.hyperlink)


def copy_row_formatting(src_ws: Worksheet, src_row_idx: int, dest_ws: Worksheet, dest_row_idx: int):
    """Copy row dimensions/heights from source row to destination row."""
    # Copy row height if specified
    if src_row_idx in src_ws.row_dimensions:
        src_dim = src_ws.row_dimensions[src_row_idx]
        if src_dim.height is not None:
            dest_ws.row_dimensions[dest_row_idx].height = src_dim.height
        # Preserve hidden row state if requested (or let loader skip it completely)
        dest_ws.row_dimensions[dest_row_idx].hidden = src_dim.hidden


def update_column_widths(src_ws: Worksheet, dest_ws: Worksheet, is_first: bool = False):
    """
    Ensure the destination sheet's columns are wide enough to preserve formatting.
    For the first worksheet, we overwrite destination widths with source widths.
    For subsequent worksheets, we only update if the source width is larger.
    """
    for col_name, col_dim in src_ws.column_dimensions.items():
        if col_dim.width is not None:
            current_width = dest_ws.column_dimensions[col_name].width
            if is_first or current_width is None or col_dim.width > current_width:
                dest_ws.column_dimensions[col_name].width = col_dim.width
