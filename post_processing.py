from copy import deepcopy
import json
from pyairtable import Api
from typing import List, Dict, Any, Optional
from pathlib import Path
from time import time
import os
from pyairtable.formulas import match
from utils import (
    create_model,
    compact_coordinates,
    extract_text_with_positions,
)


choice_of_law_mapping = {
    "California": "CA - California",
    "Florida": "FL - Florida",
    "New York": "NY - New York",
    "Tennessee": "TN - Tennessee",
    "United States": "USA - United States",
    "Australia": "AUS - Australia",
    "Canada": "CAN - Canada",
    "Germany": "DEU - Germany",
    "Denmark": "DNK - Denmark",
    "England & Wales": "EAW - England & Wales",
    "France": "FRA - France",
    "United Kingdom of Great Britain and Northern Ireland":
    "GBR - United Kingdom of Great Britain and Northern Ireland",
    "Ireland": "IRL - Ireland",
    "Japan": "JPN - Japan",
    "Korea": "KOR - Korea",
    "Mexico": "MEX - Mexico",
    "New Zealand": "NZL - New Zealand",
    "Puerto Rico": "PRI - Puerto Rico",
}

currency_mapping = {
    "USD": "USD - U.S. Dollar",
    "AUD": "AUD - Australian Dollar",
    "EUR": "EUR - Euro",
    "GBP": "GBP - British Pound",
    "MXN": "MXN - Mexican Peso",
    "NZD": "NZD - New Zealand Dollar",
}

pro_accepted_list = [
    'ACEMLA', 'AllTrack', 'MCOS', 'AMRA', 'APRA', 'ASCAP', 'BMI', 'CMRRA',
    'GMR', 'IMRO', 'JASRAC', 'KODA', 'MCPSI', 'PPCA', 'PPI', 'PPL',
    'Pro Music Rights', 'PRS', 'Re:Sound', 'SACD', 'SACEM', 'SESAC',
    'SOCAN', 'SoundExchange'
]


def update_extracted_value(json_data,
                           choice_of_law_mapping=choice_of_law_mapping,
                           currency_mapping=currency_mapping,
                           pro_accepted_list=pro_accepted_list):
    # Choice of Law
    if "Choice of Law" in json_data and "Extracted Value" in json_data["Choice of Law"]:
        original_value = json_data["Choice of Law"]["Extracted Value"]
        json_data["Choice of Law"]["Extracted Value"] = choice_of_law_mapping.get(
            original_value, original_value)

    # Currency
    if "Currency" in json_data and "Extracted Value" in json_data["Currency"]:
        original_value = json_data["Currency"]["Extracted Value"]
        json_data["Currency"]["Extracted Value"] = currency_mapping.get(
            original_value, original_value)

    # Performing Rights Organization (PRO)
    if "Performing Rights Organization" in json_data and "Extracted Value" in json_data["Performing Rights Organization"]:
        original_value = json_data["Performing Rights Organization"]["Extracted Value"]
        json_data["Performing Rights Organization"]["Extracted Value"] = original_value if original_value in pro_accepted_list else "Other"

    if json_data["Performing Rights Organization"]["Extracted Value"] == "Other":
        json_data["Other Performing Rights Organization"] = json_data["Performing Rights Organization"]

    else:
        pass

    return json_data


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
    Converts nested fields into a flat dictionary with field names and extracted values.
    
    Args:
        data_dict: Dictionary containing nested field data
    
    Returns:
        Flattened dictionary ready for Airtable
    """
    # List of fields that are multi-select in Airtable and require array values
    multi_select_fields = [
        "Territory",
        "Other Territory",
        "Excluded Territories"
    ]
    
    flattened = {}
    
    for field_name, field_data in data_dict.items():
        if isinstance(field_data, dict) and "Extracted Value" in field_data:
            extracted_value = field_data["Extracted Value"]
            
            # Handle multi-select fields - convert to array if not already
            if field_name in multi_select_fields:
                if isinstance(extracted_value, str):
                    # Convert string to array, handling empty strings and "N/A"
                    if extracted_value and extracted_value != "N/A":
                        flattened[field_name] = [extracted_value]
                    # Skip empty or N/A values for multi-select
                elif isinstance(extracted_value, list):
                    # Already an array
                    flattened[field_name] = extracted_value
            else:
                # Store the extracted value directly
                flattened[field_name] = extracted_value
        elif isinstance(field_data, dict):
            # If it's a dict without "Extracted Value", convert to JSON string
            flattened[field_name] = json.dumps(field_data)
        else:
            # Store primitive values as-is
            flattened[field_name] = field_data
    
    return flattened


def upload_to_airtable(filename, json_file, airtable_api_key=None, airtable_base_id=None):
    """
    Upload contract data to multiple Airtable tables.
    Each top-level key in the JSON (Account, Contacts, Details, etc.) 
    corresponds to a separate table in Airtable.
    
    Args:
        filename: Name of the contract
        pdf_path: Path to the PDF file
        json_path: Path to the JSON file
    
    Returns:
        Dictionary of created records by table name
    """
    record_id = {}
    if not all([airtable_api_key, airtable_base_id]):
        print("Warning: Airtable credentials not configured. Skipping upload.")
        return None
    
    try:
    
        json_data = json.loads(json_file)

        api = Api(airtable_api_key)
        created_records = {}
        
        # Store record IDs for linking
        account_record_id = None
        contact_record_id = None
        agreement_name = None
        
        # Extract Agreement Name for use in Contract fields
        if "Details" in json_data and "Agreement Name" in json_data["Details"]:
            agreement_name_data = json_data["Details"]["Agreement Name"]
            if isinstance(agreement_name_data, dict) and "Extracted Value" in agreement_name_data:
                agreement_name = agreement_name_data["Extracted Value"]
            else:
                agreement_name = agreement_name_data

        print(f"\n📤 Uploading {filename} to Airtable...")
        print("=" * 50)

        # First pass: Create Account and Contacts to get their record IDs
        for table_name in ["Account", "Contacts"]:
            if table_name not in json_data:
                continue
                
            try:
                table_data = json_data[table_name].copy()
                
                # Handle table name mapping
                airtable_table_name = table_name
                
                # Get the Airtable table
                table = api.table(airtable_base_id, airtable_table_name)
                
                # Flatten the nested structure
                record_data = flatten_extracted_data(table_data)
                
                # Apply field-specific rules
                if table_name == "Account":
                    # Remove Contacts and Details fields
                    record_data.pop("Contacts", None)
                    record_data.pop("Details", None)
                elif table_name == "Contacts":
                    # Remove Full Name field
                    record_data.pop("Full Name", None)
                
                # Create the record in Airtable
                record = table.create(record_data)
                created_records[airtable_table_name] = record
                
                # Store record IDs for linking
                if table_name == "Account":
                    account_record_id = record['id']
                elif table_name == "Contacts":
                    contact_record_id = record['id']
                
                print(f"  ✓ {airtable_table_name}: Record created (ID: {record['id']})")
                record_id[airtable_table_name] = record['id']

            except Exception as table_error:
                print(f"  ✗ {airtable_table_name}: {str(table_error)}")
                continue

        # Second pass: Create remaining tables with proper linking
        for table_name, table_data in json_data.items():
            # Skip already processed tables
            if table_name in ["Account", "Contacts"]:
                continue
            
            # Handle table name mapping
            airtable_table_name = table_name
            if table_name == "R & A":
                airtable_table_name = "Royalties & Accounting"
            
            try:
                # Get the Airtable table
                table = api.table(airtable_base_id, airtable_table_name)
                
                # Flatten the nested structure
                record_data = flatten_extracted_data(table_data.copy())
                
                # Add Contract field to specific tables
                if table_name in ["Registration Information", "General Information", 
                                  "Licensing Approvals", "R & A", "Documents"]:
                    if agreement_name:
                        record_data["Contract"] = agreement_name
                        print(f"  → Adding Contract field: {agreement_name}")
                
                # Add linking fields
                if table_name == "Details" and account_record_id:
                    record_data["Contracted Writer Party"] = [account_record_id]
                
                if table_name == "Registration Information":
                    if contact_record_id:
                        record_data["Writer's Name"] = [contact_record_id]
                
                # Create the record in Airtable
                record = table.create(record_data)
                created_records[airtable_table_name] = record

                print(f"  ✓ {airtable_table_name}: Record created (ID: {record['id']})")
                record_id[airtable_table_name] = record['id']

            except Exception as table_error:
                print(f"  ✗ {airtable_table_name}: {str(table_error)}")
                continue
        
        # Add Account Name linking to Contacts table if both exist
        if account_record_id and contact_record_id:
            try:
                contacts_table = api.table(airtable_base_id, "Contacts")
                contacts_table.update(contact_record_id, {"Account Name": [account_record_id]})
                print(f"  ✓ Contacts: Linked to Account (ID: {account_record_id})")
            except Exception as e:
                print(f"  ✗ Contacts: Failed to link Account - {str(e)}")

        print("=" * 50)
        print(f"✓ Successfully uploaded to {len(created_records)}/{len(json_data)} tables\n")
        
        # Return both record_id and agreement_name
        return {
            "record_id": record_id,
            "agreement_name": agreement_name
        }

    except Exception as e:
        print(f"✗ Error uploading to Airtable: {str(e)}")
        print(f"   Base ID: {airtable_base_id}")
        return None


def update_amendment_changes_table(
    frontend_url,
    contract_id,
    agreement_name=None,
    airtable_api_key=None,
    airtable_base_id=None,
    table_name="Amendment Changes"
):
    """
    Update the Amendment Changes table in Airtable with the contract_id.
    If the 'Links' column doesn't exist, it will be created automatically
    when the first record is inserted.
    
    Args:
        frontend_url: Frontend URL for constructing the link
        contract_id: The contract ID to add to the Links column
        agreement_name: The agreement name to add to the Contract column
        airtable_api_key: Airtable API key
        airtable_base_id: Airtable Base ID
        table_name: Name of the table (default: "Amendment Changes")
    
    Returns:
        Record ID if successful, None otherwise
    """
    if not all([airtable_api_key, airtable_base_id, contract_id]):
        print("Warning: Missing required parameters for Amendment Changes update.")
        return None
    
    try:
        api = Api(airtable_api_key)
        table = api.table(airtable_base_id, table_name)
        link = f"{frontend_url}/{contract_id}"
        
        # Create record with contract_id in Links field and agreement_name in Contract field
        record_data = {
            "Link": link,
            "Amendment Changes": ""  # Leave empty as specified
        }
        
        # Add Contract field if agreement_name is provided
        if agreement_name:
            record_data["Contract"] = agreement_name
            print(f"  → Adding Contract field to Amendment Changes: {agreement_name}")
        
        # Create new record
        record = table.create(record_data)
        print(f"✓ Amendment Changes: Added contract_id {contract_id} (Record ID: {record['id']})")
        return record['id']
        
    except Exception as e:
        print(f"✗ Error updating Amendment Changes table: {str(e)}")
        return None


# Template for Concord contracts
concord_template = {
  "Account": {
    "Account Name": "",
    "Type": "",
    "Description": "",
    "Billing Street": "",
    "Billing City": "",
    "Billing Zip/Postal Code": "",
    "Billing State/Province": "",
    "Billing Country": ""
  },
  "Contacts": {
    "First Name": "",
    "Last Name": ""
  },
  "Details": {
    "Concord Party": "",
    "Agreement Name": "",
    "Currency": "",
    "Commitment End Date": "",
    "Agreement Type": "",
    "Assignability of Contract": "",
    "Assignability of Contract Details": "",
    "Change of Control": "",
    "Change of Control Details": "",
    "Key Person Provision": "",
    "Key Person Provision Details": ""
  },
  "Documents": {
    "Schedule A Received": ""
  },
  "General Information": {
    "Effective Date": "",
    "Execution Date": "",
    "Territory": "",
    "Other Territory": "",
    "Excluded Territories": "",
    "Term Definition": "",
    "Number of Contract Periods": "",
    "Other number of Contract Periods": "",
    "Are there Options?": "",
    "Length of Each Contract Period": "",
    "Minimum Delivery Commitment?": "",
    "Minimum Delivery Commitment Amount": "",
    "Minimum Delivery Release Commitment?": "",
    "Min Delivery Release Commitment Amount": "",
    "Catalog (Full / Partial)": "",
    "All Songs Written During Term": "",
    "All Songs Acquired during Term": "",
    "All Songs Prior to Term": "",
    "Only Songs on Artist's Album": "",
    "[Prior] Pass-Through Income Included in Concord": "No",
    "Rights Granted: Assignment Copyrights": "",
    "Rights Granted: General": "",
    "Rights Granted: Master Representation": "",
    "Rights Granted: Sync Camp": "",
    "Rights Granted: Demos": "",
    "Rights Excluded": "",
    "Right of First Negotiation / Match Right": "",
    "Choice of Law": "",
    "Choice of Law - Other": ""
  },
  "Licensing Approvals": {
    "Licensing Approval Notes": "",
    "Licensing: Any ad for personal hygiene, firearms or tobacco products": "",
    "Licensing: Any political or religious use": "",
    "Licensing: Samples and interpolations": "",
    "Licensing: Fundamental adaptations / translations / etc. to music, lyrics, title, or harmonic structure": "",
    "Licensing: Issue blanket licenses including the Comps": "",
    "Licensing: Licence the Compositions for period with extends beyond the Rights Period": "",
    "Name & Likeness Approval Notes": "",
    "Name & Likeness Approvals": "",
    "Sync Master Rep Approval Notes": "",
    "Synchronization: Films, Television Programmes, Advertisements, Computer Games, Interactive Devices, Videos": "",
    "Miscellaneous Licensing Notes": "",
    "Print: Print, publish and vend, and license the same": "",
    "Mechanical: Issue \"first use\" mechanical licenses": "",
    "Mechanical: Issue mechanical reproduction licenses at less than full statutory rate for the US": "",
    "Performance: Grand rights licenses and right to dramatize": "",
    "Terms of Approval for Licensing": ""
  },
  "R & A": {
    "Royalty Basis": "",
    "Definition of Royalty Basis": "",
    "Definition of Gross Income": "",
    "At Source": "",
    "Frequency of Accounting / Statements": "",
    "Payments/Statements Due within": "",
    "Agreement Royalties": "",
    "General Master Rep Royalty": "",
    "Camp Master Rep Royalty": "",
    "Royalty Escalation": "",
    "Retroactive Collection": ""
  },
  "Registration Information": {
    "Writer(s) CAE/IPI Name": "",
    "Writer(s) CAE/IPI Number": "",
    "Publishing Designee(s) IPI Number": "",
    "Publishing Designee(s) IPI Name": "",
    "Performing Rights Organization": "",
    "Other Performing Rights Organization": ""
  }
}


def upload_to_s3(file_path: str, bucket_name: str, object_name: str) -> Optional[str]:
    """
    Upload a file to S3 bucket.

    Args:
        file_path: Path to the file to upload
        bucket_name: Name of the S3 bucket
        object_name: S3 object name (key)

    Returns:
        S3 URL of the uploaded file, or None if upload fails
    """
    if not s3_client:
        return None

    try:
        s3_client.upload_file(file_path, bucket_name, object_name)
        s3_url = f"https://{bucket_name}.s3.{AWS_REGION}.amazonaws.com/{object_name}"
        return s3_url
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return None


def save_to_mongodb(
    contract_id: str,
    file_name: str,
    s3_link: str,
    record_id: Dict[str, Any],
    actual_json: Dict[str, Any] = None
) -> Optional[str]:
    """
    Save contract information to MongoDB.

    Args:
        contract_id: Unique identifier for the contract
        file_name: Name of the PDF file (without extension)
        s3_link: S3 URL of the uploaded PDF
        record_id: Dictionary returned by upload_to_airtable
        actual_json: The processed JSON data from the contract

    Returns:
        MongoDB document ID, or None if insert fails
    """
    if mongo_collection is None:
        return None

    try:
        document = {
            "contract_id": contract_id,
            "file_name": file_name,
            "s3_link": s3_link,
            "record_id": record_id,
            "actual_json": actual_json or {},
            "created_at": time()
        }
        result = mongo_collection.insert_one(document)
        return str(result.inserted_id)
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")
        return None


def update_mongodb_and_airtable(
    contract_id: str,
    json_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Update MongoDB and Airtable records with reviewed JSON data.

    Args:
        contract_id: Contract ID to look up in MongoDB
        json_data: Updated JSON data from reviewer

    Returns:
        Dictionary containing update status and details
    """
    result = {
        "contract_id": contract_id,
        "mongodb_updated": False,
        "airtable_updated": False,
        "error": None
    }

    if mongo_collection is None:
        result["error"] = "MongoDB not configured"
        return result

    try:
        # Find the document in MongoDB by contract_id
        document = mongo_collection.find_one({"contract_id": contract_id})

        if not document:
            result["error"] = f"Contract ID '{contract_id}' not found in MongoDB"
            return result

        # Get record_id from MongoDB document
        record_id = document.get("record_id", {})
        file_name = document.get("file_name", "unknown")

        # Update MongoDB with new JSON data
        update_data = {
            "json_data": json_data,
            "updated_at": time(),
            "reviewed": True
        }
        mongo_collection.update_one(
            {"contract_id": contract_id},
            {"$set": update_data}
        )
        result["mongodb_updated"] = True
        print(f"✓ MongoDB updated for contract_id: {contract_id}")

        # Update Airtable if configured and record_id exists
        if AIRTABLE_API_KEY and AIRTABLE_BASE_ID and record_id:
            from pyairtable import Api
            from post_processing import flatten_extracted_data

            api = Api(AIRTABLE_API_KEY)
            updated_tables = []

            # Update each table that was originally created
            for table_name, airtable_record_id in record_id.items():
                if table_name in json_data:
                    try:
                        table = api.table(AIRTABLE_BASE_ID, table_name)
                        # Flatten the data for Airtable
                        flattened_data = flatten_extracted_data(
                            json_data[table_name]
                        )
                        # Update the record
                        table.update(airtable_record_id, flattened_data)
                        updated_tables.append(table_name)
                        print(f"✓ Airtable updated: {table_name} "
                              f"(Record ID: {airtable_record_id})")
                    except Exception as table_error:
                        print(f"✗ Error updating Airtable table "
                              f"{table_name}: {table_error}")
                        continue

            result["airtable_updated"] = len(updated_tables) > 0
            result["updated_tables"] = updated_tables

        return result

    except Exception as e:
        result["error"] = str(e)
        print(f"✗ Error updating records: {e}")
        return result


def process_single_pdf(
    pdf_path: str,
    output_dir: str
) -> Dict[str, Any]:
    """
    Process a single PDF file and return extracted data.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save output JSON

    Returns:
        Dictionary containing processing results and metadata
    """
    filename = Path(pdf_path).stem
    result = {
        "filename": filename,
        "status": "processing",
        "extraction_time": 0,
        "llm_time": 0,
        "total_time": 0,
        "output_path": None,
        "s3_link": None,
        "contract_id": None,
        "mongodb_id": None,
        "airtable_record_id": None,
        "amendment_changes_record_id": None,
        "error": None
    }

    process_start = time()

    try:
        # Text extraction
        extraction_start = time()
        result_dict, full_text = extract_text_with_positions(pdf_path)
        result["extraction_time"] = time() - extraction_start

        # LLM processing
        formatted_prompt = prompt.format(
            Extracted_text=full_text,
            Text_positions=result_dict
        )

        llm_start = time()
        system_message = (
            "You are a specialist in extracting coordinates "
            "of a given text and creating a bounding box."
        )
        response = model.generate_content(
            [
                {"role": "model", "parts": system_message},
                {"role": "user", "parts": formatted_prompt},
            ]
        )

        # Parse response
        response_data = response.text.strip()
        response_data = json.loads(response_data)
        result["llm_time"] = time() - llm_start


        # Post-processing
        response_data = update_extracted_value(json_data=response_data)
        response_data = populate_template(
            template=concord_template,
            source=response_data
        )

        # Save output
        json_output_path = os.path.join(output_dir, f"{filename}.json")
        with open(json_output_path, "w") as json_file:
            json_text = json.dumps(response_data, indent=2)
            json_text = compact_coordinates(json_text)
            json_file.write(json_text)

        result["output_path"] = json_output_path
        result["status"] = "success"

        # Upload to Airtable if configured
        airtable_record = None
        agreement_name = None
        if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
            airtable_result = upload_to_airtable(
                filename=filename,
                json_path=json_output_path,
                airtable_api_key=AIRTABLE_API_KEY,
                airtable_base_id=AIRTABLE_BASE_ID,
            )
            if airtable_result:
                airtable_record = airtable_result.get("record_id", {})
                agreement_name = airtable_result.get("agreement_name")
            result["airtable_record_id"] = airtable_record

        # Upload PDF to S3 if configured
        s3_url = None
        if s3_client and S3_BUCKET_NAME:
            s3_object_name = f"contracts/{filename}.pdf"
            s3_url = upload_to_s3(pdf_path, S3_BUCKET_NAME, s3_object_name)
            result["s3_link"] = s3_url

        # Save to MongoDB if configured
        if mongo_collection is not None and s3_url:
            contract_id = str(uuid.uuid4())
            mongodb_id = save_to_mongodb(
                contract_id=contract_id,
                file_name=filename,
                s3_link=s3_url,
                record_id=airtable_record or {},
                actual_json=response_data
            )
            result["contract_id"] = contract_id
            result["mongodb_id"] = mongodb_id

            # Update Amendment Changes table in Airtable with contract_id
            if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
                amendment_record_id = update_amendment_changes_table(
                    frontend_url=FRONTEND_URL,
                    contract_id=contract_id,
                    agreement_name=agreement_name,
                    airtable_api_key=AIRTABLE_API_KEY,
                    airtable_base_id=AIRTABLE_BASE_ID
                )
                result["amendment_changes_record_id"] = amendment_record_id

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    result["total_time"] = time() - process_start
    return result
