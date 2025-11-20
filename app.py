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
# File Uploader (Multi-Batch)
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# ----------------------------------------------------
# Detect New Batch
# ----------------------------------------------------
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]

    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# ----------------------------------------------------
# Show Batch Summary
# ----------------------------------------------------
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}: {len(batch)} files**")

# ----------------------------------------------------
# Undo Last Batch
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
# Extract Photos
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

            if w >= 300 and h >= 150:  # Inspection photos
                md5 = hashlib.md5(img_bytes).hexdigest()
                output.append({
                    "file": pdf_name,
                    "page": page_index,
                    "md5": md5,
                    "image": image
                })

    return output

# ----------------------------------------------------
# Run Duplicate Check
# ----------------------------------------------------
if st.button("Run Duplicate Check"):

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # Check duplicate filenames
    filenames = [f.name for f in st.session_state["all_files"]]
    duplicates_by_name = {x for x in filenames if filenames.count(x) > 1}

    if duplicates_by_name:
        st.error("⚠️ Duplicate PDF filenames detected!")
        st.warning(
            "You uploaded the same PDF twice:\n\n" +
            "\n".join(f"• **{name}**" for name in duplicates_by_name) +
            "\n\nUse Undo Last Batch or Reset."
        )
        st.stop()

    # Fix: Cache PDF bytes
    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    status = st.empty()
    status.info("Extracting inspection photos…")

    all_records = []
    progress = st.progress(0)

    for i, pdf in enumerate(st.session_state["all_files"]):
        pdf_bytes = pdf_cache[pdf.name]
        all_records.extend(extract_photos(pdf.name, pdf_bytes))
        progress.progress((i + 1) / len(st.session_state["all_files"]))

    status.empty()
    df = pd.DataFrame(all_records)

    if df.empty:
        st.warning("⚠️ No inspection photos found.")
        st.stop()

    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("✅ Good to go! No duplicate inspection photos detected.")
    else:
        st.error("🚨 Duplicate inspection photos detected:")

        # ------------------------------------------------------------
        # CSS for card layout
        # ------------------------------------------------------------
        st.markdown("""
        <style>
            .dup-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 18px;
                margin-top: 25px;
            }
            .dup-card {
                background: #1e1e1e;
                padding: 15px;
                border-radius: 10px;
                border: 1px solid #333;
                box-shadow: 0 0 10px rgba(0,0,0,0.4);
            }
            .dup-title {
                font-size: 15px;
                color: #4CAF50;
                font-family: monospace;
                margin-bottom: 10px;
                text-align: center;
            }
            .dup-img {
                width: 100%;
                border-radius: 6px;
                margin-top: 8px;
            }
            .dup-files {
                font-size: 13px;
                color: #ddd;
                margin-bottom: 8px;
                line-height: 1.3;
            }
        </style>
        """, unsafe_allow_html=True)

        # Start Grid
        st.markdown("<div class='dup-grid'>", unsafe_allow_html=True)

        # Loop groups
        for md5_hash, group in duplicates.groupby("md5"):

            # Convert first image from group
            first_row = group.iloc[0]
            buf = io.BytesIO()
            first_row["image"].save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            # File list
            file_list_html = "".join(
                f"• {row['file']} — Page {row['page']}<br>"
                for _, row in group.iterrows()
            )

            card_html = f"""
            <div class="dup-card">
                <div class="dup-title">MD5: {md5_hash}</div>

                <div class="dup-files">
                    <strong>📄 Found in:</strong><br>
                    {file_list_html}
                </div>

                <img class="dup-img" src="data:image/png;base64,{img_b64}">
            </div>
            """

            st.markdown(card_html, unsafe_allow_html=True)

        # End Grid
        st.markdown("</div>", unsafe_allow_html=True)
