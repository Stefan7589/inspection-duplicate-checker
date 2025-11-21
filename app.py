import streamlit as st
import fitz
import hashlib
from PIL import Image
import io
import pandas as pd
import base64

# ----------------------------------------------------
# Page setup
# ----------------------------------------------------
st.set_page_config(page_title="Inspection Photo Duplicate Checker", layout="wide")

# ----------------------------------------------------
# Session state initialization
# ----------------------------------------------------
for key, default in {
    "uploader_key": 0,
    "batches": [],
    "all_files": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ----------------------------------------------------
# Reset App
# ----------------------------------------------------
if st.button("Reset App"):
    st.session_state.clear()
    st.session_state["uploader_key"] = 1
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.markdown("# Inspection Photo Duplicate Checker")
st.write("Upload PDF batches and detect STRICT binary duplicate photos.")

# ----------------------------------------------------
# File uploader
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}",
)

# ----------------------------------------------------
# Detect new batch
# ----------------------------------------------------
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]
    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# ----------------------------------------------------
# Display batch summary
# ----------------------------------------------------
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}: {len(batch)} files**")

# ----------------------------------------------------
# Undo last batch
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
# PDF photo extraction
# ----------------------------------------------------
def extract_photos(pdf_name, pdf_bytes):
    records = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img in page.get_images(full=True):
            xref = img[0]
            extracted = doc.extract_image(xref)
            img_bytes = extracted["image"]

            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size

            # Inspection photo threshold
            if w >= 300 and h >= 150:
                md5 = hashlib.md5(img_bytes).hexdigest()
                records.append({
                    "file": pdf_name,
                    "page": page_index,
                    "md5": md5,
                    "image": image,
                })

    return records

# ----------------------------------------------------
# Run duplicate detection
# ----------------------------------------------------
if st.button("Run Duplicate Check"):

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # Duplicate filenames check
    filenames = [f.name for f in st.session_state["all_files"]]
    duplicates_by_name = [x for x in set(filenames) if filenames.count(x) > 1]

    if duplicates_by_name:
        st.error("Duplicate filenames detected:")
        st.write("\n".join(duplicates_by_name))
        st.stop()

    # Cache file bytes
    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    status = st.info("Extracting inspection photos...")
    all_records = []
    progress = st.progress(0)

    for i, pdf in enumerate(st.session_state["all_files"]):
        all_records.extend(extract_photos(pdf.name, pdf_cache[pdf.name]))
        progress.progress((i + 1) / len(st.session_state["all_files"]))

    status.empty()

    df = pd.DataFrame(all_records)

    if df.empty:
        st.success("No inspection photos found.")
        st.stop()

    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("No duplicate photos detected.")
        st.stop()

    st.error("Duplicate inspection photos detected:")

    # ----------------------------------------------------
    # CSS for card grid (4 cards per row)
    # ----------------------------------------------------
    st.markdown("""
    <style>
        .dup-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .dup-card {
            background: #1c1c1c;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 10px;
            box-shadow: 0 0 8px rgba(0,0,0,0.5);
            text-align: center;
        }
        .dup-img {
            width: 100%;
            border-radius: 6px;
            margin-bottom: 8px;
        }
        .dup-title {
            color: #4caf50;
            font-family: monospace;
            font-size: 14px;
            padding-bottom: 6px;
        }
        .dup-files {
            text-align: left;
            font-size: 13px;
            color: #ddd;
            line-height: 1.3;
        }
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # Display duplicate cards
    # ----------------------------------------------------
    st.markdown("<div class='dup-grid'>", unsafe_allow_html=True)

    group_map = {}  # used for summary grouping

    for md5_hash, group in duplicates.groupby("md5"):
        first_row = group.iloc[0]

        buf = io.BytesIO()
        first_row["image"].save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        files_html = "".join(
            f"• {row['file']} (Pg {row['page']})<br>"
            for _, row in group.iterrows()
        )

        # Track report groups for summary
        group_map[md5_hash] = sorted({row["file"] for _, row in group.iterrows()})

        card_html = f"""
        <div class="dup-card">
            <div class="dup-title">{md5_hash}</div>
            <img class="dup-img" src="data:image/png;base64,{img_b64}">
            <div class="dup-files">
                <strong>Found in:</strong><br>
                {files_html}
            </div>
        </div>
        """

        st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ----------------------------------------------------
    # Summary section (grouped)
    # ----------------------------------------------------
    st.subheader("Reports Containing Duplicate Photos (Grouped by Relation)")

    for i, (md5_hash, files) in enumerate(group_map.items(), start=1):
        st.write(f"### Group {i}")
        for f in files:
            st.write(f"- {f}")
        st.write("---")
