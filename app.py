import streamlit as st
from engine import load_demo_data, parse_timetable_pdf, repair_schedule
from optimizer import optimize_timetable, optimize_whole_timetable

st.set_page_config(page_title="Timetable Fixer", page_icon="🗓️", layout="wide")
st.title("🗓️ Timetable Fixer")
st.caption("OCR-enabled timetable extraction + constraint optimization without ERP access.")

with st.sidebar:
    st.header("Inputs")
    demo = st.checkbox("Use demo data", value=True)
    student_id = st.text_input("Student / Group", "BSc-CS-3A")
    teacher_filter = st.text_input("Teacher absent", "Dr. Sharma")
    ocr_mode = st.checkbox("OCR scanned PDFs", value=True, disabled=demo)
    uploaded = st.file_uploader("Upload timetable PDF(s)", type=["pdf"], accept_multiple_files=True)

if demo:
    data = load_demo_data()
    ocr_warnings = []
else:
    data = {"classes": [], "teachers": [], "rooms": [], "students": []}
    ocr_warnings = []
    for f in uploaded or []:
        try:
            classes = parse_timetable_pdf(f, use_ocr=ocr_mode, default_group=student_id)
            data["classes"].extend(classes)
            if ocr_mode:
                low_conf = sum(1 for row in classes if row.get("ocr_confidence", 100) < 55)
                if low_conf:
                    ocr_warnings.append(f"{f.name}: {low_conf} extracted row(s) have low OCR confidence.")
        except Exception as exc:
            st.error(f"Could not process {f.name}: {exc}")

    # Uploaded PDFs are not connected to the college ERP, so infer the minimal
    # solver metadata directly from OCR output.
    teacher_names = sorted({x["teacher"] for x in data["classes"] if x["teacher"] != "UNKNOWN"})
    room_names = sorted({x["room"] for x in data["classes"] if x["room"] != "UNKNOWN"})
    data["teachers"] = [{"name": t, "qualified_courses": sorted({x["course"] for x in data["classes"] if x["teacher"] == t}),
                         "available_slots": {}} for t in teacher_names]
    data["rooms"] = [{"name": r, "capacity": 60} for r in room_names]
    data["students"] = [{"id": student_id, "size": 0}]

st.subheader("Current timetable")
if data["classes"]:
    st.dataframe(data["classes"], use_container_width=True)
else:
    st.info("Upload one or more timetable PDFs or enable demo data.")

if ocr_warnings:
    st.subheader("OCR review")
    for warning in ocr_warnings:
        st.warning(warning)

if data["teachers"]:
    st.subheader("Teacher metadata")
    st.dataframe(data["teachers"], use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    absent_day = st.selectbox("Disruption day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
with col2:
    absent_slot = st.selectbox("Disruption slot", ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15", "14:00-15:00", "15:00-16:00"])

solver_mode = st.radio("Optimization mode", ["Repair one disruption", "Optimize whole timetable", "Heuristic repair"], horizontal=True)

if st.button("Run optimizer", type="primary"):
    if not data["classes"]:
        st.warning("No timetable rows were extracted.")
    elif solver_mode == "Optimize whole timetable":
        result = optimize_whole_timetable(data, time_limit=15)
    elif solver_mode == "Repair one disruption":
        result = optimize_timetable(data, student_id=student_id, absent_teacher=teacher_filter,
                                    absent_day=absent_day, absent_slot=absent_slot)
    else:
        result = repair_schedule(data, absent_day, absent_slot, teacher_filter, student_id)

    st.subheader("Optimization result")
    if result["changed"]:
        st.success(result["summary"])
        if result.get("status"):
            st.caption(f"Solver status: {result['status']}")
        st.dataframe(result["schedule"], use_container_width=True)
        st.subheader("Why this result?")
        for reason in result.get("reasons", []):
            st.write("• " + reason)
    else:
        st.warning(result["summary"])

st.divider()
st.caption("For scanned PDFs, OCR output is best-effort. Review extracted rows before relying on the optimized timetable.")
