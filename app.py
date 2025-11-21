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
# Initialize session state
# ----------------------------------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "batches" not in st.session_state:
    st.session_state["batches"] = []
if "all_files" not in st.session_state:
    st.session_state["all_files"] = []

# ----------------------------------------------------
# Reset
# ----------------------------------------------------
if st.button("Reset App"):
    for key in list(st.session_state.keys()):
        if key not in ["uploader_key"]:
            del st.session_state[key]
    st.session_state["uploader_key"] += 1
    st.experimental_set_query_params(_="reset")
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.markdown("# Inspection Photo Duplicate Checker")

# ----------------------------------------------------
# File uploader
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# ----------------------------------------------------
# Detect new batch
# ----------------------------------------------------
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]
    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# Show batch summary
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}: {len(batch)} files**")

# Undo last batch
if st.session_state["batches"]:
    if st.button("Undo Last Batch"):
        last = st.session_state["batches"].pop()
        for f in last:
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
# Duplicate check
# ----------------------------------------------------
if st.button("Run Duplicate Check"):

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    filenames = [f.name for f in st.session_state["all_files"]]
    duplicates_by_name = sorted({x for x in filenames if filenames.count(x) > 1})

    if duplicates_by_name:
        st.error("Duplicate PDF filenames detected!")
        st.warning(
            "You uploaded the same file more than once:\n\n" +
            "\n".join(f"• **{name}**" for name in duplicates_by_name) +
            "\n\nRename or remove duplicates to continue."
        )
        st.stop()

    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    status = st.info("Extracting inspection photos…")
    all_photos = []
    for pdf in st.session_state["all_files"]:
        all_photos.extend(extract_photos(pdf.name, pdf_cache[pdf.name]))
    status.empty()

    df = pd.DataFrame(all_photos)

    if df.empty:
        st.success("No inspection photos found.")
        st.stop()

    duplicates = df[df.duplicated("md5", keep=False)].sort_values("md5")

    st.subheader("Duplicate Photo Results")

    if duplicates.empty:
        st.success("No duplicates detected.")
        st.stop()

    st.error("Duplicate inspection photos detected.")

    # ----------------------------------------------------
    # CSS — True card grid layout
    # ----------------------------------------------------
    st.markdown("""
    <style>
    .dup-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 22px;
        margin-top: 20px;
    }
    .dup-card {
        background: #1f1f1f;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 14px;
        box-shadow: 0 0 8px rgba(0,0,0,0.45);
    }
    .dup-title {
        font-family: monospace;
        color: #4caf50;
        text-align: center;
        margin-bottom: 10px;
        font-size: 15px;
    }
    .dup-img {
        width: 100%;
        border-radius: 6px;
    }
    .dup-files {
        margin-top: 10px;
        color: #ddd;
        font-size: 13px;
    }
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # Card grid container
    # ----------------------------------------------------
    st.markdown("<div class='dup-grid'>", unsafe_allow_html=True)

    # For summary grouping
    grouped_sets = []

    for md5_hash, group in duplicates.groupby("md5"):

        files = sorted(set(group["file"]))
        grouped_sets.append(files)

        # Convert image to base64
        first_img = group.iloc[0]["image"]
        buf = io.BytesIO()
        first_img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        file_list_html = "".join(
            f"• {row['file']} (Pg {row['page']})<br>"
            for _, row in group.iterrows()
        )

        card_html = f"""
        <div class="dup-card">
            <div class="dup-title">{md5_hash}</div>
            <img class="dup-img" src="data:image/png;base64,{img_b64}">
            <div class="dup-files">
                <strong>Found in:</strong><br>{file_list_html}
            </div>
        </div>
        """

        st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ----------------------------------------------------
    # Relation-based summary (no duplicates)
    # ----------------------------------------------------
    st.subheader("Reports Containing Duplicate Photos (Grouped by Relation)")

    unique_groups = []
    seen_sets = set()

    for group in grouped_sets:
        key = tuple(group)
        if key not in seen_sets:
            unique_groups.append(group)
            seen_sets.add(key)

    for i, group in enumerate(unique_groups, start=1):
        st.markdown(f"### Group {i}")
        for file in group:
            st.write(f"• {file}")
