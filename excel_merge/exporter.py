"""
excel_merge/exporter.py

Responsible for saving the merged workbook to a specified output file path.
"""
import logging
import openpyxl

logger = logging.getLogger(__name__)


def save_merged_workbook(wb: openpyxl.Workbook, output_path: str):
    """Save the final in-memory workbook to the given file path."""
    try:
        wb.save(output_path)
        logger.info("Successfully exported merged data to %s", output_path)
    except Exception as e:
        logger.error("Failed to save merged workbook to %s: %s", output_path, e)
        raise e
