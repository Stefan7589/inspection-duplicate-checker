
import streamlit as st
import fitz
import hashlib
from PIL import Image
import io
import pandas as pd

if st.button("🔄 Reset App"):
    st.session_state.clear()
    st.rerun()

st.set_page_config(page_title="Inspection Photo Duplicate Checker", layout="wide")

st.markdown("""# 🟩 Inspection Photo Duplicate Checker  
Upload PDFs and detect strict binary duplicate photos.  
""")

uploaded_files = st.file_uploader(
    "📤 Upload PDF Reports",
    type=["pdf"],
    accept_multiple_files=True
)

def extract_photos(pdf_name, pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    output = []
    for page_index in range(len(doc)):
        page = doc[page_index]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_img = doc.extract_image(xref)
            img_bytes = base_img["image"]
            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size
            # Filter real inspection photos
            if w >= 650 and h >= 450:
                md5 = hashlib.md5(img_bytes).hexdigest()
                output.append({
                    "file": pdf_name,
                    "page": page_index,
                    "width": w,
                    "height": h,
                    "md5": md5,
                    "image": image
                })
    return output

if st.button("▶️ Run Duplicate Check"):
    if not uploaded_files:
        st.error("Please upload files first.")
        st.stop()

    st.info("Extracting inspection photos…")
    all_records = []

    progress = st.progress(0)
    for i, pdf in enumerate(uploaded_files):
        all_records.extend(extract_photos(pdf.name, pdf.read()))
        progress.progress((i+1)/len(uploaded_files))

    df = pd.DataFrame(all_records)

    st.subheader("📸 Extracted Inspection Photos")
    st.write(df[["file", "page", "width", "height", "md5"]])

    st.subheader("🔍 Duplicate Photo Groups")
    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    if duplicates.empty:
        st.success("✅ No duplicate inspection photos detected.")
    else:
        st.error("⚠️ Duplicate inspection photos found!")
        for md5_hash, group in duplicates.groupby("md5"):
            st.markdown(f"### 🟦 Duplicate Set — MD5: `{md5_hash}`")
            cols = st.columns(len(group))
            for col, (_, row) in zip(cols, group.iterrows()):
                col.markdown(f"**{row['file']} — Page {row['page']}**")
                col.image(row["image"], use_column_width=True)
