import streamlit as st
import pandas as pd
import os
import json
from dotenv import load_dotenv
import time
import extractor
import processor as processor_module

# Load environment variables
load_dotenv()

st.set_page_config(page_title="SOSV Document Extractor", layout="wide", page_icon="📊")

# SOSV Branding & CSS
st.markdown("""
    <style>
    :root {
        --sosv-navy: #071D49;
        --sosv-orange: #F68B1F;
        --sosv-light: #F8F9FA;
    }
    
    /* Force Light Theme appearance for specific elements if needed */
    .stApp {
        background-color: white;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: var(--sosv-navy) !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Buttons */
    div.stButton > button {
        background-color: var(--sosv-navy);
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    
    div.stButton > button:hover {
        background-color: var(--sosv-orange);
        color: white;
        border: none;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: var(--sosv-light);
        border-right: 1px solid #e0e0e0;
    }
    
    /* Metrics / Cards */
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }
    
    .metric-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: var(--sosv-orange);
    }
    
    .metric-label {
        font-size: 0.8rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.05rem;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 SOSV Investment Document Extractor")
st.markdown("<p style='color: #666; font-size: 1.1rem;'>Precision extraction into the canonical SOSV schema.</p>", unsafe_allow_html=True)

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
        
        start_time = time.time()
        
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
            raw_data, usage = processor.process_documents(documents)
            mapped_rows = processor.map_to_schema(raw_data)
            final_rows = processor.apply_inference(mapped_rows)
            
            # Create DataFrame with the canonical columns
            cols = processor.get_canonical_columns()
            df = pd.DataFrame(final_rows, columns=cols)
            
            # Metrics calculation
            end_time = time.time()
            duration = end_time - start_time
            
            # Cost calculation ($0.3/1M in, $2.5/1M out)
            cost_in = (usage['prompt_tokens'] / 1_000_000) * 0.30
            cost_out = (usage['candidates_tokens'] / 1_000_000) * 2.50
            total_cost = cost_in + cost_out

            # Store in session state for persistence across edits
            st.session_state['extracted_df'] = df
            # Audit log uses the first row (actual values)
            st.session_state['audit_log'] = processor.generate_audit_log(raw_data, final_rows[0], [])
            st.session_state['last_metrics'] = {
                "duration": duration,
                "cost": total_cost,
                "tokens": usage['total_tokens']
            }

if 'extracted_df' in st.session_state:
    m = st.session_state.get('last_metrics', {})
    if m:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Processing Time</div><div class="metric-value">{m["duration"]:.2f}s</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Estimated Cost</div><div class="metric-value">${m["cost"]:.4f}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Tokens Used</div><div class="metric-value">{m["tokens"]:,}</div></div>', unsafe_allow_html=True)

    st.subheader("Review & Edit Extracted Data")
    
    # Transpose for display: Fields as rows, (Value, Confidence, Source) as columns
    display_df = st.session_state['extracted_df'].T
    display_df.columns = ["Value", "Confidence", "Source"]
    
    # Track the original state to detect changes
    edited_display_df = st.data_editor(display_df, width="stretch", key="data_editor")
    
    # Check for changes and update session state (mapping back to horizontal)
    if not edited_display_df.equals(display_df):
        # Transpose back to horizontal format
        new_extracted_df = edited_display_df.T
        new_extracted_df.columns = st.session_state['extracted_df'].columns
        
        # Simple change detection for audit log
        changes = []
        for col in st.session_state['extracted_df'].columns:
            if not new_extracted_df[col].equals(st.session_state['extracted_df'][col]):
                changes.append(col)
        
        if changes:
            st.session_state['audit_log']['manual_edits'] = st.session_state['audit_log'].get('manual_edits', []) + changes
            # Update the stored DF to the edited one
            st.session_state['extracted_df'] = new_extracted_df
            st.rerun()

    # Export buttons
    col1, col2 = st.columns(2)
    with col1:
        # Export uses the canonical horizontal format
        csv_data = st.session_state['extracted_df'].to_csv(index=False)
        st.download_button("📥 Download CSV", csv_data, "extracted_data.csv", "text/csv")
    with col2:
        audit_json = json.dumps(st.session_state.get('audit_log', {}), indent=2)
        st.download_button("📋 Download Audit Log", audit_json, "audit_log.json", "application/json")
