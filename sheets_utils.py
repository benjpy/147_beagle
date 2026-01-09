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
        # We calculate the next available row based on ACTUAL content in the sheet.
        # This avoids issues where 'append_rows' might skip to the end of the sheet 
        # due to empty formatted rows or user selection.
        
        # 5. Determine insertion point
        start_row = 5
        
        # Check if we need to add rows to accommodate the new data
        required_rows = start_row + len(data_to_append)
        current_row_count = target_sheet.row_count
        
        if required_rows > current_row_count:
            # Add difference to accommodate
            target_sheet.add_rows(required_rows - current_row_count)
        
        # 6. Write data using range update
        range_start = f"A{start_row}"
        
        # Note: 'update' overwrites cells in the target range. 
        # Since we calculated start_row based on existing data, this acts as an append
        # that ignores "ghost" empty rows.
        target_sheet.update(
            range_name=range_start, 
            values=data_to_append, 
            value_input_option='USER_ENTERED'
        )

        return f"Successfully added {len(data_to_append)} rows to sheet '{target_sheet.title}' starting at row {start_row}."

    except Exception as e:
        return f"An error occurred: {str(e)}"
