import streamlit as st
import fitz
import hashlib
from PIL import Image
import io
import pandas as pd
import base64

# ----------------------------------------------------
# App Setup
# ----------------------------------------------------
st.set_page_config(page_title="Inspection Photo Duplicate Checker", layout="wide")

# ----------------------------------------------------
# Initialize session keys
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
    for key in list(st.session_state.keys()):
        if key not in ["uploader_key"]:
            del st.session_state[key]

    st.session_state["uploader_key"] += 1
    st.experimental_set_query_params(_=str(st.session_state["uploader_key"]))
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.markdown("""
# Inspection Photo Duplicate Checker  
Upload PDFs in batches and detect strict binary duplicate photos.
""")

# ----------------------------------------------------
# File uploader (multi-batch)
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# ----------------------------------------------------
# Detect new batches
# ----------------------------------------------------
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]

    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# ----------------------------------------------------
# Show batches
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
        last = st.session_state["batches"].pop()
        for f in last:
            if f in st.session_state["all_files"]:
                st.session_state["all_files"].remove(f)

        st.session_state["uploader_key"] += 1
        st.rerun()

# ----------------------------------------------------
# Extract photos function
# ----------------------------------------------------
def extract_photos(pdf_name, pdf_bytes):
    output = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img in page.get_images(full=True):
            xref = img[0]
            extracted = doc.extract_image(xref)
            img_bytes = extracted["image"]

            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size

            if w >= 300 and h >= 150:
                md5 = hashlib.md5(img_bytes).hexdigest()
                output.append({
                    "file": pdf_name,
                    "page": page_index,
                    "md5": md5,
                    "image": image
                })

    return output

# ----------------------------------------------------
# RUN CHECK BUTTON
# ----------------------------------------------------
run_check = st.button("Run Duplicate Check")

if run_check:

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # Detect duplicate filenames
    filenames = [f.name for f in st.session_state["all_files"]]
    name_dupes = {x for x in filenames if filenames.count(x) > 1}

    if name_dupes:
        st.error("Duplicate PDF filenames detected!")
        st.warning("\n".join([f"• {n}" for n in name_dupes]))
        st.stop()

    # Cache files BEFORE reading (fixes EmptyFileError)
    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    status = st.empty()
    status.info("Extracting inspection photos...")
    records = []
    progress = st.progress(0)

    for i, f in enumerate(st.session_state["all_files"]):
        bytes_data = pdf_cache[f.name]
        records.extend(extract_photos(f.name, bytes_data))
        progress.progress((i + 1) / len(st.session_state["all_files"]))

    status.empty()

    df = pd.DataFrame(records)

    if df.empty:
        st.warning("No inspection photos found.")
        st.stop()

    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("✅ Good to go! No duplicate inspection photos detected.")
        st.stop()

    st.error("Duplicate inspection photos detected!")

    # ----------------------------------------------------
    # CARD GRID CSS (small cards)
    # ----------------------------------------------------
    st.markdown("""
    <style>
        .dup-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 18px;
            margin-top: 25px;
        }
        .dup-card {
            background: #1b1b1b;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 10px;
            text-align: center;
            box-shadow: 0 0 6px rgba(0,0,0,0.4);
            transition: 0.2s;
        }
        .dup-card:hover {
            transform: scale(1.03);
            box-shadow: 0 0 12px rgba(0,0,0,0.6);
        }
        .dup-img {
            width: 95%;
            height: 150px;
            object-fit: cover;
            border-radius: 6px;
        }
        .dup-title {
            font-family: monospace;
            font-size: 13px;
            color: #4caf50;
            margin-bottom: 6px;
        }
        .dup-files {
            font-size: 12px;
            text-align: left;
            margin-top: 8px;
            line-height: 1.3;
            color: #ddd;
        }
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # CARD GRID OUTPUT
    # ----------------------------------------------------
    st.markdown("<div class='dup-grid'>", unsafe_allow_html=True)

    for md5_hash, group in duplicates.groupby("md5"):

        # Convert first image to base64
        img_buf = io.BytesIO()
        first = group.iloc[0]["image"]
        first.save(img_buf, format="PNG")
        img64 = base64.b64encode(img_buf.getvalue()).decode()

        file_list_html = "".join(
            f"• {row['file']} — Pg {row['page']}<br>"
            for _, row in group.iterrows()
        )

        card = f"""
        <div class="dup-card">
            <div class="dup-title">MD5: {md5_hash}</div>
            <img class="dup-img" src="data:image/png;base64,{img64}">
            <div class="dup-files"><strong>Found in:</strong><br>{file_list_html}</div>
        </div>
        """

        st.markdown(card, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
