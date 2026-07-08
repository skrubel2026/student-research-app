import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText

st.set_page_config(page_title="Undergraduate and Graduate Research Application", layout="wide")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SHEET_NAME = "Research_Applications"   # Name of the Google Sheet (spreadsheet file)
WORKSHEET_NAME = "Applications"        # Name of the tab inside that spreadsheet

COLUMNS = [
    "Timestamp", "Name", "Student ID", "Email", "Current Semester", "CGPA",
    "Program", "Credit Hours Completed", "Target Semester",
    "Subject of Interest", "Prior Experience / Skills", "Decision", "Notes"
]

SEMESTER_OPTIONS = ["Spring", "Summer", "Fall"]
SUBJECT_OPTIONS = [
    "Pharmaceutics", "Pharmacology", "Pharmaceutical Chemistry",
    "Clinical Pharmacy", "Microbiology", "Biochemistry"
]
PROGRAM_OPTIONS = ["BPharm", "MPharm"]
DECISION_OPTIONS = ["Pending", "Selected", "Denied"]

# ---------------------------------------------------------------------------
# EMAIL NOTIFICATIONS
# ---------------------------------------------------------------------------
SENDER_DISPLAY_NAME = "Dr. Ferdous Khan"
SIGNATURE = (
    "Dr. Ferdous Khan\n"
    "Associate Professor\n"
    "Department of Pharmaceutical Sciences"
)


def send_email(to_email, subject, body):
    """Sends an email via Yahoo Mail SMTP using credentials stored in secrets.
    Fails silently (returns False) rather than crashing the app, since a
    student's submission or a supervisor's save shouldn't be blocked by an
    email hiccup."""
    try:
        sender_email = st.secrets["sender_email"]
        sender_app_password = st.secrets["sender_app_password"]

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = f"{SENDER_DISPLAY_NAME} <{sender_email}>"
        msg["To"] = to_email

        with smtplib.SMTP("smtp.mail.yahoo.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_app_password)
            server.sendmail(sender_email, [to_email], msg.as_string())
        return True
    except Exception:
        return False


def send_confirmation_email(row_dict):
    subject = "Application Received — Undergraduate and Graduate Research Position"
    body = (
        f"Dear {row_dict['Name']},\n\n"
        "Thank you for applying for the undergraduate/graduate research position. "
        "We have received your application and it will be reviewed shortly.\n\n"
        "You will receive another email once a decision has been made.\n\n"
        f"Regards,\n{SIGNATURE}"
    )
    send_email(row_dict["Email"], subject, body)


def send_decision_email(name, email, decision):
    if decision == "Selected":
        subject = "Research Application — You Have Been Selected"
        body = (
            f"Dear {name},\n\n"
            "Congratulations! You have been selected for the undergraduate/graduate "
            "research position. Further details will follow shortly.\n\n"
            f"Regards,\n{SIGNATURE}"
        )
    elif decision == "Denied":
        subject = "Research Application — Update on Your Application"
        body = (
            f"Dear {name},\n\n"
            "Thank you for your interest in the undergraduate/graduate research position. "
            "After careful review, we are unable to offer you a place this semester. "
            "We encourage you to apply again in a future semester.\n\n"
            f"Regards,\n{SIGNATURE}"
        )
    else:
        return False
    return send_email(email, subject, body)


# ---------------------------------------------------------------------------
# GOOGLE SHEETS CONNECTION
# ---------------------------------------------------------------------------
@st.cache_resource
def get_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def get_worksheet():
    client = get_client()
    sh = client.open(SHEET_NAME)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=len(COLUMNS))
        ws.append_row(COLUMNS)
    return ws


def load_applications():
    ws = get_worksheet()
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=COLUMNS)
    return df


def append_application(row_dict):
    ws = get_worksheet()
    ws.append_row([row_dict.get(col, "") for col in COLUMNS])


def save_all_decisions(edited_df):
    ws = get_worksheet()
    # Rewrite the full sheet (simple + safe for the expected data sizes here)
    values = [COLUMNS] + edited_df[COLUMNS].astype(str).values.tolist()
    ws.clear()
    ws.update(values)


def find_application(student_id, email):
    """Looks up a single application by Student ID. If the stored record
    already has an email on file, the given email must also match it (for
    verification). If the stored record has no email yet (legacy
    submissions from before the Email field existed), Student ID alone is
    enough to find it, and the student can add their email during the edit.
    Returns (row_as_dict, matched) or (None, None) if not found / mismatched."""
    df = load_applications()
    if df.empty:
        return None, None
    id_match = df[df["Student ID"].astype(str).str.strip() == str(student_id).strip()]
    if id_match.empty:
        return None, None
    row = id_match.iloc[0]
    stored_email = str(row.get("Email", "")).strip()
    if stored_email:
        if stored_email.lower() != str(email).strip().lower():
            return None, None
    return row.to_dict(), id_match.index[0]


def update_application(student_id, updated_fields):
    """Updates an existing application's editable fields in place, keyed by
    Student ID. Keeps Decision, Notes, and the original Timestamp untouched
    unless explicitly included in updated_fields."""
    df = load_applications()
    match_mask = df["Student ID"].astype(str).str.strip() == str(student_id).strip()
    if not match_mask.any():
        return False
    idx = df.index[match_mask][0]
    for col, val in updated_fields.items():
        df.at[idx, col] = val
    save_all_decisions(df)
    return True


# ---------------------------------------------------------------------------
# STUDENT-FACING APPLICATION FORM
# ---------------------------------------------------------------------------
def show_student_portal():
    st.title("Undergraduate and Graduate Research Application")
    tab_new, tab_edit = st.tabs(["Submit New Application", "Edit My Application"])
    with tab_new:
        show_new_application_form()
    with tab_edit:
        show_edit_application_form()


def show_new_application_form():
    st.write(
        "Please fill in your details below to apply for an undergraduate or "
        "graduate research position. Applications are reviewed on a rolling basis."
    )

    with st.form("application_form", clear_on_submit=True):
        name = st.text_input("Full Name *")
        student_id = st.text_input("Student ID *")
        email = st.text_input("Email Address *", placeholder="you@example.com")

        col_sem, col_year = st.columns(2)
        with col_sem:
            semester_term = st.selectbox(
                "Semester Term *", SEMESTER_OPTIONS + ["➕ Type a new value"]
            )
            if semester_term == "➕ Type a new value":
                semester_term = st.text_input("Enter semester term")
        with col_year:
            this_year = datetime.now().year
            year_choice = st.selectbox("Year *", [this_year, this_year + 1])
        semester_choice = f"{semester_term} {year_choice}"

        cgpa = st.number_input(
            "CGPA *", min_value=0.0, max_value=4.0, step=0.01, format="%.2f"
        )

        col_prog, col_credit = st.columns(2)
        with col_prog:
            program_choice = st.selectbox(
                "Program *", PROGRAM_OPTIONS + ["➕ Type a new value"]
            )
            if program_choice == "➕ Type a new value":
                program_choice = st.text_input("Enter your program")
        with col_credit:
            credit_hours = st.number_input(
                "Credit Hours Completed *", min_value=0, max_value=300, step=1
            )

        col_target_sem, col_target_year = st.columns(2)
        with col_target_sem:
            target_term = st.selectbox(
                "Target Semester Term *", SEMESTER_OPTIONS + ["➕ Type a new value"]
            )
            if target_term == "➕ Type a new value":
                target_term = st.text_input("Enter target semester term")
        with col_target_year:
            target_year_choice = st.selectbox(
                "Target Year *", [this_year, this_year + 1]
            )
        target_semester = f"{target_term} {target_year_choice}"

        subject_choice = st.selectbox(
            "Subject of Interest *", SUBJECT_OPTIONS + ["➕ Type a new value"]
        )
        if subject_choice == "➕ Type a new value":
            subject_choice = st.text_input("Enter your subject of interest")

        experience = st.text_area(
            "Prior Research Experience / Relevant Skills",
            placeholder="e.g., lab techniques, software (Excel, SPSS), coursework, prior projects...",
        )

        submitted = st.form_submit_button("Submit Application")

        if submitted:
            if (not name or not student_id or not email or not semester_choice
                    or not subject_choice or not program_choice or not target_term):
                st.error("Please fill in all required fields marked with *.")
            elif "@" not in email or "." not in email:
                st.error("Please enter a valid email address.")
            else:
                row = {
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Name": name,
                    "Student ID": student_id,
                    "Email": email,
                    "Current Semester": semester_choice,
                    "CGPA": cgpa,
                    "Program": program_choice,
                    "Credit Hours Completed": credit_hours,
                    "Target Semester": target_semester,
                    "Subject of Interest": subject_choice,
                    "Prior Experience / Skills": experience,
                    "Decision": "Pending",
                    "Notes": "",
                }
                append_application(row)
                send_confirmation_email(row)
                st.success("Your application has been submitted successfully! A confirmation email has been sent.")


def show_edit_application_form():
    st.write(
        "If you already submitted an application and need to correct a "
        "mistake, verify your identity below to load and update it."
    )

    if "edit_loaded_row" not in st.session_state:
        st.session_state.edit_loaded_row = None
        st.session_state.edit_loaded_id = None
        st.session_state.edit_loaded_email = None

    with st.form("lookup_form"):
        lookup_id = st.text_input("Student ID")
        lookup_email = st.text_input(
            "Email Address",
            help="If you didn't provide an email when you first applied, you can leave this blank — you'll be able to add it below.",
        )
        find_clicked = st.form_submit_button("Find My Application")

    if find_clicked:
        found_row, _ = find_application(lookup_id, lookup_email)
        if found_row is None:
            st.error("No application found with that Student ID and Email combination.")
            st.session_state.edit_loaded_row = None
        else:
            st.session_state.edit_loaded_row = found_row
            st.session_state.edit_loaded_id = lookup_id
            st.session_state.edit_loaded_email = lookup_email

    row = st.session_state.edit_loaded_row
    if row is None:
        return

    st.success(f"Application found for {row['Name']}. Update any fields below.")
    if row.get("Decision") and row["Decision"] != "Pending":
        st.info(
            f"Note: a decision has already been recorded for this application "
            f"(current status: {row['Decision']}). Editing details will not change that status."
        )

    with st.form("edit_form"):
        name = st.text_input("Full Name *", value=row.get("Name", ""))
        email = st.text_input(
            "Email Address *",
            value=row.get("Email", ""),
            placeholder="you@example.com",
            help="Add this if it wasn't captured when you first applied — it's needed so you can receive updates.",
        )

        col_sem, col_year = st.columns(2)
        with col_sem:
            existing_term = str(row.get("Current Semester", "")).split(" ")[0]
            term_options = SEMESTER_OPTIONS + ["➕ Type a new value"]
            default_idx = term_options.index(existing_term) if existing_term in term_options else len(term_options) - 1
            semester_term = st.selectbox("Semester Term *", term_options, index=default_idx, key="edit_sem_term")
            if semester_term == "➕ Type a new value":
                semester_term = st.text_input("Enter semester term", key="edit_sem_term_custom")
        with col_year:
            this_year = datetime.now().year
            existing_year_parts = str(row.get("Current Semester", "")).split(" ")
            existing_year = int(existing_year_parts[1]) if len(existing_year_parts) > 1 and existing_year_parts[1].isdigit() else this_year
            year_options = [this_year, this_year + 1]
            year_choice = st.selectbox(
                "Year *", year_options,
                index=year_options.index(existing_year) if existing_year in year_options else 0,
                key="edit_sem_year",
            )
        semester_choice = f"{semester_term} {year_choice}"

        cgpa = st.number_input(
            "CGPA *", min_value=0.0, max_value=4.0, step=0.01, format="%.2f",
            value=float(row.get("CGPA", 0.0) or 0.0),
        )

        col_prog, col_credit = st.columns(2)
        with col_prog:
            prog_options = PROGRAM_OPTIONS + ["➕ Type a new value"]
            existing_prog = row.get("Program", "")
            default_prog_idx = prog_options.index(existing_prog) if existing_prog in prog_options else len(prog_options) - 1
            program_choice = st.selectbox("Program *", prog_options, index=default_prog_idx, key="edit_program")
            if program_choice == "➕ Type a new value":
                program_choice = st.text_input("Enter your program", key="edit_program_custom")
        with col_credit:
            credit_hours = st.number_input(
                "Credit Hours Completed *", min_value=0, max_value=300, step=1,
                value=int(row.get("Credit Hours Completed", 0) or 0),
            )

        col_target_sem, col_target_year = st.columns(2)
        with col_target_sem:
            existing_target_term = str(row.get("Target Semester", "")).split(" ")[0]
            target_term_options = SEMESTER_OPTIONS + ["➕ Type a new value"]
            default_target_idx = (
                target_term_options.index(existing_target_term)
                if existing_target_term in target_term_options else len(target_term_options) - 1
            )
            target_term = st.selectbox(
                "Target Semester Term *", target_term_options, index=default_target_idx, key="edit_target_term"
            )
            if target_term == "➕ Type a new value":
                target_term = st.text_input("Enter target semester term", key="edit_target_term_custom")
        with col_target_year:
            existing_target_parts = str(row.get("Target Semester", "")).split(" ")
            existing_target_year = (
                int(existing_target_parts[1])
                if len(existing_target_parts) > 1 and existing_target_parts[1].isdigit() else this_year
            )
            target_year_choice = st.selectbox(
                "Target Year *", year_options,
                index=year_options.index(existing_target_year) if existing_target_year in year_options else 0,
                key="edit_target_year",
            )
        target_semester = f"{target_term} {target_year_choice}"

        subj_options = SUBJECT_OPTIONS + ["➕ Type a new value"]
        existing_subject = row.get("Subject of Interest", "")
        default_subj_idx = subj_options.index(existing_subject) if existing_subject in subj_options else len(subj_options) - 1
        subject_choice = st.selectbox("Subject of Interest *", subj_options, index=default_subj_idx, key="edit_subject")
        if subject_choice == "➕ Type a new value":
            subject_choice = st.text_input("Enter your subject of interest", key="edit_subject_custom")

        experience = st.text_area(
            "Prior Research Experience / Relevant Skills",
            value=row.get("Prior Experience / Skills", ""),
        )

        update_clicked = st.form_submit_button("Update Application")

        if update_clicked:
            if not name or not email or not semester_choice or not subject_choice or not program_choice or not target_term:
                st.error("Please fill in all required fields marked with *.")
            elif "@" not in email or "." not in email:
                st.error("Please enter a valid email address.")
            else:
                updated_fields = {
                    "Name": name,
                    "Email": email,
                    "Current Semester": semester_choice,
                    "CGPA": cgpa,
                    "Program": program_choice,
                    "Credit Hours Completed": credit_hours,
                    "Target Semester": target_semester,
                    "Subject of Interest": subject_choice,
                    "Prior Experience / Skills": experience,
                }
                success = update_application(
                    st.session_state.edit_loaded_id,
                    updated_fields,
                )
                if success:
                    st.success("Your application has been updated successfully!")
                    st.session_state.edit_loaded_row = None
                else:
                    st.error("Could not find your application to update. Please try again.")


# ---------------------------------------------------------------------------
# SUPERVISOR-FACING SCREENING DASHBOARD
# ---------------------------------------------------------------------------
def show_admin_dashboard():
    st.title("Research Application — Screening Dashboard")

    df = load_applications()

    if df.empty:
        st.info("No applications submitted yet.")
        return

    # --- Filters ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        semester_filter = st.multiselect(
            "Filter by Semester", sorted(df["Current Semester"].dropna().unique())
        )
    with col2:
        subject_filter = st.multiselect(
            "Filter by Subject", sorted(df["Subject of Interest"].dropna().unique())
        )
    with col3:
        program_filter = st.multiselect(
            "Filter by Program", sorted(df["Program"].dropna().unique())
        )
    with col4:
        decision_filter = st.multiselect(
            "Filter by Decision", DECISION_OPTIONS
        )

    filtered_df = df.copy()
    if semester_filter:
        filtered_df = filtered_df[filtered_df["Current Semester"].isin(semester_filter)]
    if subject_filter:
        filtered_df = filtered_df[filtered_df["Subject of Interest"].isin(subject_filter)]
    if program_filter:
        filtered_df = filtered_df[filtered_df["Program"].isin(program_filter)]
    if decision_filter:
        filtered_df = filtered_df[filtered_df["Decision"].isin(decision_filter)]

    filtered_df["CGPA"] = pd.to_numeric(filtered_df["CGPA"], errors="coerce")
    filtered_df = filtered_df.sort_values("CGPA", ascending=False)

    st.caption(
        f"Showing {len(filtered_df)} of {len(df)} total applications. "
        f"Selected: {(df['Decision'] == 'Selected').sum()} / 4 target slots."
    )

    # --- Color-coded read-only overview (Green = Selected, Red = Denied, Yellow = Pending) ---
    def _decision_color(val):
        if val == "Selected":
            return "background-color: #1e7e34; color: white"
        elif val == "Denied":
            return "background-color: #b02a37; color: white"
        elif val == "Pending":
            return "background-color: #cc9a06; color: white"
        return ""

    overview_cols = ["Name", "Student ID", "Decision", "CGPA", "Program",
                      "Current Semester", "Target Semester", "Subject of Interest"]
    try:
        styled_overview = filtered_df[overview_cols].style.map(
            _decision_color, subset=["Decision"]
        )
    except AttributeError:
        # Older pandas versions only have the (deprecated) applymap method
        styled_overview = filtered_df[overview_cols].style.applymap(
            _decision_color, subset=["Decision"]
        )
    st.dataframe(styled_overview, use_container_width=True, hide_index=True)

    st.write("Edit the **Decision** column below, then click **Save Decisions**.")

    # Name is placed right next to Decision so it never scrolls out of view
    # while you're changing decisions.
    editor_column_order = [
        "Name", "Decision", "Student ID", "Email", "CGPA", "Program",
        "Current Semester", "Target Semester", "Subject of Interest",
        "Credit Hours Completed", "Prior Experience / Skills", "Timestamp", "Notes",
    ]

    edited = st.data_editor(
        filtered_df,
        column_order=editor_column_order,
        column_config={
            "Decision": st.column_config.SelectboxColumn(
                "Decision", options=DECISION_OPTIONS, required=True
            ),
        },
        disabled=[c for c in COLUMNS if c != "Decision" and c != "Notes"],
        use_container_width=True,
        hide_index=True,
        key="editor",
    )

    if st.button("Save Decisions", type="primary"):
        # Use the DataFrame's own row index (not Student ID) to match edited
        # rows back to the original data — this stays correct even if two
        # rows happen to share the same Student ID.
        changed_rows = []
        for idx in edited.index:
            old_decision = df.loc[idx, "Decision"] if idx in df.index else None
            new_decision = edited.loc[idx, "Decision"]
            if old_decision != new_decision and new_decision in ("Selected", "Denied"):
                changed_rows.append({
                    "name": edited.loc[idx, "Name"],
                    "email": edited.loc[idx, "Email"],
                    "decision": new_decision,
                })

        full_df = df.copy()
        full_df.update(edited)
        save_all_decisions(full_df[COLUMNS])

        sent_count = 0
        for r in changed_rows:
            if send_decision_email(r["name"], r["email"], r["decision"]):
                sent_count += 1

        st.success(
            f"Decisions saved. {sent_count} notification email(s) sent."
            if changed_rows else "Decisions saved."
        )
        st.rerun()

    st.divider()
    st.download_button(
        "Download all applications as CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="applications.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# ROUTING: decide whether to show the form or the admin dashboard
# ---------------------------------------------------------------------------
def main():
    query_params = st.query_params
    admin_key_provided = query_params.get("key", "")
    real_admin_key = st.secrets.get("admin_key", "")

    if real_admin_key and admin_key_provided == real_admin_key:
        show_admin_dashboard()
    else:
        show_student_portal()


if __name__ == "__main__":
    main()
