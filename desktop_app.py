"""Offline Windows desktop wrapper for ELAC Connect."""
from pathlib import Path
import json
import os
import sys
import traceback

import webview

import cleaner_engine

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
HTML_PATH = APP_DIR / "index.html"


class DesktopAPI:
    """Functions the HTML interface can call through pywebview."""

    def __init__(self):
        self.window = None
        self.pending_records = None
        self.pending_long_sessions = None
        self.pending_output_folder = None

    def set_window(self, window):
        self.window = window

    def choose_input_files(self):
        """Open the native Windows file picker for CSV/Excel exports."""
        if not self.window:
            return []
        try:
            chosen = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=("CSV files (*.csv)", "Excel workbooks (*.xlsx;*.xls)", "All supported files (*.csv;*.xlsx;*.xls)"),
            )
            return list(chosen or [])
        except Exception as exc:
            return {"error": str(exc)}

    def choose_output_folder(self):
        """Open the native Windows folder picker."""
        if not self.window:
            return ""
        try:
            chosen = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            return str(chosen[0]) if chosen else ""
        except Exception as exc:
            return {"error": str(exc)}

    def open_output_folder(self, output_folder):
        """Open the selected output folder in Windows File Explorer."""
        try:
            if not output_folder or not os.path.isdir(output_folder):
                return {"error": "The output folder is not available."}
            if sys.platform == "win32":
                os.startfile(output_folder)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", output_folder])
            return {"success": True}
        except Exception as exc:
            return {"error": str(exc)}

    def prepare_cleaning(self, input_paths, output_folder):
        """Analyze input files and return proposed corrections before export."""
        try:
            if not input_paths:
                return {"error": "Choose at least one Penji file first."}
            if not output_folder or not os.path.isdir(output_folder):
                return {"error": "Choose a valid output folder."}

            records, long_sessions = cleaner_engine.prepare_files(list(input_paths))
            clean, verification, unresolved, _changes, candidates = cleaner_engine.process_records(records, {})
            preview_students = cleaner_engine.aggregate_students(clean)
            self.pending_records = records
            self.pending_long_sessions = long_sessions
            self.pending_output_folder = output_folder

            def records_preview(frame, limit=500):
                if frame is None or frame.empty:
                    return []
                return json.loads(frame.head(limit).fillna("").to_json(orient="records"))

            flags = long_sessions
            return {
                "success": True,
                "prepared": True,
                "summary": {
                    "unique_students": int(len(preview_students)),
                    "verification_records": int(len(verification)),
                    "unresolved_records": int(len(unresolved)),
                    "long_session_flags": int(len(flags)),
                    "candidate_count": int(len(candidates)),
                    "output_files": [],
                    "output_folder": output_folder,
                },
                "students": records_preview(preview_students),
                "verification": records_preview(pd_frame(verification)),
                "unresolved": records_preview(pd_frame(unresolved)),
                "flags": records_preview(flags),
                "candidates": candidates,
            }
        except Exception as exc:
            return {"error": f"{exc}", "details": traceback.format_exc(limit=3)}

    def finalize_cleaning(self, decisions):
        """Apply user decisions and create final output workbooks."""
        try:
            if self.pending_records is None or not self.pending_output_folder:
                return {"error": "Import and analyze Penji files before finalizing."}
            decisions = decisions or {}
            _students, _verification, _unresolved, _changes, candidates = cleaner_engine.process_records(
                self.pending_records, decisions
            )
            pending = [item for item in candidates if item["Decision"] == "Pending"]
            if pending:
                return {"error": f"Please approve or deny all {len(pending)} proposed correction(s) before finalizing."}

            students, verification, unresolved, changes, output_files, candidates = cleaner_engine.finalize_prepared_files(
                self.pending_records,
                self.pending_long_sessions,
                self.pending_output_folder,
                decisions,
            )
            flags = self.pending_long_sessions if self.pending_long_sessions is not None else cleaner_engine.pd.DataFrame()

            def records_preview(frame, limit=500):
                if frame is None or frame.empty:
                    return []
                return json.loads(frame.head(limit).fillna("").to_json(orient="records"))

            output_folder = self.pending_output_folder
            self.pending_records = None
            self.pending_long_sessions = None
            self.pending_output_folder = None
            return {
                "success": True,
                "finalized": True,
                "summary": {
                    "unique_students": int(len(students)),
                    "verification_records": int(len(verification)),
                    "unresolved_records": int(len(unresolved)),
                    "long_session_flags": int(len(flags)),
                    "candidate_count": int(len(candidates)),
                    "output_files": [os.path.basename(path) for path in output_files],
                    "output_folder": output_folder,
                },
                "students": records_preview(students),
                "verification": records_preview(verification),
                "unresolved": records_preview(unresolved),
                "flags": records_preview(flags),
                "candidates": candidates,
            }
        except Exception as exc:
            return {"error": f"{exc}", "details": traceback.format_exc(limit=3)}

    # Retain the old API name for compatibility with any existing UI code.
    def run_cleaning(self, input_paths, output_folder):
        return self.prepare_cleaning(input_paths, output_folder)


def pd_frame(records):
    """Convert a list of records to a DataFrame for preview serialization."""
    return cleaner_engine.pd.DataFrame(records)


def main():
    api = DesktopAPI()
    window = webview.create_window(
        "ELAC Connect: Data Pipeline",
        str(HTML_PATH),
        js_api=api,
        width=1180,
        height=780,
        min_size=(900, 640),
        background_color="#f4f6f9",
    )
    api.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
