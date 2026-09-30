from datetime import date, datetime
import pandas as pd
import streamlit as st

from aase import robustness_report, simulate_disruption
from calendar_parser import parse_academic_calendar
from database import absence_count, init_db, load_data, recent_runs, record_absence, record_run, save_calendar, seed_from_data
from engine import gap_score, load_demo_data, repair_schedule
from ingestion import parse_timetable_file
from optimizer import optimize_timetable, optimize_whole_timetable

st.set_page_config(page_title="AASE Control Center", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")
init_db()

st.markdown("""
<style>
:root { --navy:#123b70; --ink:#20354b; }
html, body, [class*="css"] { color:#20354b; }
.stApp { background:#f7f9fc !important; color:#20354b !important; }
.block-container { padding:1.25rem 1.6rem 2.5rem; max-width:1500px; }
section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div { background:#fff !important; border-right:1px solid #dfe5ec; }
section[data-testid="stSidebar"] * { color:#526274; }
.erp-brand { font-size:1.05rem; font-weight:800; color:#20354b !important; padding:.4rem .55rem 1rem; }
.hero { background:linear-gradient(135deg,#f5f8fc,#e9f0f8); border:1px solid #dfe6ee; border-radius:22px; padding:1.25rem 1.5rem; margin-bottom:1rem; box-shadow:0 5px 18px rgba(24,45,70,.06); }
.hero h1 { margin:0; color:#1d3854 !important; font-size:2.15rem; text-align:center; }
.hero .sub,.hero .identity { text-align:center; color:#53677d !important; font-weight:600; margin-top:.35rem; }
.section-title { color:#1f3852 !important; font-size:1.55rem; font-weight:800; margin:1.35rem 0 .65rem; }
.metric-card { background:#123b70; color:#fff !important; border-radius:18px; padding:1rem .8rem; min-height:112px; display:flex; flex-direction:column; justify-content:center; text-align:center; box-shadow:0 7px 15px rgba(14,48,89,.14); }
.metric-card .value,.metric-card .label { color:#fff !important; }
.metric-card .value { font-size:1.65rem; font-weight:850; }
.metric-card .label { font-size:.9rem; font-weight:700; }
.timeline { border-left:3px solid #163f74; margin:.2rem 0 0 1rem; padding-left:1.4rem; }
.timeline-item { position:relative; margin:0 0 1rem; }
.timeline-item:before { content:""; position:absolute; width:11px; height:11px; border-radius:50%; background:#ffd400; border:2px solid #153f73; left:-1.82rem; top:.75rem; }
.timeline-time { color:#17457e !important; font-weight:850; }
.class-card { background:#fff; border:1px solid #e0e6ed; border-radius:13px; padding:.75rem 1rem; box-shadow:0 3px 8px rgba(30,55,80,.06); }
.class-course { font-weight:800; color:#1e3b59 !important; }
.class-meta { color:#5f7082 !important; font-size:.86rem; }
div[data-testid="stDataFrame"], div[data-testid="stFileUploader"] { border:1px solid #e1e6ed; border-radius:12px; overflow:hidden; background:#fff; }
button[kind="primary"] { background:#123b70 !important; color:#fff !important; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="erp-brand">🧠 AASE Control Center</div>', unsafe_allow_html=True)
    page = st.radio("Navigation", ["Dashboard","Time Table","Teachers","Rooms","Academic Calendar","OCR Intake","Disruptions","Optimization","Reports"], label_visibility="collapsed")
    st.divider()
    st.caption("Data layer: SQLite")
    st.caption("OCR: Local Tesseract")
    st.caption("ERP integration: API-ready")

if "db_seeded" not in st.session_state:
    seed_from_data(load_demo_data(), source="demo", replace_classes=True)
    st.session_state["db_seeded"] = True

data = load_data()

st.markdown("""
<div class="hero">
  <h1>AASE — Adaptive Academic Scheduling Engine</h1>
  <div class="sub">Intelligent timetable management • disruption recovery • student-gap optimization</div>
  <div class="identity">BSc Computer Science · Scheduling Administration Dashboard</div>
</div>
""", unsafe_allow_html=True)

today_name = datetime.now().strftime("%A")
groups = sorted({x["group"] for x in data["classes"]}) or ["BSc-CS-3A"]
selected_group = st.selectbox("Student / Group", groups, index=0, key="selected_group")
today_classes = [x for x in data["classes"] if x["day"] == today_name and x["group"] == selected_group]
current_gap = gap_score(data["classes"], selected_group)

m1,m2,m3,m4 = st.columns(4)
for col,value,label in [(m1,len(today_classes),"Classes Today"),(m2,current_gap,"Student Idle-Gap Score"),(m3,absence_count(),"Recorded Staff Absences"),(m4,len(data["rooms"]),"Managed Rooms")]:
    col.markdown(f'<div class="metric-card"><div class="value">{value}</div><div class="label">{label}</div></div>', unsafe_allow_html=True)

if page == "Dashboard":
    st.markdown('<div class="section-title">Today\'s Timetable</div>', unsafe_allow_html=True)
    if today_classes:
        st.markdown('<div class="timeline">', unsafe_allow_html=True)
        order={s:i for i,s in enumerate(["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"])}
        for row in sorted(today_classes,key=lambda x:order.get(x["slot"],99)):
            st.markdown(f'<div class="timeline-item"><div class="timeline-time">{row["slot"]}</div><div class="class-card"><div class="class-course">{row["course"]}</div><div class="class-meta">{row["teacher"]} · Room {row["room"]} · {row["group"]}</div></div></div>',unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else: st.info(f"No scheduled classes for {selected_group} today ({today_name}).")
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="section-title">Managed timetable records</div>',unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(data["classes"]),use_container_width=True,hide_index=True)
    with c2:
        st.markdown('<div class="section-title">Recent AASE operations</div>',unsafe_allow_html=True)
        runs=recent_runs(6)
        if runs: st.dataframe(pd.DataFrame(runs)[["created_at","operation","status","summary"]],use_container_width=True,hide_index=True)
        else: st.info("No optimization runs yet.")

elif page == "Time Table":
    st.markdown('<div class="section-title">Timetable Intake</div>',unsafe_allow_html=True)
    st.caption("Upload PDF, CSV or Excel. CSV/XLSX are parsed directly; PDF text is extracted first and scanned PDFs can fall back to local Tesseract OCR.")
    files=st.file_uploader("Upload timetable files",type=["pdf","csv","xlsx"],accept_multiple_files=True)
    use_ocr=st.checkbox("Enable Tesseract fallback for scanned PDFs",value=True)
    if files and st.button("Parse & import timetable",type="primary"):
        imported=[]
        for f in files:
            try:
                rows, source = parse_timetable_file(f,default_group=selected_group,use_ocr=use_ocr)
                imported.extend(rows)
                st.success(f"{f.name}: {len(rows)} row(s) parsed via {source}.")
            except Exception as exc: st.error(f"Could not process {f.name}: {exc}")
        if imported:
            imported_data={"classes":imported,"teachers":[],"rooms":[],"students":[{"id":selected_group,"size":0}]}
            teacher_names=sorted({x["teacher"] for x in imported if x["teacher"]!="UNKNOWN"})
            room_names=sorted({x["room"] for x in imported if x["room"]!="UNKNOWN"})
            imported_data["teachers"]=[{"name":t,"qualified_courses":sorted({x["course"] for x in imported if x["teacher"]==t}),"available_slots":{}} for t in teacher_names]
            imported_data["rooms"]=[{"name":r,"capacity":60} for r in room_names]
            seed_from_data(imported_data,source="document_import",replace_classes=True)
            st.success(f"Imported {len(imported)} timetable record(s) into SQLite.")
            st.dataframe(pd.DataFrame(imported),use_container_width=True,hide_index=True)

elif page == "Teachers":
    st.markdown('<div class="section-title">Teacher Metadata & Availability</div>',unsafe_allow_html=True)
    rows=[{"Teacher":t["name"],"Qualified courses":", ".join(t.get("qualified_courses",[])),"Available slots":sum(len(v) for v in t.get("available_slots",{}).values())} for t in data["teachers"]]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.markdown("### Record an absence")
    if data["teachers"]:
        teacher=st.selectbox("Teacher",sorted({t["name"] for t in data["teachers"]}))
        absence_date=st.date_input("Absence date",value=date.today())
        reason=st.text_input("Reason","")
        if st.button("Record absence",type="primary"):
            record_absence(teacher,absence_date.isoformat(),reason); st.success(f"Recorded {teacher} as absent on {absence_date}."); st.rerun()

elif page == "Rooms":
    st.markdown('<div class="section-title">Room Inventory</div>',unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(data["rooms"]),use_container_width=True,hide_index=True)

elif page == "Academic Calendar":
    st.markdown('<div class="section-title">Academic Calendar Intelligence</div>',unsafe_allow_html=True)
    calendar_file=st.file_uploader("Upload academic calendar",type=["pdf","csv","xlsx"],key="calendar_upload")
    restricted=st.checkbox("Treat restricted holidays as blocked",value=False)
    if calendar_file and st.button("Parse & save calendar",type="primary"):
        try:
            events,warnings=parse_academic_calendar(calendar_file,use_ocr=True)
            save_calendar(events,restricted_as_holiday=restricted)
            for w in warnings: st.warning(w)
            if events:
                st.success(f"Saved {len(events)} calendar event(s) to SQLite.")
                st.dataframe(pd.DataFrame(events),use_container_width=True,hide_index=True)
            else: st.error("No calendar events were parsed, so nothing was saved.")
        except Exception as exc: st.error(f"Could not process academic calendar: {exc}")
    else: st.caption("Supported: PDF, CSV, XLSX. Scanned PDFs automatically fall back to Tesseract when needed.")

elif page == "OCR Intake":
    st.markdown('<div class="section-title">Document Intake & OCR</div>',unsafe_allow_html=True)
    st.info("AASE accepts PDF, CSV and XLSX for timetable and academic-calendar intake. OCR is only needed when a PDF contains images/scans instead of selectable text.")
    st.code("PDF → text extraction → parser → SQLite\nScanned PDF → Tesseract OCR → parser → SQLite\nCSV/XLSX → pandas → normalized records → SQLite",language="text")
    st.markdown("### Tesseract configuration")
    st.write("Install Tesseract 5.x locally. If it is not on PATH, set TESSERACT_CMD to the full tesseract.exe path.")
    st.code('Windows example:\nTESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe',language="text")
    st.success("OCR is local and free; no Google Cloud account or API key is required.")

elif page == "Disruptions":
    st.markdown('<div class="section-title">Disruption Management</div>',unsafe_allow_html=True)
    disruption_type=st.radio("Failure type",["Teacher unavailable","Room unavailable"],horizontal=True)
    targets=sorted({x["teacher"] if disruption_type=="Teacher unavailable" else x["room"] for x in data["classes"]})
    target=st.selectbox("Resource",targets or ["No resources found"])
    if st.button("Simulate disruption",type="primary"):
        result=simulate_disruption(data,disruption_type,target,time_limit=10); st.session_state["last_result"]=result; record_run("Disruption simulation",result.get("status","UNKNOWN"),result.get("summary",""))
    if "last_result" in st.session_state:
        result=st.session_state["last_result"]
        (st.success if result.get("status") in {"OPTIMAL","FEASIBLE"} or result.get("changed") else st.warning)(result.get("summary","Completed."))
        if result.get("schedule"): st.dataframe(pd.DataFrame(result["schedule"]),use_container_width=True,hide_index=True)
        for r in result.get("reasons",[]): st.write("• "+r)

elif page == "Optimization":
    st.markdown('<div class="section-title">AASE Optimization Engine</div>',unsafe_allow_html=True)
    operation=st.selectbox("Operation",["Optimize whole timetable","Repair one disruption","Heuristic repair","Robustness analysis"])
    teacher_names=sorted({t["name"] for t in data["teachers"]})
    absent_teacher=st.selectbox("Absent teacher",teacher_names) if teacher_names else ""
    c1,c2=st.columns(2)
    with c1: absent_day=st.selectbox("Day",["Monday","Tuesday","Wednesday","Thursday","Friday"])
    with c2: absent_slot=st.selectbox("Slot",["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"])
    if st.button("Run AASE",type="primary"):
        if operation=="Optimize whole timetable": result=optimize_whole_timetable(data,time_limit=15)
        elif operation=="Repair one disruption": result=optimize_timetable(data,student_id=selected_group,absent_teacher=absent_teacher,absent_day=absent_day,absent_slot=absent_slot)
        elif operation=="Heuristic repair": result=repair_schedule(data,absent_day,absent_slot,absent_teacher,selected_group)
        else:
            rb=robustness_report(data,time_limit=5); result={"status":"COMPLETE","summary":f"Tested {rb['checks']} single-resource disruptions.","reasons":[f"Recoverable: {rb['recoverable_checks']}/{rb['checks']} ({rb['robustness_percent']}%)."]}; st.session_state["robustness"]=rb
        st.session_state["last_result"]=result; record_run(operation,result.get("status","UNKNOWN"),result.get("summary",""))
    if "last_result" in st.session_state:
        result=st.session_state["last_result"]
        (st.success if result.get("status") in {"OPTIMAL","FEASIBLE","COMPLETE"} or result.get("changed") else st.warning)(result.get("summary","Operation completed."))
        if result.get("schedule"): st.dataframe(pd.DataFrame(result["schedule"]),use_container_width=True,hide_index=True)
        for r in result.get("reasons",[]): st.write("• "+r)
        rb=st.session_state.get("robustness")
        if rb: st.metric("Single-resource robustness",f"{rb['robustness_percent']}%",f"{rb['recoverable_checks']}/{rb['checks']} recoverable")

else:
    st.markdown('<div class="section-title">Reports & Audit Trail</div>',unsafe_allow_html=True)
    runs=recent_runs(50)
    if runs: st.dataframe(pd.DataFrame(runs),use_container_width=True,hide_index=True)
    else: st.info("No AASE operations have been recorded yet.")
    st.markdown("### Architecture")
    st.code("ERP/API or PDF/Tesseract → SQLite normalized data → CP-SAT optimizer → repaired timetable → dashboard",language="text")

st.divider()
st.caption("AASE is ERP-agnostic: SQLite is the local project database today; a college ERP API can become the production data source later.")
