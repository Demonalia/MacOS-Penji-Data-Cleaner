# ELAC Connect — Offline Windows Desktop Project

This project keeps the ELAC Connect HTML/CSS interface and connects it to the existing Python Penji cleaner. File processing happens locally on the computer; the app does not upload student records to a server.

## What is connected

- Windows-native file picker for one or more Penji CSV/Excel exports (`.csv`, `.xlsx`, `.xls`).
- Output-folder picker.
- Existing student-ID rules: valid IDs are 9 digits and begin with `88` or `90`; when an ID is invalid/missing, the cleaner proposes recovery using a unique valid ID associated with the same email.
- Two-stage cleaning workflow: analyze records first, then approve or deny every proposed Student ID correction before final reports are generated. Denied corrections preserve the original ID and route records that remain invalid to `Unresolved_Records.xlsx`.
- Individual **Approve** / **Deny Change** actions plus **Approve All** / **Deny All** controls. Users can change a decision before finalizing.
- Data Review tabs switch between Needs Verification, Unresolved Records, and Long Sessions.
- Cleaned student totals, verification records, unresolved records, and cleaning report exports.
- Student output workbooks split into batches of up to 980 unique students.
- Long-session quality check for the detailed Penji export. Any *single* session with `Duration Minutes >= 480` is included in `Long_Session_Flags.xlsx` with the requested flag text: `Session lasting more that 8 hrs`. Separate sessions are not added together.
- Google Fonts was removed so the interface does not need the internet to load its font.

## Run the source project on Windows

1. Install Python 3.11 or newer. During installation, enable **Add Python to PATH** if the installer offers that option.
2. Extract this folder somewhere convenient, such as `Documents\ELAC_Connect_Offline_Project`.
3. Open the folder in File Explorer.
4. Double-click `run_app.bat`. On the first run, install the packages listed in `requirements.txt` if Python reports a missing module:
   ```powershell
   py -3 -m pip install -r requirements.txt
   ```
5. Use **Import Penji**, choose the file(s), choose an output folder, then click **Import & Analyze Files**.
6. On Student ID Validation, review proposed corrections. Approve or deny each one, or use the bulk controls.
7. Click **Finalize Cleaning & Export** to create the final workbooks.

## Build the Windows app

1. While connected to the internet, open the project folder in File Explorer and double-click `build_windows_exe.bat`. This installs build dependencies and packages the app.
2. When it finishes, look in `dist\ELAC_Connect\`.
3. Test `ELAC_Connect.exe` on the target Windows computer. Keep the whole `dist\ELAC_Connect` folder together when copying it; do not copy only the `.exe`.
4. After the app and its required Windows WebView2 runtime are present, the app processes files without internet access. Some Windows installations may need the WebView2 Runtime installed once before the app can launch.

## Important notes

- Test with a copy of a Penji export first and verify the outputs before using the app for official reporting.
- The detailed-format long-session flag is based on the exported `Duration Minutes` value. It does not change or delete the attendance record.
- The existing cleaner aggregates records by Student ID for the final student totals; the long-session report retains the original detailed session rows.
- The interface separates ID verification, unresolved records, and long-session flags into distinct review categories. The Student ID correction approval screen appears before final export, so no proposed email-based correction is applied until the user approves it. The original four-step Data Pipeline Overview remains on the dashboard as a guide for staff. The desktop window opens at a more compact size and can be resized.
- The review tables display up to 500 records in the interface; the complete detailed long-session records remain in the Excel report. Validate the updated interface and generated files with representative test files before official use.
