import streamlit as st
import fitz
import hashlib
from PIL import Image
import io
import pandas as pd
import base64
from collections import defaultdict, deque

# ----------------------------------------------------
# Streamlit App Setup
# ----------------------------------------------------
st.set_page_config(page_title="Inspection Photo Duplicate Checker", layout="wide")

# ----------------------------------------------------
# Session Initialization
# ----------------------------------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

if "batches" not in st.session_state:
    st.session_state["batches"] = []

if "all_files" not in st.session_state:
    st.session_state["all_files"] = []

# ----------------------------------------------------
# Reset Button
# ----------------------------------------------------
if st.button("Reset App"):
    keep = {"uploader_key"}
    for key in list(st.session_state.keys()):
        if key not in keep:
            del st.session_state[key]

    st.session_state["uploader_key"] += 1
    st.experimental_set_query_params(reset="1")
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.title("Inspection Photo Duplicate Checker")
st.write("Upload PDFs in batches and detect strict binary duplicate photos.")

# ----------------------------------------------------
# File Upload
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# detect new batch
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]
    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# show batch summary
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}:** {len(batch)} files")

# ----------------------------------------------------
# Undo Last Batch
# ----------------------------------------------------
if st.session_state["batches"]:
    if st.button("Undo Last Batch"):
        last = st.session_state["batches"].pop()
        for f in last:
            if f in st.session_state["all_files"]:
                st.session_state["all_files"].remove(f)

        st.session_state["uploader_key"] += 1
        st.rerun()

# ----------------------------------------------------
# Extract Photos
# ----------------------------------------------------
def extract_photos(pdf_name, pdf_bytes):
    output = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for p in range(len(doc)):
        page = doc[p]
        for img in page.get_images(full=True):
            xref = img[0]
            data = doc.extract_image(xref)
            img_bytes = data["image"]

            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size
            if w >= 300 and h >= 150:
                md5 = hashlib.md5(img_bytes).hexdigest()
                output.append({
                    "file": pdf_name,
                    "page": p,
                    "md5": md5,
                    "image": image
                })

    return output

# ----------------------------------------------------
# RUN Duplicate Check
# ----------------------------------------------------
if st.button("Run Duplicate Check"):

    if not st.session_state["all_files"]:
        st.error("Upload files first.")
        st.stop()

    # check duplicate filenames
    names = [f.name for f in st.session_state["all_files"]]
    if len(names) != len(set(names)):
        st.error("Duplicate filenames detected. Fix this first.")
        st.stop()

    # cache PDF bytes
    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    # extract
    status = st.empty()
    status.info("Extracting photos…")
    all_records = []
    progress = st.progress(0)

    for i, f in enumerate(st.session_state["all_files"]):
        all_records.extend(extract_photos(f.name, pdf_cache[f.name]))
        progress.progress((i+1)/len(st.session_state["all_files"]))

    status.empty()

    df = pd.DataFrame(all_records)

    if df.empty:
        st.warning("No inspection photos found.")
        st.stop()

    # find duplicates
    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    # ----------------------------------------------------
    # NO DUPLICATES
    # ----------------------------------------------------
    if duplicates.empty:
        st.success("No duplicate photos found.")
        st.stop()

    # ----------------------------------------------------
    # YES DUPLICATES → DISPLAY GRID CARDS
    # ----------------------------------------------------
    st.error("Duplicate inspection photos detected.")

    # CSS Grid
    st.markdown("""
    <style>
        .dup-grid { 
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .dup-card {
            background: #1f1f1f;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 12px;
        }
        .dup-card img { width: 100%; border-radius: 6px; }
        .dup-title {
            font-family: monospace;
            color: #4caf50;
            text-align: center;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .dup-files {
            color: #ddd;
            font-size: 13px;
            margin-top: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

    html = "<div class='dup-grid'>"

    # record report relationships for clustering later
    graph = defaultdict(set)

    for md5_hash, group in duplicates.groupby("md5"):

        # build relationships (edges)
        files = list(group["file"].unique())
        for a in files:
            for b in files:
                if a != b:
                    graph[a].add(b)
                    graph[b].add(a)

        # convert first image
        first = group.iloc[0]
        buf = io.BytesIO()
        first["image"].save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        # file list
        file_html = "".join(f"• {row['file']} (Pg {row['page']})<br>"
                            for _, row in group.iterrows())

        # card HTML
        html += f"""
        <div class='dup-card'>
            <div class='dup-title'>MD5: {md5_hash}</div>
            <img src='data:image/png;base64,{img_b64}' />
            <div class='dup-files'>
                <strong>Found in:</strong><br>
                {file_html}
            </div>
        </div>
        """

    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # SUMMARY — GRAPH CLUSTERING OF RELATED REPORTS
    # ----------------------------------------------------
    st.subheader("Reports Containing Duplicate Photos (Grouped by Relation)")

    visited = set()
    groups = []

    for node in graph:
        if node not in visited:
            queue = deque([node])
            component = set()

            while queue:
                curr = queue.popleft()
                if curr not in visited:
                    visited.add(curr)
                    component.add(curr)
                    queue.extend(graph[curr])

            groups.append(sorted(component))

    # Display groups
    for i, group in enumerate(groups, start=1):
        st.markdown(f"### Group {i}")
        for rep in group:
            st.markdown(f"- {rep}")
