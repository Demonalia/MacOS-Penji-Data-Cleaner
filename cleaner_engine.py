import os
import re
import pandas as pd

# ============================================================
# da rules I need followed 980 unique records in each file and our student ids start with 88 or 90 and must be 9 digits long
# ============================================================

MAX_STUDENTS_PER_FILE = 980

VALID_ID_RE = re.compile(r"^(88|90)\d{7}$")

# ============================================================
# Nova wanted helper functions - I didn't argue since it helps make it easier for the program to compare the data in the files
# She wanted her docstrings
# ============================================================
def normalize_column_name(value):
    """Make column names easier to compare."""
    if pd.isna(value):
        return ""

    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "", value)

    return value


def normalize_email(value):
    """Normalize email for matching."""
    if pd.isna(value):
        return ""

    return str(value).strip().lower()


def normalize_id(value):
    """
    Normalize a Student ID.

    Handles things such as:
        881234567
        '881234567'
        881234567.0
    """

    if pd.isna(value):
        return ""

    value = str(value).strip()

    # Handle Excel-style numeric values such as 881234567.0 - she doesn't trust penji's output
    if value.endswith(".0"):
        value = value[:-2]

    return value


def valid_student_id(student_id):
    """
    A valid Student ID must:
        - contain exactly 9 digits
        - begin with 88 or 90
    """

    student_id = normalize_id(student_id)

    return bool(VALID_ID_RE.fullmatch(student_id))


def clean_text(value):
    """Convert blank/NaN values to an empty string."""
    if pd.isna(value):
        return ""

    return str(value).strip()

# ============================================================
# FILE READING - okay so the user will select the file from the popup
# ============================================================

def read_input_file(file_path):
    """
    Read CSV, XLS, or XLSX.

    For Excel files, all worksheets are combined.
    """

    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".csv":
        df = pd.read_csv(file_path, dtype=str)

    elif extension in [".xlsx", ".xls"]:
        sheets = pd.read_excel(
            file_path,
            sheet_name=None,
            dtype=str
        )

        frames = []

        for sheet_name, sheet_df in sheets.items():
            if not sheet_df.empty:
                sheet_df["__source_sheet"] = sheet_name
                frames.append(sheet_df)

        if frames:
            df = pd.concat(
                frames,
                ignore_index=True
            )
        else:
            df = pd.DataFrame()

    else:
        raise ValueError(
            f"Unsupported file type: {extension}"
        )

    return df


# ============================================================
# FORMAT DETECTION - I explained to Nova that we seemed to have 2 different outputs one with 4 columns and another with 27ish so this
# is an attempt to get baby to "read"
# ============================================================

def detect_format(df):
    """
    Detect whether the file is:

        SIMPLE
        or
        DETAILED

    Returns None if neither format is recognized.
    """

    columns = {
        normalize_column_name(column)
        for column in df.columns
    }

    # --------------------------------------------------------
    # SIMPLE FORMAT - for the 4 column
    # --------------------------------------------------------

    simple_required = {
        "name",
        "studentid",
        "email",
        "totaldurationhours"
    }

    if simple_required.issubset(columns):
        return "simple"

    # --------------------------------------------------------
    # DETAILED FORMAT - for the other one. we don't need the info from the other column so its just gonna focus on those 4
    # --------------------------------------------------------

    detailed_required = {
        "studentemail",
        "studentid",
        "studentname",
        "durationminutes"
    }

    if detailed_required.issubset(columns):
        return "detailed"

    return None


# ============================================================
# STANDARDIZE INPUT
# ============================================================

def find_long_sessions(df, detected_format, source_file):
    """Return detailed Penji sessions lasting 8 hours or more (480 minutes)."""
    if detected_format != "detailed" or df.empty:
        return pd.DataFrame()

    column_map = {
        normalize_column_name(column): column
        for column in df.columns
    }
    duration_col = column_map.get("durationminutes")
    if not duration_col:
        return pd.DataFrame()

    minutes = pd.to_numeric(df[duration_col], errors="coerce")
    flagged = df.loc[minutes >= 480].copy()
    if flagged.empty:
        return pd.DataFrame()

    flagged["Source File"] = source_file
    flagged["Flag"] = "Session lasting more that 8 hrs"
    # Keep the original Duration Minutes field and all original source columns.
    return flagged


def standardize_frame(df, detected_format):
    """
    Convert either supported input format into the same
    internal structure.

    Standard columns:

        Student ID
        Student Name
        Student Email
        Duration Hours
        Source Row
    """

    # Map normalized column names back to their actual names
    column_map = {
        normalize_column_name(column): column
        for column in df.columns
    }

    output = pd.DataFrame()

    # --------------------------------------------------------
    # SIMPLE FORMAT - Basically this is how it's going to treat the simple one
    # --------------------------------------------------------

    if detected_format == "simple":

        output["Student ID"] = df[
            column_map["studentid"]
        ].apply(normalize_id)

        output["Student Name"] = df[
            column_map["name"]
        ].apply(clean_text)

        output["Student Email"] = df[
            column_map["email"]
        ].apply(normalize_email)

        output["Duration Hours"] = pd.to_numeric(
            df[column_map["totaldurationhours"]],
            errors="coerce"
        ).fillna(0)

    # --------------------------------------------------------
    # DETAILED FORMAT - this is how its going to treat the shitload of columns one
    # --------------------------------------------------------

    elif detected_format == "detailed":

        output["Student ID"] = df[
            column_map["studentid"]
        ].apply(normalize_id)

        output["Student Name"] = df[
            column_map["studentname"]
        ].apply(clean_text)

        output["Student Email"] = df[
            column_map["studentemail"]
        ].apply(normalize_email)

        duration_minutes = pd.to_numeric(
            df[column_map["durationminutes"]],
            errors="coerce"
        ).fillna(0)

        output["Duration Hours"] = (
            duration_minutes / 60
        )

    else:
        raise ValueError(
            "Unknown input format."
        )

    # Pandas row number + 2 gives us the approximate Excel row
    # because row 1 contains headers.
    output["Source Row"] = range(
        2,
        len(output) + 2
    )

    return output


# ============================================================
# BUILD EMAIL → VALID STUDENT ID LOOKUP - we're going to have it look up student ids based on the student email on the actual data file
# since it can't be connected to any database but we tend to have repeat customers 
# ============================================================

def build_email_lookup(records):
    """
    Build:

        email -> set of valid Student IDs

    Only valid Student IDs are allowed to establish a match.
    """

    email_to_ids = {}

    for _, row in records.iterrows():

        email = normalize_email(
            row["Student Email"]
        )

        student_id = normalize_id(
            row["Student ID"]
        )

        if not email:
            continue

        if not valid_student_id(student_id):
            continue

        if email not in email_to_ids:
            email_to_ids[email] = set()

        email_to_ids[email].add(student_id)

    return email_to_ids


# ============================================================
# PROCESS RECORDS - all this stuffs below is the program now handling the records
# ============================================================

def process_records(records, correction_decisions=None):
    """
    Process every attendance record.

    Returns:

        clean_records
        verification_records
        unresolved_records
        change_records
        proposed_changes
    """

    correction_decisions = correction_decisions or {}
    email_to_ids = build_email_lookup(records)

    clean_records = []
    verification_records = []
    unresolved_records = []
    change_records = []
    proposed_changes = []

    # --------------------------------------------------------
    # Process each record
    # --------------------------------------------------------

    for record_key, row in records.iterrows():

        original_id = normalize_id(
            row["Student ID"]
        )

        email = normalize_email(
            row["Student Email"]
        )

        name = clean_text(
            row["Student Name"]
        )

        duration_hours = round(float(row["Duration Hours"]), 2)

        source_row = row["Source Row"]
        source_file = row["Source File"]

        # ----------------------------------------------------
        # CASE 1: Email is associated with multiple distinct valid IDs.
        # Flag EVERY record with that email, including rows whose own
        # ID is valid, for manual verification.
        # ----------------------------------------------------

        possible_ids_for_email = email_to_ids.get(email, set()) if email else set()
        if email and len(possible_ids_for_email) > 1:
            verification_records.append({
                "Student Email": email,
                "Student Name": name,
                "Original Student ID": original_id,
                "Possible Student IDs": ", ".join(sorted(possible_ids_for_email)),
                "Duration Hours": duration_hours,
                "Source Row": source_row,
                "Source File": source_file,
                "Reason": "Email is associated with multiple valid Student IDs."
            })
            change_records.append({
                "Student Email": email,
                "Student Name": name,
                "Original Student ID": original_id,
                "Final Student ID": "",
                "Change": "Verification required",
                "Reason": "Email is associated with multiple valid Student IDs.",
                "Duration Hours": duration_hours,
                "Source Row": source_row,
                "Source File": source_file
            })
            continue

        # ----------------------------------------------------
        # CASE 2: Student ID is already valid
        # ----------------------------------------------------

        if valid_student_id(original_id):

            clean_records.append({
                "Student ID": original_id,
                "Student Name": name,
                "Student Email": email,
                "Duration Hours": duration_hours
            })

            change_records.append({
                "Student Email": email,
                "Student Name": name,
                "Original Student ID": original_id,
                "Final Student ID": original_id,
                "Change": "No change",
                "Reason": "Student ID was already valid.",
                "Duration Hours": duration_hours,
                "Source Row": source_row,
                "Source File": source_file    
            })    

            continue

        # ----------------------------------------------------
        # CASE 2:
        # Invalid/missing ID but email exists
        # ----------------------------------------------------

        if email:

            possible_ids = email_to_ids.get(
                email,
                set()
            )

            # -----------------------------------------------
            # Exactly ONE valid ID found - i need to figure out what hell she's talking about here
            # -----------------------------------------------

            if len(possible_ids) == 1:

                repaired_id = next(iter(possible_ids))
                decision = str(correction_decisions.get(str(record_key), "")).lower()
                candidate = {
                    "Record Key": str(record_key),
                    "Student Name": name,
                    "Student Email": email,
                    "Original Student ID": original_id or "(Blank)",
                    "Proposed Student ID": repaired_id,
                    "Reason": "Matched to one valid Student ID using email.",
                    "Source Row": int(source_row) if pd.notna(source_row) else "",
                    "Decision": "Approved" if decision == "approved" else "Denied" if decision == "denied" else "Pending"
                }
                proposed_changes.append(candidate)

                if decision == "approved":
                    clean_records.append({
                        "Student ID": repaired_id,
                        "Student Name": name,
                        "Student Email": email,
                        "Duration Hours": duration_hours
                    })
                    change_records.append({
                        "Student Email": email,
                        "Student Name": name,
                        "Original Student ID": original_id,
                        "Final Student ID": repaired_id,
                        "Change": "Student ID recovered (approved)",
                        "Reason": "Matched to one valid Student ID using email; correction approved.",
                        "Duration Hours": duration_hours,
                        "Source Row": source_row,
                        "Source File": source_file
                    })
                elif decision == "denied":
                    reason = "Proposed Student ID correction was denied; original Student ID was preserved."
                    unresolved_records.append({
                        "Student Email": email,
                        "Student Name": name,
                        "Original Student ID": original_id,
                        "Possible Student IDs": repaired_id,
                        "Duration Hours": duration_hours,
                        "Source Row": source_row,
                        "Source File": source_file,
                        "Reason": reason
                    })
                    change_records.append({
                        "Student Email": email,
                        "Student Name": name,
                        "Original Student ID": original_id,
                        "Final Student ID": original_id,
                        "Change": "Correction denied; original preserved",
                        "Reason": reason,
                        "Duration Hours": duration_hours,
                        "Source Row": source_row,
                        "Source File": source_file
                    })
                # Pending candidates are intentionally excluded from cleaned
                # and unresolved outputs until the user makes a decision.
                continue

            # -----------------------------------------------
            # Multiple valid IDs found - same here
            # -----------------------------------------------

            if len(possible_ids) > 1:

                verification_records.append({
                    "Student Email": email,
                    "Student Name": name,
                    "Original Student ID": original_id,
                    "Possible Student IDs": ", ".join(
                        sorted(possible_ids)
                    ),
                    "Duration Hours": duration_hours,
                    "Source Row": source_row,
                    "Source File": source_file,
                    "Reason": (
                        "Email is associated with multiple "
                        "valid Student IDs."
                    )
                })

                change_records.append({
                    "Student Email": email,
                    "Student Name": name,
                    "Original Student ID": original_id,
                    "Final Student ID": "",
                    "Change": "Verification required",
                    "Reason": (
                        "Email is associated with multiple "
                        "valid Student IDs."
                    ),
                    "Duration Hours": duration_hours,
                    "Source Row": source_row,
                    "Source File": source_file
                })

                continue

        # ----------------------------------------------------
        # CASE 3:
        # No valid ID can be established
        # ----------------------------------------------------

        if not original_id:

            reason = (
                "Student ID is missing and could not "
                "be recovered using email."
            )

        elif not original_id.isdigit():

            reason = (
                "Student ID is not numeric and could "
                "not be recovered using email."
            )

        elif len(original_id) != 9:

            reason = (
                "Student ID is more than or less than "
                "9 digits and could not be recovered "
                "using email."
            )

        elif not (
            original_id.startswith("88")
            or original_id.startswith("90")
        ):

            reason = (
                "Student ID does not begin with 88 or 90 "
                "and could not be recovered using email."
            )

        else:

            reason = (
                "Student ID could not be validated."
            )

        unresolved_records.append({
            "Student Email": email,
            "Student Name": name,
            "Original Student ID": original_id,
            "Possible Student IDs": "",
            "Duration Hours": duration_hours,
            "Source Row": source_row,
            "Source File": source_file,
            "Reason": reason
        })

        change_records.append({
            "Student Email": email,
            "Student Name": name,
            "Original Student ID": original_id,
            "Final Student ID": "",
            "Change": "Unresolved",
            "Reason": reason,
            "Duration Hours": duration_hours,
            "Source Row": source_row,
            "Source File": source_file
        })

    return (
        clean_records,
        verification_records,
        unresolved_records,
        change_records,
        proposed_changes
    )


# ============================================================
# AGGREGATE CLEAN STUDENTS - lol just the implication that the other students are unclean uncleeeaaannn!
# ============================================================

def aggregate_students(clean_records):
    """
    Combine all records belonging to the same Student ID.

    One student = one row.
    """

    if not clean_records:
        return pd.DataFrame(
            columns=[
                "Student ID",
                "Student Name",
                "Student Email",
                "Total Duration Hours"
            ]
        )

    df = pd.DataFrame(clean_records)

    # --------------------------------------------------------
    # Aggregate hours by Student ID
    # --------------------------------------------------------

    grouped = (
        df.groupby("Student ID", as_index=False)
        .agg({
            "Student Name": "first",
            "Student Email": "first",
            "Duration Hours": "sum"
        })
    )

    grouped = grouped.rename(
        columns={
            "Duration Hours":
                "Total Duration Hours"
        }
    )

    # Keep reported hours to a maximum of two decimal places.
    grouped["Total Duration Hours"] = (
        grouped["Total Duration Hours"]
        .round(2)
    )

    return grouped


# ============================================================
# EXCEL FORMATTING
# ============================================================

def format_excel(writer, sheet_name):
    """
    Basic Excel usability formatting.
    """

    worksheet = writer.sheets[sheet_name]

    # Freeze header row
    worksheet.freeze_panes = "A2"

    # Enable filters
    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )

    # Adjust column widths
    for column_cells in worksheet.columns:

        max_length = 0

        column_letter = column_cells[0].column_letter

        for cell in column_cells:

            if cell.value is not None:

                max_length = max(
                    max_length,
                    len(str(cell.value))
                )

        worksheet.column_dimensions[
            column_letter
        ].width = min(
            max_length + 2,
            50
        )


# ============================================================
# EXPORT - thing that spits out our cleaned files, log of changes made, things it can't find, the other one lol 
# ============================================================

def export_results(
    students_df,
    verification_df,
    unresolved_df,
    change_df,
    output_folder
):
    """
    Export:

        Students_001.xlsx
        Students_002.xlsx
        ...

        Verification_Records.xlsx
        Unresolved_Records.xlsx
    """

    output_files = []

    # --------------------------------------------------------
    # CLEAN STUDENT FILES
    # --------------------------------------------------------

    if not students_df.empty:

        total_students = len(students_df)

        file_number = 1

        for start in range(
            0,
            total_students,
            MAX_STUDENTS_PER_FILE
        ):

            end = start + MAX_STUDENTS_PER_FILE

            chunk = students_df.iloc[
                start:end
            ]

            filename = (
                f"Students_{file_number:03d}.xlsx"
            )

            path = os.path.join(
                output_folder,
                filename
            )

            with pd.ExcelWriter(
                path,
                engine="openpyxl"
            ) as writer:

                chunk.to_excel(
                    writer,
                    index=False,
                    sheet_name="Students"
                )

                format_excel(
                    writer,
                    "Students"
                )

            output_files.append(path)

            file_number += 1

    # --------------------------------------------------------
    # VERIFICATION FILE
    # --------------------------------------------------------

    if not verification_df.empty:

        path = os.path.join(
            output_folder,
            "Verification_Records.xlsx"
        )

        with pd.ExcelWriter(
            path,
            engine="openpyxl"
        ) as writer:

            verification_df.to_excel(
                writer,
                index=False,
                sheet_name="Verification"
            )

            format_excel(
                writer,
                "Verification"
            )

        output_files.append(path)

    # --------------------------------------------------------
    # UNRESOLVED FILE
    # --------------------------------------------------------

    if not unresolved_df.empty:

        path = os.path.join(
            output_folder,
            "Unresolved_Records.xlsx"
        )

        with pd.ExcelWriter(
            path,
            engine="openpyxl"
        ) as writer:

            unresolved_df.to_excel(
                writer,
                index=False,
                sheet_name="Unresolved"
            )

            format_excel(
                writer,
                "Unresolved"
            )

        output_files.append(path)

    # --------------------------------------------------------
    # CLEANING REPORT
    # --------------------------------------------------------

    if not change_df.empty:

        path = os.path.join(
            output_folder,
            "Cleaning_Report.xlsx"
        )

        with pd.ExcelWriter(
            path,
            engine="openpyxl"
        ) as writer:

            change_df.to_excel(
                writer,
                index=False,
                sheet_name="Changes"
            )

            format_excel(
                writer,
                "Changes"
            )

        output_files.append(path)

    return output_files


# ============================================================
# MAIN CLEANING FUNCTION
# ============================================================

def prepare_files(file_paths):
    """Read and standardize input files without exporting final results."""
    all_records = []
    long_session_frames = []

    for file_path in file_paths:
        print(f"Reading: {os.path.basename(file_path)}")
        df = read_input_file(file_path)
        if df.empty:
            print("  File is empty.")
            continue

        detected_format = detect_format(df)
        if detected_format is None:
            raise ValueError(
                f"Could not recognize the format of:\n{os.path.basename(file_path)}"
            )

        long_sessions = find_long_sessions(df, detected_format, os.path.basename(file_path))
        if not long_sessions.empty:
            long_session_frames.append(long_sessions)

        standardized = standardize_frame(df, detected_format)
        standardized["Source File"] = os.path.basename(file_path)
        all_records.append(standardized)

    if not all_records:
        raise ValueError("No usable records were found.")

    records = pd.concat(all_records, ignore_index=True).reset_index(drop=True)
    long_sessions_df = pd.concat(long_session_frames, ignore_index=True) if long_session_frames else pd.DataFrame()
    return records, long_sessions_df


def finalize_prepared_files(records, long_sessions_df, output_folder, correction_decisions):
    """Apply explicit correction decisions, then generate the final Excel reports."""
    clean_records, verification_records, unresolved_records, change_records, proposed_changes = process_records(
        records, correction_decisions
    )

    pending = [item for item in proposed_changes if item["Decision"] == "Pending"]
    if pending:
        raise ValueError(f"{len(pending)} proposed Student ID correction(s) still need an Approve or Deny Change decision.")

    students_df = aggregate_students(clean_records)
    verification_df = pd.DataFrame(verification_records)
    unresolved_df = pd.DataFrame(unresolved_records)
    change_df = pd.DataFrame(change_records)

    output_files = export_results(
        students_df, verification_df, unresolved_df, change_df, output_folder
    )

    flag_path = os.path.join(output_folder, "Long_Session_Flags.xlsx")
    if long_sessions_df is not None and not long_sessions_df.empty:
        with pd.ExcelWriter(flag_path, engine="openpyxl") as writer:
            long_sessions_df.to_excel(writer, index=False, sheet_name="Long Sessions")
            format_excel(writer, "Long Sessions")
        output_files.append(flag_path)
    elif os.path.exists(flag_path):
        os.remove(flag_path)

    return students_df, verification_df, unresolved_df, change_df, output_files, proposed_changes


def clean_files(file_paths, output_folder):
    """Backward-compatible batch cleaner; approves unique email recoveries."""
    records, long_sessions_df = prepare_files(file_paths)
    _, _, _, _, candidates = process_records(records, {})
    decisions = {item["Record Key"]: "approved" for item in candidates}
    students_df, verification_df, unresolved_df, _change_df, output_files, _ = finalize_prepared_files(
        records, long_sessions_df, output_folder, decisions
    )
    return students_df, verification_df, unresolved_df, output_files
