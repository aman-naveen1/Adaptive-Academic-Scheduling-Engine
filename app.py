from datetime import date, datetime
from html import escape
from pathlib import Path
import re
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

# Streamlit reruns the script after widget interactions. These counters give
# uploaders a fresh widget identity after a successful import, so the same
# browser session can process another file without requiring a page refresh.
for state_key in ("timetable_upload_version", "calendar_upload_version"):
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

def _read_structured_upload(uploaded_file):
    """Return a dataframe for CSV/XLSX/XLS uploads."""
    name = getattr(uploaded_file, "name", "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    return None


def _norm_header(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _normalize_resource_frame(frame):
    """Normalize common metadata headers without requiring exact template names."""
    aliases = {
        "teacher_name": "teacher", "faculty": "teacher", "faculty_name": "teacher",
        "instructor": "teacher", "professor": "teacher",
        "room_name": "room", "room_no": "room", "room_number": "room",
        "classroom": "room", "venue": "room",
        "seating_capacity": "capacity", "room_capacity": "capacity", "seats": "capacity",
        "qualified_course": "qualified_courses", "courses": "qualified_courses",
        "subjects": "qualified_courses", "available_day": "available_days",
        "days": "available_days", "availability_days": "available_days",
        "available_time": "available_hours", "available_slots": "available_hours",
        "times": "available_hours", "time_slots": "available_hours",
        "absence_date": "date", "absent_date": "date",
        "event": "name", "event_name": "name", "description": "name",
        "event_type": "type", "category": "type", "status": "type",
        "absence_reason": "reason", "remarks": "reason", "notes": "reason",
    }
    rename = {}
    for col in frame.columns:
        key = _norm_header(col)
        if key in aliases:
            rename[col] = aliases[key]
    return frame.rename(columns=rename)


def _classify_resource_upload(frame, filename=""):
    """Identify resource CSV/XLSX files using headers, with filename fallback."""
    frame = _normalize_resource_frame(frame)
    columns = {_norm_header(c) for c in frame.columns}
    name = str(filename).lower()

    if "rooms" in name or "room" in name:
        if "room" in columns or "capacity" in columns:
            return "rooms"
    if "availability" in name and "teacher" in columns:
        return "availability"
    if ("absence" in name or "absences" in name) and "teacher" in columns and "date" in columns:
        return "absences"
    if "calendar" in name and "date" in columns:
        return "calendar"

    if {"day", "slot", "course"} <= columns and ({"teacher"} <= columns or {"room"} <= columns):
        return "timetable"
    if {"room", "capacity"} <= columns:
        return "rooms"
    if {"teacher", "date"} <= columns:
        return "absences"
    if {"teacher", "qualified_courses"} <= columns and {"available_days"} <= columns:
        return "availability"
    if "date" in columns and ("name" in columns or "type" in columns):
        return "calendar"
    return None


def _import_resource_upload(uploaded_file, selected_group):
    """Import one structured resource file into the normalized SQLite layer."""
    frame = _read_structured_upload(uploaded_file)
    kind = _classify_resource_upload(frame, getattr(uploaded_file, "name", ""))

    if kind == "timetable":
        rows, source = parse_timetable_file(uploaded_file, default_group=selected_group, use_ocr=False)
        teachers = sorted({row["teacher"] for row in rows if row["teacher"] != "UNKNOWN"})
        rooms = sorted({row["room"] for row in rows if row["room"] != "UNKNOWN"})
        students = [{"id": selected_group, "size": 0}]
        if "student_id" in frame.columns:
            students = [{"id": str(x).strip(), "size": 0} for x in frame["student_id"].dropna().unique() if str(x).strip()]
        seed_from_data({
            "classes": rows,
            "teachers": [{"name": t, "qualified_courses": sorted({r["course"] for r in rows if r["teacher"] == t}), "available_slots": {}} for t in teachers],
            "rooms": [{"name": room, "capacity": 60} for room in rooms],
            "students": students,
        }, source="document_import", replace_classes=True)
        return f"{len(rows)} timetable record(s) imported", rows

    if kind == "rooms":
        frame = _normalize_resource_frame(frame)
        rooms = []
        for _, row in frame.iterrows():
            name = str(row.get("room", "")).strip()
            if not name or name.lower() == "nan":
                continue
            rooms.append({
                "name": name,
                "capacity": int(float(row.get("capacity", 0) or 0)),
                "type": str(row.get("type", "Classroom")).strip(),
            })
        seed_from_data({"rooms": rooms}, source="room_metadata", replace_classes=False)
        return f"{len(rooms)} room record(s) imported", rooms

    if kind == "availability":
        frame = _normalize_resource_frame(frame)
        teachers = []
        for _, row in frame.iterrows():
            name = str(row.get("teacher", "")).strip()
            if not name or name.lower() == "nan":
                continue
            courses = [x.strip() for x in str(row.get("qualified_courses", "")).split(";") if x.strip()]
            days = [x.strip() for x in str(row.get("available_days", "")).split(";") if x.strip()]
            hours_text = str(row.get("available_hours", "")).strip()
            # Normalize availability into actual slot lists for CP-SAT.
            hours = [s.strip() for s in re.split(r"[;,|]+", hours_text) if s.strip()]
            teachers.append({
                "name": name,
                "qualified_courses": courses,
                "available_slots": {day: hours[:] for day in days},
            })
        seed_from_data({"teachers": teachers}, source="teacher_metadata", replace_classes=False)
        return f"{len(teachers)} teacher availability record(s) imported", teachers

    if kind == "absences":
        frame = _normalize_resource_frame(frame)
        count = 0
        for _, row in frame.iterrows():
            teacher = str(row.get("teacher", "")).strip()
            absence_date = str(row.get("date", "")).strip()
            if teacher and teacher.lower() != "nan" and absence_date and absence_date.lower() != "nan":
                record_absence(teacher, absence_date, str(row.get("reason", "")).strip())
                count += 1
        return f"{count} teacher absence record(s) imported", []

    if kind == "calendar":
        events, warnings = parse_academic_calendar(uploaded_file, use_ocr=False)
        if not events:
            raise ValueError("No dated academic-calendar events were detected.")
        save_calendar(events, restricted_as_holiday=False)
        return f"{len(events)} academic-calendar event(s) imported", events

    raise ValueError("Unrecognized structured file. Expected timetable, room, teacher availability, teacher absence, or academic-calendar columns.")


with st.sidebar:
    st.markdown('<div class="erp-brand">🧠 AASE Control Center</div>', unsafe_allow_html=True)
    page = st.radio("Navigation", ["Dashboard","Time Table","Teachers","Rooms","Academic Calendar","OCR Intake","Disruptions","Optimization","Reports"], label_visibility="collapsed")
    st.divider()
    st.caption("Data layer: SQLite")
    st.caption("OCR: Local Tesseract")
    st.caption("ERP integration: API-ready")
    st.divider()
    if st.button("Clear current session", use_container_width=True):
        for key in ("last_result", "disruption_result", "optimization_result", "robustness", "last_import_preview", "last_calendar_preview"):
            st.session_state.pop(key, None)
        st.session_state["timetable_upload_version"] += 1
        st.session_state["calendar_upload_version"] += 1
        st.rerun()

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
    col.markdown(f'<div class="metric-card"><div class="value">{escape(str(value))}</div><div class="label">{escape(label)}</div></div>', unsafe_allow_html=True)

if page == "Dashboard":
    st.markdown('<div class="section-title">Today\'s Timetable</div>', unsafe_allow_html=True)
    if today_classes:
        st.markdown('<div class="timeline">', unsafe_allow_html=True)
        order={s:i for i,s in enumerate(["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"])}
        for row in sorted(today_classes,key=lambda x:order.get(x["slot"],99)):
            st.markdown(f'<div class="timeline-item"><div class="timeline-time">{escape(str(row["slot"]))}</div><div class="class-card"><div class="class-course">{escape(str(row["course"]))}</div><div class="class-meta">{escape(str(row["teacher"]))} · Room {escape(str(row["room"]))} · {escape(str(row["group"]))}</div></div></div>',unsafe_allow_html=True)
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
    st.markdown('<div class="section-title">Timetable & Resource Intake</div>',unsafe_allow_html=True)
    st.caption("Upload one or more timetable/resource CSV or Excel files. AASE automatically detects timetable, room, teacher availability, absence and academic-calendar files.")
    uploader_key = f"timetable_upload_{st.session_state['timetable_upload_version']}"
    files=st.file_uploader("Upload timetable/resource files",type=["pdf","csv","xlsx","xls"],accept_multiple_files=True,key=uploader_key)
    use_ocr=st.checkbox("Enable Tesseract fallback for scanned PDFs",value=True,key="timetable_use_ocr")
    b1,b2=st.columns([3,1])
    with b1:
        parse_clicked=st.button("Parse & import files",type="primary",disabled=not files)
    with b2:
        clear_clicked=st.button("Clear uploads",disabled=not files)
    if clear_clicked:
        st.session_state["timetable_upload_version"] += 1
        st.rerun()

    if parse_clicked:
        timetable_rows=[]
        timetable_sources=[]
        successes=[]
        errors=[]

        # Collect all timetable files first so uploading both classroom and
        # student timetables produces one combined timetable instead of the
        # second file replacing the first.
        resource_files=[]
        for f in files:
            try:
                suffix = Path(getattr(f, "name", "")).suffix.lower()
                if suffix == ".pdf":
                    rows, source = parse_timetable_file(f,default_group=selected_group,use_ocr=use_ocr)
                    timetable_rows.extend(rows)
                    timetable_sources.append(f"{f.name} ({source})")
                else:
                    frame = _read_structured_upload(f)
                    kind = _classify_resource_upload(frame, getattr(f, "name", ""))
                    if kind == "timetable":
                        rows, source = parse_timetable_file(f,default_group=selected_group,use_ocr=False)
                        timetable_rows.extend(rows)
                        timetable_sources.append(f"{f.name} ({source})")
                    else:
                        resource_files.append(f)
            except Exception as exc:
                errors.append(f"{f.name}: {exc}")

        if timetable_rows:
            teachers = sorted({row["teacher"] for row in timetable_rows if row["teacher"] != "UNKNOWN"})
            rooms = sorted({row["room"] for row in timetable_rows if row["room"] != "UNKNOWN"})
            students = [{"id": selected_group, "size": 0}]
            seed_from_data({
                "classes": timetable_rows,
                "teachers": [{"name": t, "qualified_courses": sorted({r["course"] for r in timetable_rows if r["teacher"] == t}), "available_slots": {}} for t in teachers],
                "rooms": [{"name": room, "capacity": 60} for room in rooms],
                "students": students,
            }, source="document_import", replace_classes=True)
            successes.append(f"Timetable: {len(timetable_rows)} row(s) imported from {len(timetable_sources)} file(s).")

        for f in resource_files:
            try:
                message, preview = _import_resource_upload(f, selected_group)
                successes.append(f"{f.name}: {message}.")
            except Exception as exc:
                errors.append(f"{f.name}: {exc}")

        for message in successes:
            st.success(message)
        for error in errors:
            st.error(f"Could not process {error}")

        if successes:
            st.session_state["last_import_preview"] = timetable_rows
            st.session_state["last_import_summary"] = f"Processed {len(successes)} file(s); data is now available in SQLite."
            st.session_state["timetable_upload_version"] += 1
            st.rerun()

    if st.session_state.get("last_import_preview"):
        st.success(st.session_state.get("last_import_summary","Files imported successfully."))
        if st.session_state["last_import_preview"]:
            st.dataframe(pd.DataFrame(st.session_state["last_import_preview"]),use_container_width=True,hide_index=True)

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
    calendar_key = f"calendar_upload_{st.session_state['calendar_upload_version']}"
    calendar_file=st.file_uploader("Upload academic calendar",type=["pdf","csv","xlsx","xls"],key=calendar_key)
    restricted=st.checkbox("Treat restricted holidays as blocked",value=False,key="calendar_restricted")
    c1,c2=st.columns([3,1])
    with c1:
        calendar_clicked=st.button("Parse & save calendar",type="primary",disabled=not calendar_file)
    with c2:
        clear_calendar=st.button("Clear upload",disabled=not calendar_file)
    if clear_calendar:
        st.session_state["calendar_upload_version"] += 1
        st.rerun()
    if calendar_clicked:
        try:
            events,warnings=parse_academic_calendar(calendar_file,use_ocr=True)
            save_calendar(events,restricted_as_holiday=restricted)
            if events:
                st.session_state["last_calendar_preview"] = events
                st.session_state["last_calendar_warnings"] = warnings
                st.session_state["calendar_upload_version"] += 1
                st.rerun()
            else:
                st.error("No calendar events were parsed, so nothing was saved.")
                for w in warnings: st.warning(w)
        except Exception as exc:
            st.error(f"Could not process {calendar_file.name}: {exc}")
    else:
        st.caption("Supported: PDF, CSV, XLSX and XLS. Scanned PDFs automatically fall back to Tesseract when needed.")
    if st.session_state.get("last_calendar_preview"):
        st.success(f"Saved {len(st.session_state['last_calendar_preview'])} academic-calendar event(s) to SQLite.")
        for warning in st.session_state.get("last_calendar_warnings", []):
            st.warning(warning)
        st.dataframe(pd.DataFrame(st.session_state["last_calendar_preview"]),use_container_width=True,hide_index=True)

elif page == "OCR Intake":
    st.markdown('<div class="section-title">Document Intake & OCR</div>',unsafe_allow_html=True)
    st.info("AASE accepts PDF, CSV and Excel for timetable and academic-calendar intake. OCR is only needed when a PDF contains images/scans instead of selectable text.")
    st.code("PDF → text extraction → parser → SQLite\nScanned PDF → Tesseract OCR → parser → SQLite\nCSV/XLSX/XLS → pandas → normalized records → SQLite",language="text")
    st.markdown("### Tesseract configuration")
    st.write("Install Tesseract 5.x locally. If it is not on PATH, set TESSERACT_CMD to the full tesseract.exe path.")
    st.code('Windows example:\nTESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe',language="text")
    st.success("OCR is local and free; no Google Cloud account or API key is required.")

elif page == "Disruptions":
    st.markdown('<div class="section-title">Disruption Management</div>',unsafe_allow_html=True)
    disruption_type=st.radio("Failure type",["Teacher unavailable","Room unavailable"],horizontal=True,key="disruption_type")
    targets=sorted({x["teacher"] if disruption_type=="Teacher unavailable" else x["room"] for x in data["classes"]})
    target=st.selectbox("Resource",targets or ["No resources found"],key="disruption_target")
    if disruption_type == "Teacher unavailable":
        d1,d2=st.columns(2)
        with d1: disruption_day=st.selectbox("Absent day",["Monday","Tuesday","Wednesday","Thursday","Friday"],key="disruption_day")
        with d2: disruption_slots=st.multiselect("Absent time slots",["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"],default=["09:00-10:00"],key="disruption_slots")
    else:
        disruption_day=None
        disruption_slots=[]
    d1,d2=st.columns([3,1])
    with d1:
        simulate_clicked=st.button("Simulate disruption",type="primary",disabled=(disruption_type=="Teacher unavailable" and not disruption_slots))
    with d2:
        clear_simulation=st.button("Clear result",disabled="disruption_result" not in st.session_state)
    if clear_simulation:
        st.session_state.pop("disruption_result",None)
        st.rerun()
    if simulate_clicked:
        try:
            result=simulate_disruption(data,disruption_type,target,day=disruption_day,slots=disruption_slots,time_limit=10)
            st.session_state["disruption_result"]=result
            record_run("Disruption simulation",result.get("status","UNKNOWN"),result.get("summary",""))
        except Exception as exc:
            st.session_state["disruption_result"]={"status":"ERROR","summary":f"Disruption simulation failed: {exc}"}
            record_run("Disruption simulation","ERROR",str(exc))
    if "disruption_result" in st.session_state:
        result=st.session_state["disruption_result"]
        (st.success if result.get("status") in {"OPTIMAL","FEASIBLE"} or result.get("changed") else st.warning)(result.get("summary","Completed."))
        if result.get("schedule"): st.dataframe(pd.DataFrame(result["schedule"]),use_container_width=True,hide_index=True)
        for r in result.get("reasons",[]): st.write("• "+r)

elif page == "Optimization":
    st.markdown('<div class="section-title">AASE Optimization Engine</div>',unsafe_allow_html=True)
    operation=st.selectbox("Operation",["Optimize whole timetable","Repair one disruption","Heuristic repair","Robustness analysis"],key="optimization_operation")
    teacher_names=sorted({t["name"] for t in data["teachers"]})
    absent_teacher=st.selectbox("Absent teacher",teacher_names) if teacher_names else ""
    c1,c2=st.columns(2)
    with c1: absent_day=st.selectbox("Day",["Monday","Tuesday","Wednesday","Thursday","Friday"],key="optimization_day")
    with c2: absent_slots=st.multiselect("Time slots",["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"],default=["09:00-10:00"],key="optimization_slots")
    o1,o2=st.columns([3,1])
    with o1:
        run_clicked=st.button("Run AASE",type="primary",disabled=(operation in {"Optimize whole timetable","Repair one disruption","Heuristic repair"} and not absent_slots))
    with o2:
        clear_optimization=st.button("Clear result",disabled="optimization_result" not in st.session_state)
    if clear_optimization:
        st.session_state.pop("optimization_result",None)
        st.session_state.pop("robustness",None)
        st.rerun()
    if run_clicked:
        try:
            if operation=="Optimize whole timetable":
                result=optimize_whole_timetable(data,time_limit=15,absent_teacher=absent_teacher,absent_day=absent_day,absent_slots=absent_slots)
            elif operation=="Repair one disruption":
                result=optimize_timetable(data,student_id=selected_group,absent_teacher=absent_teacher,absent_day=absent_day,absent_slots=absent_slots)
            elif operation=="Heuristic repair":
                result=repair_schedule(data,absent_day,absent_slots[0] if absent_slots else None,absent_teacher,selected_group)
            else:
                rb=robustness_report(data,time_limit=5)
                result={"status":"COMPLETE","summary":f"Tested {rb['checks']} single-resource disruptions.","reasons":[f"Recoverable: {rb['recoverable_checks']}/{rb['checks']} ({rb['robustness_percent']}%)."]}
                st.session_state["robustness"]=rb
            st.session_state["optimization_result"]=result
            record_run(operation,result.get("status","UNKNOWN"),result.get("summary",""))
        except Exception as exc:
            result={"status":"ERROR","summary":f"Optimization failed: {exc}","reasons":["Check the input timetable/resource metadata and try again."]}
            st.session_state["optimization_result"]=result
            record_run(operation,"ERROR",str(exc))
    if "optimization_result" in st.session_state:
        result=st.session_state["optimization_result"]
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
