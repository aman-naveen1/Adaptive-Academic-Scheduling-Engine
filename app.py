import streamlit as st
from datetime import date

from aase import (
    analyze_calendar_impact,
    optimize_with_calendar,
    robustness_report,
    simulate_disruption,
)
from calendar_parser import calendar_summary, parse_academic_calendar
from engine import load_demo_data, parse_timetable_pdf, repair_schedule
from optimizer import optimize_timetable, optimize_whole_timetable

st.set_page_config(page_title="AASE", page_icon="🧠", layout="wide")
st.title("🧠 AASE — Adaptive Academic Scheduling Engine")
st.caption("OCR + constraint optimization + academic-calendar intelligence + disruption simulation.")

with st.sidebar:
    st.header("Timetable inputs")
    demo = st.checkbox("Use demo timetable", value=True)
    student_id = st.text_input("Student / Group", "BSc-CS-3A")
    teacher_filter = st.text_input("Teacher absent", "Dr. Sharma")
    ocr_mode = st.checkbox("OCR scanned PDFs", value=True, disabled=demo)
    uploaded = st.file_uploader(
        "Upload timetable PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    st.header("Academic calendar")
    calendar_file = st.file_uploader(
        "Upload academic calendar",
        type=["pdf", "csv", "xlsx"],
        help="AASE parses dated holidays, restricted holidays and academic events.",
    )
    restricted_as_holiday = st.checkbox(
        "Treat restricted holidays as blocked",
        value=False,
        help="Leave off when your institution permits classes on restricted holidays.",
    )
    semester_start = st.date_input("Semester start", value=date(2026, 7, 1))
    semester_end = st.date_input("Semester end", value=date(2026, 11, 30))

if demo:
    data = load_demo_data()
    ocr_warnings = []
else:
    data = {"classes": [], "teachers": [], "rooms": [], "students": []}
    ocr_warnings = []
    for f in uploaded or []:
        try:
            classes = parse_timetable_pdf(
                f, use_ocr=ocr_mode, default_group=student_id
            )
            data["classes"].extend(classes)
            if ocr_mode:
                low_conf = sum(
                    1 for row in classes if row.get("ocr_confidence", 100) < 55
                )
                if low_conf:
                    ocr_warnings.append(
                        f"{f.name}: {low_conf} extracted row(s) have low OCR confidence."
                    )
        except Exception as exc:
            st.error(f"Could not process {f.name}: {exc}")

    teacher_names = sorted(
        {x["teacher"] for x in data["classes"] if x["teacher"] != "UNKNOWN"}
    )
    room_names = sorted(
        {x["room"] for x in data["classes"] if x["room"] != "UNKNOWN"}
    )
    data["teachers"] = [
        {
            "name": t,
            "qualified_courses": sorted(
                {x["course"] for x in data["classes"] if x["teacher"] == t}
            ),
            "available_slots": {},
        }
        for t in teacher_names
    ]
    data["rooms"] = [{"name": r, "capacity": 60} for r in room_names]
    data["students"] = [{"id": student_id, "size": 0}]

calendar_events = []
calendar_warnings = []
if calendar_file:
    try:
        calendar_events, calendar_warnings = parse_academic_calendar(calendar_file)
    except Exception as exc:
        st.error(f"Could not process academic calendar: {exc}")

st.subheader("Current timetable")
if data["classes"]:
    st.dataframe(data["classes"], use_container_width=True)
else:
    st.info("Upload one or more timetable PDFs or enable demo data.")

if ocr_warnings:
    st.subheader("OCR review")
    for warning in ocr_warnings:
        st.warning(warning)

if calendar_warnings:
    for warning in calendar_warnings:
        st.warning(warning)

if calendar_events:
    st.subheader("Academic calendar")
    summary = calendar_summary(
        calendar_events,
        semester_start,
        semester_end,
        restricted_as_holiday,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calendar events", summary["events"])
    c2.metric("Holiday dates", summary["holiday_days"])
    c3.metric("Restricted holidays", summary["restricted_holiday_days"])
    c4.metric("Teaching weekdays", summary["teaching_days"])

    st.dataframe(calendar_events, use_container_width=True)

    impact = analyze_calendar_impact(
        data,
        calendar_events,
        restricted_as_holiday,
        weeks=16,
        semester_start=semester_start,
        semester_end=semester_end,
    )
    if impact["impacted_sessions"]:
        st.info(
            f"Calendar impact estimate: {impact['estimated_lost_sessions']} recurring "
            "class occurrences are exposed to blocked dates under the current weekly timetable."
        )
        st.dataframe(impact["impacted_sessions"], use_container_width=True)

if data["teachers"]:
    st.subheader("Teacher metadata")
    st.dataframe(data["teachers"], use_container_width=True)

st.subheader("AASE operation")
solver_mode = st.selectbox(
    "Choose operation",
    [
        "Calendar-aware optimization",
        "Optimize whole timetable",
        "Simulate disruption",
        "Robustness analysis",
        "Repair one disruption",
        "Heuristic repair",
    ],
)

if solver_mode == "Simulate disruption":
    disruption_type = st.radio(
        "Failure type", ["Teacher unavailable", "Room unavailable"], horizontal=True
    )
    if disruption_type == "Teacher unavailable":
        targets = sorted({x["teacher"] for x in data["classes"] if x.get("teacher")})
    else:
        targets = sorted({x["room"] for x in data["classes"] if x.get("room")})
    target_name = st.selectbox("Resource to remove", targets or ["No resources found"])

elif solver_mode in {"Repair one disruption", "Heuristic repair"}:
    col1, col2 = st.columns(2)
    with col1:
        absent_day = st.selectbox(
            "Disruption day",
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        )
    with col2:
        absent_slot = st.selectbox(
            "Disruption slot",
            [
                "09:00-10:00",
                "10:00-11:00",
                "11:15-12:15",
                "12:15-13:15",
                "14:00-15:00",
                "15:00-16:00",
            ],
        )

if st.button("Run AASE", type="primary"):
    if solver_mode != "Robustness analysis":
        st.session_state.pop("robustness", None)

    if not data["classes"]:
        st.warning("No timetable rows were extracted.")
    elif solver_mode == "Calendar-aware optimization":
        if not calendar_events:
            st.warning("Upload an academic calendar first.")
        else:
            result = optimize_with_calendar(
                data,
                calendar_events,
                restricted_as_holiday,
                time_limit=15,
                semester_start=semester_start,
                semester_end=semester_end,
            )
            st.session_state["last_result"] = result
    elif solver_mode == "Optimize whole timetable":
        result = optimize_whole_timetable(data, time_limit=15)
        st.session_state["last_result"] = result
    elif solver_mode == "Simulate disruption":
        result = simulate_disruption(
            data, disruption_type, target_name, time_limit=10
        )
        st.session_state["last_result"] = result
    elif solver_mode == "Robustness analysis":
        result = robustness_report(data, time_limit=5)
        st.session_state["robustness"] = result
        result = {
            "status": "COMPLETE",
            "summary": f"AASE tested {result['checks']} single-resource disruptions.",
            "reasons": [
                f"Recoverable scenarios: {result['recoverable_checks']}/{result['checks']}.",
                f"Robustness metric: {result['robustness_percent']}%.",
            ],
        }
        st.session_state["last_result"] = result
    elif solver_mode == "Repair one disruption":
        result = optimize_timetable(
            data,
            student_id=student_id,
            absent_teacher=teacher_filter,
            absent_day=absent_day,
            absent_slot=absent_slot,
        )
        st.session_state["last_result"] = result
    else:
        result = repair_schedule(
            data, absent_day, absent_slot, teacher_filter, student_id
        )
        st.session_state["last_result"] = result

if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    st.subheader("AASE result")
    if result.get("status") in {"OPTIMAL", "FEASIBLE", "COMPLETE"}:
        st.success(result.get("summary", "Operation completed."))
    elif result.get("changed"):
        st.success(result.get("summary", "Operation completed."))
    else:
        st.warning(result.get("summary", "No solution found."))

    if result.get("status"):
        st.caption(f"Solver status: {result['status']}")

    if result.get("schedule"):
        st.dataframe(result["schedule"], use_container_width=True)

    if "robustness" in st.session_state:
        robustness = st.session_state["robustness"]
        st.metric(
            "Single-resource robustness",
            f"{robustness['robustness_percent']}%",
            f"{robustness['recoverable_checks']}/{robustness['checks']} scenarios recoverable",
        )
        with st.expander("Robustness details"):
            st.write("Teacher failures")
            st.dataframe(robustness["teacher_results"], use_container_width=True)
            st.write("Room failures")
            st.dataframe(robustness["room_results"], use_container_width=True)

    if result.get("reasons"):
        st.subheader("Why this result?")
        for reason in result["reasons"]:
            st.write("• " + reason)

st.divider()
st.caption(
    "AASE is ERP-agnostic: it can run standalone with PDFs/CSV/XLSX now and can later "
    "receive structured data through an ERP API."
)
