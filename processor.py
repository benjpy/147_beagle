import google.generativeai as genai
import json
import os
import pandas as pd

class InvestmentProcessor:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp') # Reverting to 2.0 exp as 2.5 was invalid
        self.prompt_template = self._load_prompt()
        self.categories = {
            "CRM Status": ["Need more info", "Needs to be added", "Added", "On CRM but needs correcting"],
            "SOSV participated?": ["Yes", "No"],
            "Deal currency": ["CAD", "CHF", "EUR", "USD", "GBP", "JPY", "SGD", "HKD"],
            "Security Name": ["SPA", "OPA", "Grant", "Prize", "CPN", "SAFE", "IndieBio Therapeutics Track ACE 1", "CLN", "IndieBio Therapeutics Track ACE 2", "IndieBio Therapeutics Track ACE 3", "IndieBio Therapeutics Track ACE 4", "IndieBio ACE", "ASA", "Genesis Consortium Convertible", "Promissory Loan Note", "Loan Agreement", "CLA", "IndieBio SPA", "IndieBio SAFE", "HAX FSCA", "Collaboration Agreement"],
            "SOSV Category": ["Program Deal", "Follow-on", "Grants&Prizes"],
            "Equity or Notes": ["Equity", "Notes", "N/A"],
            "Round": ["Series A", "Seed", "Grant", "Prize", "Pre-Seed", "Seed Extension", "Pre-Seed Extension", "Program Deal", "Opportunistic CLNs/SAFEs", "Genesis Consortium", "Bridge To Series A", "Bridge To Seed", "Tx Track", "HAX/IndieBio Program Deal"]
        }

    def _load_prompt(self):
        try:
            with open("prompts.txt", "r") as f:
                return f.read()
        except FileNotFoundError:
            return "Extract investment data from the following text and return as JSON: {text}"

    def get_canonical_columns(self):
        # Load columns from the reference CSV
        try:
            df = pd.read_csv("Alex New Company Form - Closed.csv", nrows=0)
            cols = df.columns.tolist()
            # The first column is unnamed (Company Name)
            if cols[0].startswith("Unnamed"):
                cols[0] = "Company Name"
            return cols
        except:
            return []

    def process_documents(self, documents):
        """
        documents: List of dicts {'filename': str, 'content': str, 'type': str}
        """
        # 1. Combine content for Gemini
        combined_content = ""
        for doc in documents:
            combined_content += f"=== FILE: {doc['filename']} ===\n{doc['content']}\n\n"

        # 2. Call Gemini
        prompt = self.prompt_template.replace("{text}", combined_content)
        response = self.model.generate_content(prompt)
        
        # 3. Parse JSON from response
        usage = getattr(response, 'usage_metadata', None)
        token_usage = {
            "prompt_tokens": usage.prompt_token_count if usage else 0,
            "candidates_tokens": usage.candidates_token_count if usage else 0,
            "total_tokens": usage.total_token_count if usage else 0
        }

        try:
            # Simple cleanup for Gemini JSON formatting
            json_str = response.text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            extracted_data = json.loads(json_str)
        except Exception as e:
            print(f"Error parsing Gemini response: {e}")
            extracted_data = {}

        return extracted_data, token_usage

    def map_to_schema(self, extracted_data):
        """Maps Gemini JSON to 4 rows in the 47-column CSV schema: (Value, Confidence, Reference, Document)."""
        columns = self.get_canonical_columns()
        
        row_val = {col: "" for col in columns}
        row_conf = {col: "" for col in columns}
        row_ref = {col: "" for col in columns}
        row_doc = {col: "" for col in columns}
        
        # Mapping for the complex CSV headers
        mapping = {
            "Company Name": ["Company Name"],
            "Round Identifier": ["Round Identifier"],
            "FA Code": ["FA Code"],
            "CRM Status": ["CRM Status"],
            "SOSV participated?": ["SOSV participated?"],
            "Investors": ["Investors"],
            "Deal Currency (Symbol)": ["Deal Currency (Symbol)"],
            "Total Fundraising \n(In Deal Currency) ": ["Total Fundraising (Deal Currency)"],
            "SOSV Total \n(In Deal Currency)": ["SOSV Total (Deal Currency)"],
            "SOSV IV/V \n(In Deal Currency)": ["SOSV IV/V (Deal Currency)"],
            "SOSV Decarb\n(In Deal Currency)": ["SOSV Decarb (Deal Currency)"],
            "External Funding (In Deal Currency) ": ["External Funding (Deal Currency)"],
            "Round": ["Round"],
            "Security Name": ["Security Name"],
            "Date of Closing": ["Date of Closing"],
            "a. Pre-Money Valuation \n(in Deal Currency)": ["Pre-Money Valuation (Deal Currency)"],
            "b. Post-Money Valuation \n(in Deal Currency)": ["Post-Money Valuation (Deal Currency)"],
            "c. Pre-Money Valuation Cap \n(in Deal Currency)": ["Pre-Money Valuation Cap (Deal Currency)"],
            "d. Post-Money Valuation Cap \n(in Deal Currency)": ["Post-Money Valuation Cap (Deal Currency)"],
            "Discount (%)": ["Discount (%)"],
            "Interest (%)": ["Interest (%)"],
            "Equity or Notes": ["Equity or Notes"]
        }
        
        for schema_col, gemini_keys in mapping.items():
            for key in gemini_keys:
                if key in extracted_data:
                    field_data = extracted_data[key]
                    val = ""
                    if isinstance(field_data, dict):
                        val = field_data.get("value")
                        # Split source into Reference and Document
                        sources = field_data.get("sources", [])
                        if not sources and ("source_file" in field_data or "file" in field_data):
                            # Fallback for old/single source format
                            sources = [{
                                "file": field_data.get("source_file", field_data.get("file", "")),
                                "detail": field_data.get("source_detail", field_data.get("detail", "")),
                                "type": field_data.get("source_type", field_data.get("type", ""))
                            }]
                        
                        # --- Conflict Handling ---
                        is_conflict = field_data.get("is_conflict", False)
                        base_conf = self.calculate_confidence(field_data)
                        if is_conflict:
                            row_conf[schema_col] = f"🔴 {base_conf}"
                        else:
                            row_conf[schema_col] = base_conf

                        # --- Reference Formatting ---
                        # Group details by filename
                        file_details = {} # filename -> list of details
                        
                        for s in sources:
                            fname = s.get("file", "").strip()
                            detail = s.get("detail", "").strip()
                            if fname:
                                if fname not in file_details:
                                    file_details[fname] = []
                                if detail:
                                    # Specific handling for Page/Article checks if needed, 
                                    # but generally just cleaning "Sheet:" / "Cell:" prefixes
                                    clean_detail = detail.replace("Sheet: ", "").replace("Cell: ", "").replace("Cells: ", "")
                                    
                                    # Check for Page/Article pattern (simple heuristic)
                                    # If detail has "Page X" and "Article Y", we might want to join them differently
                                    # For now, relying on the requested " > " if it looks hierarchical, otherwise just add
                                    if "Article" in clean_detail and "Page" in clean_detail:
                                         clean_detail = clean_detail.replace(", Article", " > Article")

                                    file_details[fname].append(clean_detail)

                        formatted_refs = []
                        if is_conflict:
                             formatted_refs.append("🔴 Conflict Detected")

                        for fname, details in file_details.items():
                            if details:
                                # "Seed-round... > Cells A2:A5 + A8:A9"
                                joined_details = " + ".join(details)
                                formatted_refs.append(f"{fname} > {joined_details}")
                            else:
                                formatted_refs.append(fname)
                        
                        row_ref[schema_col] = "\n".join(formatted_refs)

                        # --- Document Formatting ---
                        # Deduplicate filenames but preserve order
                        row_doc[schema_col] = "\n".join(file_details.keys())
                    else:
                        val = field_data
                    
                    # Ensure val is a string (join lists, convert others)
                    if isinstance(val, list):
                        # Join with ; and remove any brackets/quotes if present
                        row_val[schema_col] = "; ".join(map(lambda x: str(x).strip(" []\"'"), val))
                    elif val is None:
                        row_val[schema_col] = ""
                    else:
                        row_val[schema_col] = str(val).strip(" []\"'")
                    break
        
        # Label the rows in the first column (Company Name)
        company_name = row_val.get("Company Name", "Unknown")
        row_conf["Company Name"] = f"{company_name} (Confidence)"
        row_ref["Company Name"] = f"{company_name} (Reference)"
        row_doc["Company Name"] = f"{company_name} (Document)"

        # Apply strict categorical normalization
        for row in [row_val]: # Only normalize the actual values
            for col, allowed in self.categories.items():
                schema_col = self._map_category_to_schema_name(col)
                if schema_col and row.get(schema_col):
                    val = str(row[schema_col]).strip()
                    if val not in allowed:
                        # Simple case-insensitive match
                        match = next((a for a in allowed if a.lower() == val.lower()), None)
                        if match:
                            row[schema_col] = match
                        # Optional: Add fuzzy matching here if needed

        return [row_val, row_conf, row_ref, row_doc]

    def _map_category_to_schema_name(self, cat):
        """Maps internal category name to specific CSV header."""
        mapping = {
            "CRM Status": "CRM Status",
            "SOSV participated?": "SOSV participated?",
            "Deal currency": "Deal Currency (Symbol)",
            "Security Name": "Security Name",
            "SOSV Category": "SOSV Category",
            "Equity or Notes": "Equity or Notes",
            "Round": "Round"
        }
        return mapping.get(cat)

    def calculate_confidence(self, field_data):
        """Applies PRD rubric based on source type(s)."""
        if not field_data or not isinstance(field_data, dict):
            return ""
        
        val = field_data.get("value")
        if val is None or str(val).strip() == "":
            return ""

        sources = field_data.get("sources", [])
        if not sources:
            # Fallback for single source
            source_type = str(field_data.get("source_type", field_data.get("type", ""))).upper()
            if source_type == "PDF": return "95%"
            if source_type in ["EXCEL", "CSV"]: return "85%"
            return "50%"
        
        # Determine highest confidence from all sources
        confidences = []
        for s in sources:
            stype = str(s.get("type", "")).upper()
            if stype == "PDF": confidences.append(95)
            elif stype in ["EXCEL", "CSV"]: confidences.append(85)
            else: confidences.append(50)
        
        if not confidences: return "50%"
        return f"{max(confidences)}%"

    def apply_inference(self, rows):
        """Infers values like Post-money = Pre-money + Total Fundraising and USD mirroring."""
        if not rows or len(rows) < 4: return rows
        row_val = rows[0]
        row_conf = rows[1]
        row_ref = rows[2]
        row_doc = rows[3]

        # Helper to clean currency strings and convert to float
        def clean_val(val):
            if not val or str(val).strip() == "": return None
            try:
                # Remove common currency symbols and commas
                s = str(val).replace("$", "").replace("£", "").replace("€", "").replace(",", "").strip()
                return float(s)
            except:
                return None

        total = clean_val(row_val.get("Total Fundraising \n(In Deal Currency) "))
        pre = clean_val(row_val.get("a. Pre-Money Valuation \n(in Deal Currency)"))
        post = clean_val(row_val.get("b. Post-Money Valuation \n(in Deal Currency)"))

        # Inference: Post = Pre + Total
        if post is None and pre is not None and total is not None:
            row_val["b. Post-Money Valuation \n(in Deal Currency)"] = pre + total
            row_conf["b. Post-Money Valuation \n(in Deal Currency)"] = "75% (Inferred)"
            row_ref["b. Post-Money Valuation \n(in Deal Currency)"] = "Derived: Pre-Money + Total"
            row_doc["b. Post-Money Valuation \n(in Deal Currency)"] = "N/A (Inferred)"
        
        # Inference: USD Normalization
        currency = str(row_val.get("Deal Currency (Symbol)", "")).upper()
        if "$" in currency or "USD" in currency:
            # Copy all deal currency values to USD counterparts for all rows
            usd_mapping = {
                "Total Fundraising \n(In Deal Currency) ": "Total Fundraising \n($USD)",
                "SOSV Total \n(In Deal Currency)": "SOSV Total \n($USD)",
                "External Funding (In Deal Currency) ": "External Funding \n($USD)",
                "a. Pre-Money Valuation \n(in Deal Currency)": "a. Pre-Money Valuation\n($USD)",
                "b. Post-Money Valuation \n(in Deal Currency)": "b. Post-Money Valuation \n($USD)",
                "c. Pre-Money Valuation Cap \n(in Deal Currency)": "c. Pre-Money Valuation Cap \n($USD) ",
                "d. Post-Money Valuation Cap \n(in Deal Currency)": "d. Post-Money Valuation Cap\n($USD)"
            }
            for deal_col, usd_col in usd_mapping.items():
                for r in rows:
                    if deal_col in r and r[deal_col]:
                        r[usd_col] = r[deal_col]

        # Final pass: Date formatting for 'Date of Closing'
        # Target format: M/D/YYYY
        date_col = "Date of Closing"
        if row_val.get(date_col):
            try:
                date_val = str(row_val[date_col]).strip()
                # Use pandas to parse and then format
                dt = pd.to_datetime(date_val)
                row_val[date_col] = f"{dt.month}/{dt.day}/{dt.year}"
            except:
                pass # Fallback to whatever Gemini gave us

        return rows

    def generate_audit_log(self, original_data, final_data, conflicts):
        """Generates the structured audit log."""
        log = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "extraction_results": {},
            "final_row": final_data,
            "conflicts": conflicts
        }
        
        # Store metadata for each field
        for field, data in original_data.items():
            if isinstance(data, dict):
                log["extraction_results"][field] = {
                    "value": data.get("value"),
                    "source": data.get("source"),
                    "confidence": self.calculate_confidence(data)
                }
        
        return log
