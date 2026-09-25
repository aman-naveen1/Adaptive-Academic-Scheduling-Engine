import streamlit as st
from engine import load_demo_data, parse_timetable_pdf, repair_schedule

st.set_page_config(page_title="Timetable Fixer", page_icon="🗓️", layout="wide")
st.title("🗓️ Timetable Fixer")
st.caption("Repair disrupted college schedules while minimizing student idle gaps and timetable conflicts.")

with st.sidebar:
    st.header("Inputs")
    demo = st.checkbox("Use demo data", value=True)
    student_id = st.text_input("Student / Group", "BSc-CS-3A")
    teacher_filter = st.text_input("Teacher absent", "Dr. Sharma")
    uploaded = st.file_uploader("Upload timetable PDF", type=["pdf"], accept_multiple_files=True)

if demo:
    data = load_demo_data()
else:
    data = {"classes": [], "teachers": [], "rooms": [], "students": []}
    for f in uploaded or []:
        data["classes"].extend(parse_timetable_pdf(f))

st.subheader("Current timetable")
if data["classes"]:
    st.dataframe(data["classes"], use_container_width=True)
else:
    st.info("Upload a timetable PDF or enable demo data.")

st.subheader("Teacher availability")
if data["teachers"]:
    st.dataframe(data["teachers"], use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    absent_day = st.selectbox("Disruption day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
with col2:
    absent_slot = st.selectbox("Disruption slot", ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15", "14:00-15:00", "15:00-16:00"])

if st.button("Repair timetable", type="primary"):
    result = repair_schedule(data, absent_day, absent_slot, teacher_filter, student_id)
    st.subheader("Repair result")
    if result["changed"]:
        st.success(result["summary"])
        st.dataframe(result["schedule"], use_container_width=True)
        st.subheader("Why this move?")
        for reason in result["reasons"]:
            st.write("• " + reason)
    else:
        st.warning(result["summary"])

st.divider()
st.caption("Demo data is synthetic and intended for project demonstration only.")
