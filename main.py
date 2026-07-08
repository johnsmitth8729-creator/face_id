"""
Root-level entrypoint for the Excel Merge system.
Delegates execution to the excel_merge package.
"""
import os
import sys

from excel_merge.main import run_merge

if __name__ == "__main__":
    # Allow passing the target folder as the first positional argument
    folder = "files"
    if len(sys.argv) > 1:
        folder = sys.argv[1]

    target_folder = os.path.abspath(folder)
    target_output = os.path.abspath("Merged.xlsx")

    # If the folder doesn't exist, create it so the user can easily place files there
    if not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)
        print(f"Created folder: {target_folder} (please place your source .xlsx files here)")

    # Execute the merge
    success = run_merge(target_folder, target_output)
    if success:
        print(f"Merged workbook successfully generated at: {target_output}")
        sys.exit(0)
    else:
        print("Merge failed.")
        sys.exit(1)
