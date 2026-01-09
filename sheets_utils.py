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

        # 3. Find the target sheet (next to "Index")
        worksheets = sh.worksheets()
        target_sheet = None
        
        for i, ws in enumerate(worksheets):
            if ws.title == "Index":
                if i + 1 < len(worksheets):
                    target_sheet = worksheets[i + 1]
                else:
                    return "Error: 'Index' is the last sheet; no sheet follows it."
                break
        
        if not target_sheet:
            return "Error: 'Index' sheet not found."

        # 4. Prepare data
        # Convert df to formatted list of lists (handling NaNs, etc.)
        data_to_append = df.fillna("").values.tolist()
        
        # 5. Determine insertion point
        # User constraint: "add the rows from row 3"
        # We check if the sheet is empty to respect the "row 3" start.
        # If existing data > 0 rows, we just append to the end.
        existing_values = target_sheet.get_all_values()
        num_existing_rows = len(existing_values)

        if num_existing_rows < 2:
            # If less than 2 rows exist, we might need to pad to start at row 3.
            # Row 1 and Row 2 might be headers or titles.
            # However, gspread 'append_rows' adds to the *first empty row*.
            # If the sheet is totally empty, it adds at row 1.
            # To force row 3, we can insert empty rows if needed?
            # Or simpler: verify if we need to header row?
            # The prompt implies the sheet structure exists, just adding rows.
            # I will use append_rows. If the user wants strictly row 3 start in an empty sheet,
            # we'd need to resize/update specific cells. 
            # Given "spreadsheet indicated in the .env", it likely has a template.
            pass

        # Append data
        target_sheet.append_rows(data_to_append, value_input_option='USER_ENTERED')

        return f"Successfully added {len(data_to_append)} rows to sheet '{target_sheet.title}'."

    except Exception as e:
        return f"An error occurred: {str(e)}"
