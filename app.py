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
    st.session_state["batches"] = []  # List of batches, each batch = list of UploadedFile objects

if "all_files" not in st.session_state:
    st.session_state["all_files"] = []  # Flattened list of all files in upload order

if "run_pressed" not in st.session_state:
    st.session_state["run_pressed"] = False

# ----------------------------------------------------
# Reset Button (FULL multi-reset reliability)
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
# File uploader (user uploads batches manually)
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
    # Identify which of the newly uploaded files are NEW in this run
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]

    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# ----------------------------------------------------
# Display batch summary (NO file list, as requested)
# ----------------------------------------------------
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}: {len(batch)} files**")

# ----------------------------------------------------
# Undo Last Batch — only before running
# ----------------------------------------------------
if st.session_state["batches"]:
    if st.button("Undo Last Batch"):

    # Remove last batch
    last_batch = st.session_state["batches"].pop()

    for f in last_batch:
        if f in st.session_state["all_files"]:
            st.session_state["all_files"].remove(f)

    # Allow running again
    st.session_state["run_pressed"] = False

    # Force uploader to refresh so removed files disappear visually
    st.session_state["uploader_key"] += 1

    st.rerun()

# ----------------------------------------------------
# Extract Inspection Photos
# ----------------------------------------------------
def extract_photos(pdf_name, pdf_bytes):
    output = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_index in range(len(doc)):
        page = doc[page_index]

        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_img = doc.extract_image(xref)
            img_bytes = base_img["image"]

            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size

            # UNIVERSAL working inspection-photo threshold
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
    st.session_state["run_pressed"] = True

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # -------------------------------------------
    # Detect duplicate filenames BEFORE processing
    # -------------------------------------------
    filenames = [f.name for f in st.session_state["all_files"]]
    duplicates_by_name = {x for x in filenames if filenames.count(x) > 1}

    if duplicates_by_name:
        st.error("⚠️ Duplicate PDF filenames detected!")
        st.warning(
            "You uploaded at least one PDF twice:\n\n" +
            "\n".join(f"- **{name}**" for name in duplicates_by_name) +
            "\n\nUse Undo Last Batch or Reset to fix your upload."
        )
        st.stop()

    # -------------------------------------------
    # Extract inspection photos with progress bar
    # -------------------------------------------
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

    # -------------------------------------------
    # No images found safety
    # -------------------------------------------
    if df.empty or "md5" not in df.columns:
        st.warning("⚠️ No valid inspection photos were found in any uploaded PDFs.")
        st.stop()

    # -------------------------------------------
    # Duplicate detection
    # -------------------------------------------
    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("✅ Good to go! No duplicate inspection photos detected.")
    else:
        st.error("🚨 Duplicate inspection photos detected:")

        for md5_hash, group in duplicates.groupby("md5"):
            st.markdown(f"### Duplicate Set — MD5: `{md5_hash}`")
            cols = st.columns(len(group))

            for col, (_, row) in zip(cols, group.iterrows()):
                col.markdown(f"**{row['file']} — Page {row['page']}**")

                # Convert image to base64 for stable thumbnails
                buf = io.BytesIO()
                row["image"].save(buf, format="PNG")
                img_bytes = buf.getvalue()

                col.markdown(
                    f"<img src='data:image/png;base64,{base64.b64encode(img_bytes).decode()}' "
                    f"style='width:70%; max-width:250px; border-radius:6px;'>",
                    unsafe_allow_html=True
                )
