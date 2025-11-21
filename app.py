import streamlit as st
import fitz
import hashlib
from PIL import Image
import io
import pandas as pd
import base64

# ----------------------------------------------------
# APP SETUP
# ----------------------------------------------------
st.set_page_config(page_title="Inspection Photo Duplicate Checker", layout="wide")

# ----------------------------------------------------
# SESSION STATE SETUP
# ----------------------------------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

if "batches" not in st.session_state:
    st.session_state["batches"] = []

if "all_files" not in st.session_state:
    st.session_state["all_files"] = []

# ----------------------------------------------------
# RESET APP
# ----------------------------------------------------
if st.button("Reset App"):
    for key in list(st.session_state.keys()):
        if key not in ["uploader_key"]:
            del st.session_state[key]
    st.session_state["uploader_key"] += 1
    st.experimental_set_query_params(reset=st.session_state["uploader_key"])
    st.rerun()

# ----------------------------------------------------
# TITLE
# ----------------------------------------------------
st.markdown("# Inspection Photo Duplicate Checker")

# ----------------------------------------------------
# FILE UPLOADER
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# ----------------------------------------------------
# DETECT NEW BATCH
# ----------------------------------------------------
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]
    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# ----------------------------------------------------
# SHOW BATCH SUMMARY
# ----------------------------------------------------
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}: {len(batch)} files**")

# ----------------------------------------------------
# UNDO LAST BATCH
# ----------------------------------------------------
if st.session_state["batches"]:
    if st.button("Undo Last Batch"):
        last_batch = st.session_state["batches"].pop()
        for f in last_batch:
            if f in st.session_state["all_files"]:
                st.session_state["all_files"].remove(f)
        st.session_state["uploader_key"] += 1
        st.rerun()

# ----------------------------------------------------
# EXTRACT PHOTOS FROM PDF
# ----------------------------------------------------
def extract_photos(pdf_name, pdf_bytes):
    output = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_index, page in enumerate(doc):
        for img in page.get_images(full=True):
            xref = img[0]
            extracted = doc.extract_image(xref)
            img_bytes = extracted["image"]

            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size

            if w >= 300 and h >= 150:  # inspection photo threshold
                md5 = hashlib.md5(img_bytes).hexdigest()
                output.append({
                    "file": pdf_name,
                    "page": page_index,
                    "md5": md5,
                    "image": image
                })
    return output

# ----------------------------------------------------
# RUN DUPLICATE CHECK
# ----------------------------------------------------
run_check = st.button("Run Duplicate Check")

if run_check:

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # Check duplicate filenames
    filenames = [f.name for f in st.session_state["all_files"]]
    dup_names = {x for x in filenames if filenames.count(x) > 1}

    if dup_names:
        st.error("Duplicate filenames detected!")
        st.warning("\n".join(f"• {x}" for x in dup_names))
        st.stop()

    # Cache file bytes
    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    status = st.info("Extracting inspection photos…")
    all_records = []
    progress = st.progress(0)

    for i, pdf in enumerate(st.session_state["all_files"]):
        all_records.extend(extract_photos(pdf.name, pdf_cache[pdf.name]))
        progress.progress((i + 1) / len(st.session_state["all_files"]))

    status.empty()

    df = pd.DataFrame(all_records)

    if df.empty:
        st.warning("No valid inspection photos detected.")
        st.stop()

    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("No duplicate photos detected!")
        st.stop()
    else:
        st.error("Duplicate inspection photos detected!")

    # ----------------------------------------------------
    # CSS FOR GRID CARDS
    # ----------------------------------------------------
    st.markdown("""
    <style>
        .dup-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
            gap: 25px;
            margin-top: 25px;
        }
        .dup-card {
            background: #1f1f1f;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 14px;
            box-shadow: 0 0 8px rgba(0,0,0,0.4);
        }
        .dup-img {
            width: 100%;
            border-radius: 6px;
        }
        .dup-title {
            font-family: monospace;
            font-weight: bold;
            text-align: center;
            color: #4caf50;
            margin-bottom: 12px;
        }
        .dup-files {
            margin-top: 10px;
            color: #ddd;
            font-size: 13px;
        }
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # BUILD CARD GRID
    # ----------------------------------------------------
    grid_html = "<div class='dup-grid'>"
    report_groups = []  # for summary

    for md5_hash, group in duplicates.groupby("md5"):

        # Convert first image only
        first_row = group.iloc[0]
        buffer = io.BytesIO()
        first_row["image"].save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode()

        files_html = ""
        current_group_reports = set()

        for _, row in group.iterrows():
            files_html += f"• {row['file']} (Pg {row['page']})<br>"
            current_group_reports.add(row["file"])

        report_groups.append(current_group_reports)

        grid_html += f"""
        <div class="dup-card">
            <div class="dup-title">{md5_hash}</div>
            <img class="dup-img" src="data:image/png;base64,{img_b64}">
            <div class="dup-files"><strong>Found in:</strong><br>{files_html}</div>
        </div>
        """

    grid_html += "</div>"
    st.markdown(grid_html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # GROUP SUMMARY SECTION
    # ----------------------------------------------------
    st.subheader("Reports Containing Duplicate Photos (Grouped by Relation)")
    for i, group in enumerate(report_groups, start=1):
        st.markdown(f"### Group {i}")
        for file in sorted(group):
            st.write(f"- {file}")
