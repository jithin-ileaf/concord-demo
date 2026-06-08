from copy import deepcopy
import json
from pyairtable import Api


# pro_accepted_list = [
#     'ACEMLA', 'AllTrack', 'MCOS', 'AMRA', 'APRA', 'ASCAP', 'BMI', 'CMRRA',
#     'GMR', 'IMRO', 'JASRAC', 'KODA', 'MCPSI', 'PPCA', 'PPI', 'PPL',
#     'Pro Music Rights', 'PRS', 'Re:Sound', 'SACD', 'SACEM', 'SESAC',
#     'SOCAN', 'SoundExchange'
# ]


# def update_extracted_value(json_data,
#                            choice_of_law_mapping=None,
#                            currency_mapping=None,
#                            pro_accepted_list=pro_accepted_list):
#     # Current PRO
#     if "Current PRO" in json_data and isinstance(json_data["Current PRO"], dict) and "Extracted Value" in json_data["Current PRO"]:
#         original_value = json_data["Current PRO"]["Extracted Value"]
#         if original_value not in pro_accepted_list and original_value not in ("N/A", "Not specified", "Not specified in APA"):
#             json_data["Current PRO"]["Extracted Value"] = "Other"

#     return json_data


def populate_template(template, source):
    """
    Recursively walk through the template JSON.
    If a leaf value is "" and the same key exists in source,
    replace it with the FULL object from source.
    """
    if isinstance(template, dict):
        populated = {}

        for key, value in template.items():
            # Case 1: Leaf node and key exists in source
            if value == "" and key in source:
                populated[key] = deepcopy(source[key])

            # Case 2: Nested dictionary → recurse
            else:
                populated[key] = populate_template(value, source)

        return populated

    # Non-dict values are returned unchanged
    return template


def flatten_extracted_data(data_dict):
    """
    Flatten nested JSON structure for Airtable upload.
    Recursively extracts all fields from nested categories and converts them 
    into a flat dictionary with field names and extracted values.
    
    Applies proper type conversions for numeric fields to ensure Airtable compatibility.

    Args:
        data_dict: Dictionary containing nested field data (with categories like "General", "Asset Details", etc.)

    Returns:
        Flattened dictionary ready for Airtable (no categories, just individual fields)
    """
    # NOTE: All fields are sent as plain strings/text
    # Multi-select logic removed to avoid LLM inconsistencies with determining valid options

    # List of fields to skip (e.g., checkbox fields that need special handling)
    skip_fields = [
        "Distribution Rights Acquired"
    ]

    # Numeric fields that require type conversion
    # Field 16: Minimum Delivery Commitment (integer)
    # Field 18: Copyright Percentage Assigned (decimal 0-100)
    numeric_fields = {
        "Minimum Delivery Commitment": "integer",  # Field 16
        "Copyright Percentage Assigned": "number"  # Field 18
    }

    flattened = {}

    def clean_value(value):
        """
        Clean extracted values by removing trailing punctuation and
        normalizing common patterns.
        """
        if not isinstance(value, str):
            return value
        
        # Strip whitespace
        cleaned = value.strip()
        
        # Remove trailing periods, commas, semicolons
        while cleaned and cleaned[-1] in '.,:;':
            cleaned = cleaned[:-1].strip()
        
        return cleaned

    def convert_numeric_value(field_name, value, field_type):
        """
        Convert a value to the appropriate numeric type for Airtable.
        
        Args:
            field_name: Name of the field
            value: The value to convert
            field_type: Type of conversion ('integer' or 'number')
            
        Returns:
            Converted numeric value or None if conversion fails/value is invalid
        """
        # Handle None, empty strings, and non-string/non-numeric values
        if value is None or value == "":
            return None
        
        # Check for explicit null values
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ("n/a", "not specified", "not applicable", "none", ""):
                return None
        
        # Try to convert to number
        try:
            if field_type == "integer":
                # Convert to integer
                numeric_value = int(float(str(value).strip()))
                return numeric_value
            elif field_type == "number":
                # Convert to float
                numeric_value = float(str(value).strip())
                return numeric_value
        except (ValueError, TypeError, AttributeError):
            # Conversion failed - return None to skip or use string fallback
            print(f"  ⚠ Could not convert '{field_name}': '{value}' to {field_type}")
            return None
        
        return None

    def process_field(field_name, field_data):
        """Helper function to process a single field."""
        # Skip fields that are in the skip list
        if field_name in skip_fields:
            return

        if isinstance(field_data, dict) and "Extracted Value" in field_data:
            extracted_value = field_data["Extracted Value"]
            
            # Clean the extracted value if it's a string
            if isinstance(extracted_value, str):
                extracted_value = clean_value(extracted_value)
            
            # Apply type conversion for numeric fields
            if field_name in numeric_fields:
                field_type = numeric_fields[field_name]
                converted_value = convert_numeric_value(field_name, extracted_value, field_type)
                flattened[field_name] = converted_value
            else:
                # Store the cleaned extracted value directly as plain string/text
                flattened[field_name] = extracted_value
        elif isinstance(field_data, dict):
            # Recursively process nested dictionaries (categories)
            for nested_field_name, nested_field_data in field_data.items():
                process_field(nested_field_name, nested_field_data)
        else:
            # Store primitive values as-is (or apply conversion if numeric field)
            if field_name in numeric_fields:
                field_type = numeric_fields[field_name]
                converted_value = convert_numeric_value(field_name, field_data, field_type)
                flattened[field_name] = converted_value
            else:
                flattened[field_name] = field_data

    # Process all top-level fields/categories
    for field_name, field_data in data_dict.items():
        process_field(field_name, field_data)

    return flattened


def upload_to_airtable(filename, json_file, airtable_api_key=None, airtable_base_id=None, airtable_table_name=None, contract_id=None):
    """
    Upload contract data to a single Airtable table.
    All fields are flattened and uploaded as one record.

    Args:
        filename: Name of the contract
        json_file: JSON string of the extracted contract data
        airtable_api_key: Airtable API key
        airtable_base_id: Airtable Base ID
        airtable_table_name: Airtable table name
        contract_id: Contract ID from MongoDB (optional)

    Returns:
        Dictionary with record_id and catalog name
    """
    if not all([airtable_api_key, airtable_base_id, airtable_table_name]):
        print("Warning: Airtable credentials not configured. Skipping upload.")
        return None

    try:
        json_data = json.loads(json_file)

        api = Api(airtable_api_key)
        catalog_name = None

        # Extract Catalog name for logging
        if "Catalog" in json_data:
            catalog_data = json_data["Catalog"]
            if isinstance(catalog_data, dict) and "Extracted Value" in catalog_data:
                catalog_name = catalog_data["Extracted Value"]
            else:
                catalog_name = catalog_data

        print(f"\n📤 Uploading {filename} to Airtable table '{airtable_table_name}'...")
        print("=" * 50)

        # Flatten all fields into a single record
        record_data = flatten_extracted_data(json_data)

        # Add Links field if contract_id is provided
        if contract_id:
            record_data["Links"] = f"http://52.203.82.123/get_contract/{contract_id}"

        # Upload to the single table
        table = api.table(airtable_base_id, airtable_table_name)
        
        try:
            record = table.create(record_data)
            print(f"  ✓ Record created (ID: {record['id']})")
            print("=" * 50)
            print(f"✓ Successfully uploaded to '{airtable_table_name}'\n")

            return {
                "record_id": {airtable_table_name: record['id']},
                "agreement_name": catalog_name
            }
        except Exception as upload_error:
            # If upload fails, provide detailed error information
            error_str = str(upload_error)
            print(f"\n✗ Upload failed: {error_str}")
            print("=" * 50)
            
            # Try to extract field name from error message
            import re
            field_match = re.search(r'Field "([^"]+)"', error_str)
            
            if field_match:
                problematic_field = field_match.group(1)
                print(f"\n⚠ Problematic field identified: {problematic_field}")
                
                if problematic_field in record_data:
                    print(f"   Value: {record_data[problematic_field]}")
                    print(f"\n🔄 Attempting upload without the problematic field...")
                    
                    # Remove the problematic field and try again
                    cleaned_data = {k: v for k, v in record_data.items() if k != problematic_field}
                    
                    try:
                        record = table.create(cleaned_data)
                        print(f"  ✓ Record created (ID: {record['id']})")
                        print(f"  ⚠ Skipped field: {problematic_field}")
                        print("=" * 50)
                        
                        return {
                            "record_id": {airtable_table_name: record['id']},
                            "agreement_name": catalog_name,
                            "skipped_fields": [problematic_field],
                            "warning": f"Field '{problematic_field}' was skipped due to error"
                        }
                    except Exception as retry_error:
                        print(f"  ✗ Retry also failed: {str(retry_error)}")
                        print("=" * 50)
            else:
                print("\n⚠ Could not identify specific problematic field from error")
                print("=" * 50)
            
            return None

    except Exception as e:
        print(f"✗ Error uploading to Airtable: {str(e)}")
        print(f"   Base ID: {airtable_base_id}, Table: {airtable_table_name}")
        return None


# def update_amendment_changes_table(
#     frontend_url,
#     contract_id,
#     agreement_name=None,
#     airtable_api_key=None,
#     airtable_base_id=None,
#     table_name="Contract Utilities"
# ):
#     """
#     Update the Contract Utilities table in Airtable with the contract_id.
#     If the 'Links' column doesn't exist, it will be created automatically
#     when the first record is inserted.

#     Args:
#         frontend_url: Frontend URL for constructing the link
#         contract_id: The contract ID to add to the Links column
#         agreement_name: The agreement name to add to the Contract column
#         airtable_api_key: Airtable API key
#         airtable_base_id: Airtable Base ID
#         table_name: Name of the table (default: "Contract Utilities")

#     Returns:
#         Record ID if successful, None otherwise
#     """
#     if not all([airtable_api_key, airtable_base_id, contract_id]):
#         print("Warning: Missing required parameters for Contract Utilities update.")
#         return None

#     try:
#         api = Api(airtable_api_key)
#         table = api.table(airtable_base_id, table_name)
#         link = f"{frontend_url}/{contract_id}"

#         # Create record with contract_id in Links field and agreement_name in Contract field
#         record_data = {
#             "Link": link,
#             "Amendment Changes": ""  # Leave empty as specified
#         }

#         # Add Contract field if agreement_name is provided
#         if agreement_name:
#             record_data["Contract"] = agreement_name
#             print(f"  → Adding Contract field to Contract Utilities: {agreement_name}")

#         # Create new record
#         record = table.create(record_data)
#         print(f"✓ Contract Utilities: Added contract_id {contract_id} (Record ID: {record['id']})")
#         return record['id']

#     except Exception as e:
#         print(f"✗ Error updating Contract Utilities table: {str(e)}")
#         return None


# Template for PW APA contracts (flat - all fields map to columns in a single Airtable table)
concord_template = {
  "General": {
    "Catalog": "",
    "General Rights Tags": "",
    "Acquisition Summary": "",
    "Rights Status": "",
    "Additional Acquisition Summary Details": "",
    "Date of Acquisition Agreement": "",
    "Cash Date": "",
    "PW Business Affairs Contact": "",
    "PW Outside Counsel": "",
    "Seller Parties (Individual)": "",
    "Seller Parties (Other)": "",
    "Seller Counsel": "",
    "Seller Personal Manager": "",
    "Seller Business Manager": "",
    "Purchaser": "",
    "Holdbacks": "",
    "Right of First Negotiation / Matching Rights": "",
    "Additional Purchase Price": "",
    "Press Releases / Public Announcements": "",
    "Restrictions on Seller": "",
    "Additional Purchaser Obligations": "",
    "Additional Seller Obligations": "",
    "Governing Law of Acquisition Agreement": "",
    "Jurisdiction and Venue for Acquisition Agreement Disputes": "",
    "Indemnification": "",
    "Additional Notes": "",
  },
  "Asset Details": {
    "PW Acquired Interest (%)": "",
    "Seller Retained Interest (%)": "",
    "Rights Acquired (By Type)": "",
    "Excluded Assets and/or Excluded Rights": "",
    "Income Sources": "",
    "Current PRO": "",
    "Current NRO": "",
    "Current Trademark Portfolio": "",
  },
  "Post-Closing Asset Management": {
    "Go-Forward Arrangements": "",
    "Possible Additional Rights": "",
    "Exclusivity Restrictions": "",
    "Other (Post-Closing)": "",
  },
  "Distribution Details": {
    "Distribution Rights Acquired": "",
    "PW Rights of Distribution Start Date": "",
    "Acquired Rights of Distribution Territory": "",
    "Current Distributor": "",
    "Current Distributor Governing Agreement": "",
    "Termination Notice Required": "",
    "Videos Included": "",
    "Other PW Distribution Obligations": "",
  },
  "Approval Details": {
    "PW Obligation to Obtain Seller Approval (Outgoing)": "",
    "Approval Procedure": "",
    "Seller Approval Contact": "",
  },
  "Accounting & Audit": {
    "Accounting Frequency to Seller": "",
    "Accounting Lag to Seller": "",
    "Seller Statement Recipient(s)": "",
    "Other Royalty Participants (Companies)": "",
    "Other Royalty Participants (Individuals)": "",
    "Seller Rights to Audit PW": "",
    "Pre-Closing Audits by Seller": "",
  },
  "Seller Retained Interest Financial Terms": {
    "Percentage of Revenue Received by PW": "",
    "Seller Retained Interest Percentage": "",
    "Other Payable Percentages": "",
    "PW Administration Fee": "",
    "PW Distribution Fee": "",
  },
  
}
