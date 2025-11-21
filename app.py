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
# Session Keys
# ----------------------------------------------------
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "batches" not in st.session_state:
    st.session_state["batches"] = []
if "all_files" not in st.session_state:
    st.session_state["all_files"] = []

# ----------------------------------------------------
# Reset App
# ----------------------------------------------------
if st.button("Reset App"):
    for key in list(st.session_state.keys()):
        if key not in ["uploader_key"]:
            del st.session_state[key]
    st.session_state["uploader_key"] += 1
    st.rerun()

# ----------------------------------------------------
# Title
# ----------------------------------------------------
st.markdown("# Inspection Photo Duplicate Checker")

# ----------------------------------------------------
# File Upload
# ----------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload PDF Reports (multiple batches allowed)",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state['uploader_key']}"
)

# ----------------------------------------------------
# Batch Detection
# ----------------------------------------------------
if uploaded_files:
    new_files = [f for f in uploaded_files if f not in st.session_state["all_files"]]
    if new_files:
        st.session_state["batches"].append(new_files)
        st.session_state["all_files"].extend(new_files)

# Show Batches
if st.session_state["batches"]:
    st.subheader("Uploaded Batches:")
    for i, batch in enumerate(st.session_state["batches"], start=1):
        st.write(f"**Batch {i}: {len(batch)} files**")

# Undo Batch
if st.session_state["batches"]:
    if st.button("Undo Last Batch"):
        last = st.session_state["batches"].pop()
        for f in last:
            st.session_state["all_files"].remove(f)
        st.session_state["uploader_key"] += 1
        st.rerun()

# ----------------------------------------------------
# Extract Photos
# ----------------------------------------------------
def extract_photos(pdf_name, pdf_bytes):
    out = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for img in page.get_images(full=True):

            xref = img[0]
            data = doc.extract_image(xref)
            img_bytes = data["image"]

            image = Image.open(io.BytesIO(img_bytes))
            w, h = image.size

            if w >= 300 and h >= 150:  
                md5 = hashlib.md5(img_bytes).hexdigest()
                out.append({
                    "file": pdf_name,
                    "page": page_idx,
                    "md5": md5,
                    "image": image,
                    "img_bytes": img_bytes
                })
    return out

# ----------------------------------------------------
# Run Duplicate Check
# ----------------------------------------------------
if st.button("Run Duplicate Check"):

    if not st.session_state["all_files"]:
        st.error("Please upload files first.")
        st.stop()

    # Duplicate filename protection
    filenames = [f.name for f in st.session_state["all_files"]]
    duplicated_filenames = {name for name in filenames if filenames.count(name) > 1}

    if duplicated_filenames:
        st.error("⚠️ Duplicate PDF filenames detected!")
        st.warning(
            "You uploaded the same file more than once:\n\n" +
            "\n".join(f"• **{name}**" for name in duplicated_filenames) +
            "\n\nRename or remove duplicates to continue."
        )
        st.stop()

    pdf_cache = {f.name: f.read() for f in st.session_state["all_files"]}

    status = st.info("Extracting inspection photos...")
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
    # CSS for Card Grid
    # ----------------------------------------------------
    st.markdown("""
    <style>
    .dup-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 18px;
        margin-top: 20px;
    }
    .dup-card {
        width: 320px;
        background: #1f1f1f;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 12px;
        box-shadow: 0 0 8px rgba(0,0,0,0.4);
    }
    .dup-title {
        font-family: monospace;
        color: #4caf50;
        text-align: center;
        margin-bottom: 8px;
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
    # RENDER GRID
    # ----------------------------------------------------
    st.markdown("<div class='dup-grid'>", unsafe_allow_html=True)

    # Grouping logic
    report_groups = []

    def merge_group(new_set):
        for group in report_groups:
            if group & new_set:
                group |= new_set
                return
        report_groups.append(set(new_set))

    # CSV rows list
    csv_rows = []

    for md5_hash, group in duplicates.groupby("md5"):

        files = set(group["file"].unique())
        merge_group(files)

        first_row = group.iloc[0]
        first_img = first_row["image"]

        buf = io.BytesIO()
        first_img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode()

        file_list_html = "".join(
            f"• {row['file']} (Pg {row['page']})<br>"
            for _, row in group.iterrows()
        )

        # ---- Add rows to CSV ----
        for _, row in group.iterrows():
            csv_rows.append({
                "md5": md5_hash,
                "image_base64": img_b64,
                "report": row["file"],
                "page": row["page"]
            })

        card_html = f"""
        <div class="dup-card">
            <div class="dup-title">{md5_hash}</div>
            <img class="dup-img" src="data:image/png;base64,{img_b64}">
            <div class="dup-files"><strong>Found in:</strong><br>{file_list_html}</div>
        </div>
        """

        st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ----------------------------------------------------
    # SUMMARY GROUPS
    # ----------------------------------------------------
    st.subheader("Reports Containing Duplicate Photos (Grouped by Relation)")

    grouped_csv_rows = []

    for i, group in enumerate(report_groups, start=1):
        st.markdown(f"### Group {i}")
        for file in sorted(group):
            st.write(f"• {file}")
            grouped_csv_rows.append({
                "group_id": i,
                "report": file
            })

    # ----------------------------------------------------
    # EXPORT CSV
    # ----------------------------------------------------
    st.subheader("Export Results")

    df_csv = pd.DataFrame(csv_rows)
    df_groups = pd.DataFrame(grouped_csv_rows)

    # merge both sections separated with indicator
    output = io.StringIO()
    output.write("Duplicate Photos\n")
    df_csv.to_csv(output, index=False)
    output.write("\n\nGrouped Summary\n")
    df_groups.to_csv(output, index=False)

    st.download_button(
        "📥 Download CSV Report",
        output.getvalue(),
        "duplicate_photo_report.csv",
        "text/csv"
    )
