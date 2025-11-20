import streamlit as st
import fitz
import hashlib
from PIL import Image
import io
import pandas as pd

# ----------------------------------------------------
# App Setup
# ----------------------------------------------------
st.set_page_config(page_title="Inspection Photo Duplicate Checker", layout="wide")

# ----------------------------------------------------
# Reset Logic (Container-Based Reset)
# ----------------------------------------------------
if "uploader_container_key" not in st.session_state:
    st.session_state["uploader_container_key"] = 0

if st.button("Reset App"):
    st.session_state.clear()  # Clear all state
    st.session_state["uploader_container_key"] += 1  # Force new container
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.markdown("""
# Inspection Photo Duplicate Checker  
Upload PDFs and detect strict binary duplicate photos.
""")

# ----------------------------------------------------
# Dynamic Container for File Uploader (THIS FIXES THE PROBLEM)
# ----------------------------------------------------
uploader_container = st.container()

with uploader_container:
    uploaded_files = st.file_uploader(
        "Upload PDF Reports",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_container_key']}"
    )

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

            if w >= 650 and h >= 450:  # Only real inspection photos
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

    if not uploaded_files:
        st.error("Please upload PDF files first.")
        st.stop()

    status = st.empty()
    status.info("Extracting inspection photos…")

    all_records = []
    progress = st.progress(0)

    for i, pdf in enumerate(uploaded_files):
        pdf_bytes = pdf.read()
        all_records.extend(extract_photos(pdf.name, pdf_bytes))
        progress.progress((i + 1) / len(uploaded_files))

    status.empty()

    df = pd.DataFrame(all_records)

    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("No duplicate inspection photos detected.")
    else:
        st.error("Duplicate inspection photos detected:")

        for md5_hash, group in duplicates.groupby("md5"):
            st.markdown(f"### Duplicate Set — MD5: `{md5_hash}`")

            cols = st.columns(len(group))
            for col, (_, row) in zip(cols, group.iterrows()):
                col.markdown(f"**{row['file']} — Page {row['page']}**")
                col.image(row["image"], use_column_width=True)
