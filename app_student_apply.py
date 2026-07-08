import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Undergrad Research Application", layout="wide")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SHEET_NAME = "Research_Applications"   # Name of the Google Sheet (spreadsheet file)
WORKSHEET_NAME = "Applications"        # Name of the tab inside that spreadsheet

COLUMNS = [
    "Timestamp", "Name", "Student ID", "Current Semester", "CGPA",
    "Subject of Interest", "Prior Experience / Skills", "Decision", "Notes"
]

SEMESTER_OPTIONS = ["Spring", "Summer", "Fall"]
SUBJECT_OPTIONS = [
    "Pharmaceutics", "Pharmacology", "Pharmaceutical Chemistry",
    "Clinical Pharmacy", "Microbiology", "Biochemistry"
]
DECISION_OPTIONS = ["Pending", "Selected", "Denied"]

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


# ---------------------------------------------------------------------------
# STUDENT-FACING APPLICATION FORM
# ---------------------------------------------------------------------------
def show_application_form():
    st.title("Undergraduate Research Application")
    st.write(
        "Please fill in your details below to apply for an undergraduate "
        "research position. Applications are reviewed on a rolling basis."
    )

  with st.form("application_form", clear_on_submit=True):
        name = st.text_input("Full Name *")
        student_id = st.text_input("Student ID *")

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
            if not name or not student_id or not semester_choice or not subject_choice:
                st.error("Please fill in all required fields marked with *.")
            else:
                row = {
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Name": name,
                    "Student ID": student_id,
                    "Current Semester": semester_choice,
                    "CGPA": cgpa,
                    "Subject of Interest": subject_choice,
                    "Prior Experience / Skills": experience,
                    "Decision": "Pending",
                    "Notes": "",
                }
                append_application(row)
                st.success("Your application has been submitted successfully!")


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
    col1, col2, col3 = st.columns(3)
    with col1:
        semester_filter = st.multiselect(
            "Filter by Semester", sorted(df["Current Semester"].dropna().unique())
        )
    with col2:
        subject_filter = st.multiselect(
            "Filter by Subject", sorted(df["Subject of Interest"].dropna().unique())
        )
    with col3:
        decision_filter = st.multiselect(
            "Filter by Decision", DECISION_OPTIONS
        )

    filtered_df = df.copy()
    if semester_filter:
        filtered_df = filtered_df[filtered_df["Current Semester"].isin(semester_filter)]
    if subject_filter:
        filtered_df = filtered_df[filtered_df["Subject of Interest"].isin(subject_filter)]
    if decision_filter:
        filtered_df = filtered_df[filtered_df["Decision"].isin(decision_filter)]

    filtered_df["CGPA"] = pd.to_numeric(filtered_df["CGPA"], errors="coerce")
    filtered_df = filtered_df.sort_values("CGPA", ascending=False)

    st.caption(
        f"Showing {len(filtered_df)} of {len(df)} total applications. "
        f"Selected: {(df['Decision'] == 'Selected').sum()} / 4 target slots."
    )

    st.write("Edit the **Decision** column below, then click **Save Decisions**.")

    edited = st.data_editor(
        filtered_df,
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
        # Merge edits back into the full (unfiltered) dataset before saving
        full_df = df.set_index("Student ID")
        edits_df = edited.set_index("Student ID")
        full_df.update(edits_df)
        full_df = full_df.reset_index()[COLUMNS]
        save_all_decisions(full_df)
        st.success("Decisions saved.")
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
        show_application_form()


if __name__ == "__main__":
    main()
