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
# Initialize all required session keys
# ----------------------------------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

if "batches" not in st.session_state:
    st.session_state["batches"] = []  # list of batches (each batch is a list of files)

if "all_files" not in st.session_state:
    st.session_state["all_files"] = []  # flattened list of all uploaded files

# ----------------------------------------------------
# Reset Button (fully reliable)
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
# Detect new batch of uploaded files
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
# Extract inspection photos
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

            # Universal threshold
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
# Run Duplicate Check
# ----------------------------------------------------
if st.button("Run Duplicate Check"):

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # Duplicate filename detection
    filenames = [f.name for f in st.session_state["all_files"]]
    duplicates_by_name = {x for x in filenames if filenames.count(x) > 1}

    if duplicates_by_name:
        st.error("⚠️ Duplicate PDF filenames detected!")
        st.warning(
            "You uploaded the same PDF file more than once:\n\n" +
            "\n".join(f"- **{name}**" for name in duplicates_by_name) +
            "\n\nUse Undo Last Batch or Reset to fix this."
        )
        st.stop()

    # Extraction progress
    status = st.empty()
    status.info("Extracting inspection photos…")
    all_records = []
    progress = st.progress(0)

    for i, pdf in enumerate(st.session_state["all_files"]):
        pdf_bytes = pdf.read()
        all_records.extend(extract_photos(pdf.name, pdf_bytes))
        progress.progress((i + 1) / len(st.session_state["all_files"]))

    status.empty()
    df = pd.DataFrame(all_records)

    if df.empty or "md5" not in df.columns:
        st.warning("⚠️ No valid inspection photos found.")
        st.stop()

    # Duplicate detection
    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("✅ Good to go! No duplicate inspection photos detected.")
    else:
        st.error("🚨 Duplicate inspection photos detected:")

        # ------------------------------------------------------------
        # GRID CARD CSS
        # ------------------------------------------------------------
        st.markdown("""
        <style>
            .dup-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .dup-card {
                background: #1a1a1a;
                padding: 15px;
                border-radius: 10px;
                border: 1px solid #333;
                box-shadow: 0 0 8px rgba(0,0,0,0.35);
            }
            .dup-title {
                font-size: 14px;
                color: #4caf50;
                margin-bottom: 10px;
                font-family: monospace;
            }
            .dup-img {
                width: 100%;
                border-radius: 6px;
                margin-bottom: 8px;
            }
            .dup-files {
                font-size: 13px;
                line-height: 1.3;
            }
        </style>
        """, unsafe_allow_html=True)

        # ------------------------------------------------------------
        # GRID START
        # ------------------------------------------------------------
        st.markdown("<div class='dup-grid'>", unsafe_allow_html=True)

        for md5_hash, group in duplicates.groupby("md5"):

            # Convert first image to Base64
            first_row = group.iloc[0]
            buf = io.BytesIO()
            first_row["image"].save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            # Build card
            st.markdown(f"""
            <div class="dup-card">
                <div class="dup-title">MD5: {md5_hash}</div>

                <img class="dup-img" src="data:image/png;base64,{img_b64}">

                <div class="dup-files">
                    <strong>📄 Found in:</strong><br>
                    {''.join([f"• {row['file']} — Page {row['page']}<br>" 
                              for _, row in group.iterrows()])}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ------------------------------------------------------------
        # GRID END
        # ------------------------------------------------------------
        st.markdown("</div>", unsafe_allow_html=True)
