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
# Initialize keys
# ----------------------------------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

# full reset-safe structure
if st.button("Reset App"):
    st.session_state.clear()
    st.session_state["uploader_key"] = 1
    st.experimental_set_query_params(_="reset")
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.markdown("""
# Inspection Photo Duplicate Checker  
Upload PDFs and detect strict binary duplicate photos.
""")

# ----------------------------------------------------
# File uploader (simple, no batch logic)
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# ----------------------------------------------------
# Extract inspection photos
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

    if not uploaded_files:
        st.error("Please upload PDF files first.")
        st.stop()

    # duplicate filename detection
    filenames = [f.name for f in uploaded_files]
    duplicates_by_name = {x for x in filenames if filenames.count(x) > 1}

    if duplicates_by_name:
        st.error("⚠️ Duplicate PDF filenames detected!")
        st.warning(
            "You uploaded at least one PDF twice:\n\n" +
            "\n".join(f"- **{name}**" for name in duplicates_by_name) +
            "\n\nRemove duplicates or re-upload."
        )
        st.stop()

    # extraction progress
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

    # safety check
    if df.empty or "md5" not in df.columns:
        st.warning("⚠️ No valid inspection photos found in the uploaded PDFs.")
        st.stop()

    # duplicates
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

                buf = io.BytesIO()
                row["image"].save(buf, format="PNG")
                img_bytes = buf.getvalue()

                col.markdown(
                    f"<img src='data:image/png;base64,{base64.b64encode(img_bytes).decode()}' "
                    f"style='width:70%; max-width:250px; border-radius:6px;'>",
                    unsafe_allow_html=True
                )
