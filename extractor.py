import pdfplumber
import pandas as pd
import io
import logging

# Suppress minor PDF parsing warnings that clutter the terminal
logging.getLogger("pdfminer").setLevel(logging.ERROR)

def extract_text_from_pdf(file_bytes):
    """Extracts text from a PDF file using pdfplumber for better table/layout retention."""
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
            text += "\n--- Page Break ---\n"
    return text

def extract_data_from_excel(file_bytes, extension):
    """Extracts data from Excel or CSV files."""
    if extension == ".xlsx":
        # Load all sheets
        dict_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        # Convert to a readable string format for Gemini
        output = ""
        for sheet_name, df in dict_df.items():
            output += f"Sheet: {sheet_name}\n"
            output += df.to_string(index=False)
            output += "\n\n"
        return output
    elif extension == ".csv":
        df = pd.read_csv(io.BytesIO(file_bytes))
        return df.to_string(index=False)
    return ""
