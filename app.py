import streamlit as st
import pandas as pd
import os
import json
from dotenv import load_dotenv
import extractor
import processor as processor_module

# Load environment variables
load_dotenv()

st.set_page_config(page_title="SOSV Document Extractor", layout="wide")

st.title("📊 SOSV Investment Document Extractor")
st.markdown("""
Extract investment data from PDFs and Spreadsheets into the canonical SOSV schema.
""")

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")
    
    # Get API key from secrets or environment
    api_key = os.getenv("GOOGLE_API_KEY")
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
    except Exception:
        # Secrets not configured or missing, fall back to env var already set
        pass
    
    if api_key:
        st.success("Gemini API Key loaded.")
    else:
        st.error("Gemini API Key not found. Please set `GOOGLE_API_KEY` in Streamlit Secrets or a `.env` file.")

# File uploader
uploaded_files = st.file_uploader("Upload Investment Documents (PDF, XLSX, CSV)", accept_multiple_files=True)

if uploaded_files:
    st.info(f"Uploaded {len(uploaded_files)} files.")
    
    if st.button("🚀 Process Documents"):
        processor = processor_module.InvestmentProcessor(api_key)
        
        with st.spinner("Reading documents..."):
            documents = []
            for uploaded_file in uploaded_files:
                file_bytes = uploaded_file.read()
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                
                content = ""
                if ext == ".pdf":
                    content = extractor.extract_text_from_pdf(file_bytes)
                elif ext in [".xlsx", ".csv"]:
                    content = extractor.extract_data_from_excel(file_bytes, ext)
                
                documents.append({
                    "filename": uploaded_file.name,
                    "content": content,
                    "type": ext
                })

        with st.spinner("Analyzing with Gemini..."):
            raw_data = processor.process_documents(documents)
            mapped_rows = processor.map_to_schema(raw_data)
            final_rows = processor.apply_inference(mapped_rows)
            
            # Create DataFrame with the canonical columns
            cols = processor.get_canonical_columns()
            df = pd.DataFrame(final_rows, columns=cols)
            
            # Store in session state for persistence across edits
            st.session_state['extracted_df'] = df
            # Audit log uses the first row (actual values)
            st.session_state['audit_log'] = processor.generate_audit_log(raw_data, final_rows[0], [])

if 'extracted_df' in st.session_state:
    st.subheader("Review & Edit Extracted Data")
    
    # Track the original state to detect changes
    edited_df = st.data_editor(st.session_state['extracted_df'], num_rows="dynamic", key="data_editor")
    
    # Check for changes and update audit log
    if not edited_df.equals(st.session_state['extracted_df']):
        # Simple change detection
        changes = []
        for col in edited_df.columns:
            if not edited_df[col].equals(st.session_state['extracted_df'][col]):
                changes.append(col)
        
        if changes:
            st.session_state['audit_log']['manual_edits'] = st.session_state['audit_log'].get('manual_edits', []) + changes
            # Note: In a production app, we'd store the old vs new value here.
            # Update the stored DF to the edited one
            st.session_state['extracted_df'] = edited_df

    # Export buttons
    col1, col2 = st.columns(2)
    with col1:
        csv_data = edited_df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv_data, "extracted_data.csv", "text/csv")
    with col2:
        audit_json = json.dumps(st.session_state.get('audit_log', {}), indent=2)
        st.download_button("📋 Download Audit Log", audit_json, "audit_log.json", "application/json")
