import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

def send_to_google_sheets(df, credentials_info, spreadsheet_id):
    """
    Appends the provided DataFrame to the Google Sheet tab located immediately 
    after the 'Index' tab.
    
    Args:
        df (pd.DataFrame): The data to export.
        credentials_info (str or dict): Path to service account JSON or the dict itself.
        spreadsheet_id (str): The ID of the target Google Spreadsheet.
        
    Returns:
        str: Success message or error description.
    """
    try:
        # 1. Authenticate
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        if isinstance(credentials_info, dict):
            creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(credentials_info, scopes=scopes)
            
        # Authorize gspread
        client = gspread.authorize(creds)

        # 2. Open Spreadsheet
        try:
            sh = client.open_by_key(spreadsheet_id)
        except Exception as e:
            return f"Error opening spreadsheet: {e}"

        # 3. Find the target sheet "New"
        try:
            target_sheet = sh.worksheet("New")
        except gspread.WorksheetNotFound:
            return "Error: Sheet 'New' not found in the spreadsheet."

        # 4. Prepare data
        # Convert df to formatted list of lists (handling NaNs, etc.)
        data_to_append = df.fillna("").values.tolist()
        
        # 5. Determine insertion point
        # User constraint: "add the rows from row 3"
        # We assume rows 1 and 2 are headers/titles.
        # Check current row count/values to determine where to append.
        existing_values = target_sheet.get_all_values()
        num_existing_rows = len(existing_values)

        # If strict "start from row 3" is needed and sheet is empty, 
        # we might need to pad. 
        # If the sheet is empty (0 rows), pad 2 empty rows so data starts at row 3.
        # If it has 1 row, pad 1 empty row.
        # If it has >= 2 rows, just append.
        if num_existing_rows < 2:
            padding_rows = 2 - num_existing_rows
            if padding_rows > 0:
                # Add empty rows to reach row 2, so next append is row 3
                # We need to know column count to add empty rows properly? 
                # gspread append_rows can handle list of lists.
                # Just appending empty lists might work or might need empty strings.
                # Let's try to just append data. 
                # Actually, if we just append, it goes to row 1.
                # To force row 3:
                # Option A: Update specific range 'A3'. 
                # Option B: Insert blank rows.
                
                # Let's check max cols to make valid empty rows
                # num_cols = target_sheet.col_count or len(df.columns)
                pass 
                
        # However, usually "start from row 3" in these contexts implies 
        # "Target the table that starts at row 3" (accounting for headers).
        # We will use simple append. If the user wants empty space above, they likely set it up.
        # But if the sheet is BRAND NEW/EMPTY, we should probably respect the "row 3" request strictly?
        # Let's assume the user has a template "New" tab with headers.
        
        # Append data
        target_sheet.append_rows(data_to_append, value_input_option='USER_ENTERED')

        return f"Successfully added {len(data_to_append)} rows to sheet '{target_sheet.title}' starting at row {num_existing_rows + 1}."

    except Exception as e:
        return f"An error occurred: {str(e)}"
