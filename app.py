"""
FastAPI application for processing contract PDFs.
This API provides an endpoint to upload ZIP files containing PDF contracts,
which are then processed using the Gemini model for information extraction.
"""
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from time import time
from typing import List, Dict, Any, Optional
import boto3
import uvicorn
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient

from prompt import extraction_prompt as prompt
from utils import (
    create_model,
    compact_coordinates,
    extract_text_with_positions,
)
from post_processing import (
    update_extracted_value,
    populate_template,
    upload_to_airtable,
    update_amendment_changes_table,
    concord_template
)

load_dotenv()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================
class ReviewerSubmitRequest(BaseModel):
    """Request model for reviewer_submit endpoint."""
    contract_id: str
    json_file: Dict[str, Any]


# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================
app = FastAPI(
    title="Contract Processing API",
    description="API for processing contract PDF files with AI extraction",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # can be ["*"] to allow all origins (not recommended in production)
    allow_credentials=True,
    allow_methods=["*"],     # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],     # Authorization, Content-Type, etc.
)

# ============================================================================
# CONFIGURATION
# ============================================================================
# Airtable
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

# AWS S3
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# MongoDB
MONGODB_URI = os.getenv("DATABASE_URI")
MONGODB_DATABASE = os.getenv("DATABASE_NAME")
MONGODB_COLLECTION = os.getenv("COLLECTION_NAME")

OUT_DIR = "outputs/"
FRONTEND_URL = os.getenv("FRONTEND_URL")
# Ensure output directory exists
os.makedirs(OUT_DIR, exist_ok=True)

# Initialize S3 client
s3_client = None
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and S3_BUCKET_NAME:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

# Initialize MongoDB client
mongo_client = None
mongo_collection = MONGODB_COLLECTION
if MONGODB_URI and MONGODB_DATABASE and MONGODB_COLLECTION:
    try:
        mongo_client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000
        )
        # Test connection
        mongo_client.server_info()
        mongo_db = mongo_client[MONGODB_DATABASE]
        mongo_collection = mongo_db[MONGODB_COLLECTION]
        print(f"✓ MongoDB connected successfully to {MONGODB_DATABASE}")
    except Exception as e:
        print(f"⚠ MongoDB connection failed: {e}")
        print("  Continuing without MongoDB support.")
        mongo_client = None
        mongo_collection = None

# Initialize the model
model = create_model(
    model_name="gemini-2.5-flash",
    temperature=0.2,
)

# Load the Concord template
concord_template = concord_template


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


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
    actual_json: Dict[str, Any] = None,
    amendment_changes_record_id: str = None
) -> Optional[str]:
    """
    Save contract information to MongoDB.

    Args:
        contract_id: Unique identifier for the contract
        file_name: Name of the PDF file (without extension)
        s3_link: S3 URL of the uploaded PDF
        record_id: Dictionary returned by upload_to_airtable
        actual_json: The processed JSON data from the contract
        amendment_changes_record_id: Airtable record ID for Contract Utilities table

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
            "amendment_changes_record_id": amendment_changes_record_id,
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
        amendment_changes_record_id = document.get("amendment_changes_record_id")

        # Update MongoDB with new JSON data
        update_data = {
            "actual_json": json_data,
            "updated_at": time(),
            "reviewed": True
        }
        
        update_result = mongo_collection.update_one(
            {"contract_id": contract_id},
            {"$set": update_data}
        )
        
        # Verify the update was successful
        if update_result.modified_count > 0:
            result["mongodb_updated"] = True
            print(f"✓ MongoDB updated for contract_id: {contract_id}")
        else:
            print(f"⚠ MongoDB update matched but didn't modify document for contract_id: {contract_id}")
            result["mongodb_updated"] = True  # Still consider it successful if matched
            
        # Log update details for debugging
        print(f"  → Matched: {update_result.matched_count}, Modified: {update_result.modified_count}")

        # Update Airtable if configured and record_id exists
        if AIRTABLE_API_KEY and AIRTABLE_BASE_ID and record_id:
            from pyairtable import Api
            from post_processing import flatten_extracted_data

            api = Api(AIRTABLE_API_KEY)
            updated_tables = []

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

            # First pass: Update Account and Contacts to get their record IDs
            for table_name in ["Account", "Contacts"]:
                if table_name not in json_data or table_name not in record_id:
                    continue

                try:
                    table_data = json_data[table_name].copy()
                    airtable_record_id = record_id[table_name]

                    # Get the Airtable table
                    table = api.table(AIRTABLE_BASE_ID, table_name)

                    # Flatten the nested structure
                    flattened_data = flatten_extracted_data(table_data)

                    # Apply field-specific rules
                    if table_name == "Account":
                        # Remove Contacts and Details fields
                        flattened_data.pop("Contacts", None)
                        flattened_data.pop("Details", None)
                        account_record_id = airtable_record_id
                    elif table_name == "Contacts":
                        # Remove Full Name field
                        flattened_data.pop("Full Name", None)
                        contact_record_id = airtable_record_id

                    # Update the record
                    table.update(airtable_record_id, flattened_data)
                    updated_tables.append(table_name)
                    print(f"✓ Airtable updated: {table_name} "
                          f"(Record ID: {airtable_record_id})")

                except Exception as table_error:
                    print(f"✗ Error updating Airtable table "
                          f"{table_name}: {table_error}")
                    continue

            # Second pass: Update remaining tables with proper linking
            for table_name in json_data.keys():
                # Skip already processed tables
                if table_name in ["Account", "Contacts"]:
                    continue

                # Handle table name mapping
                airtable_table_name = table_name
                if table_name == "R & A":
                    airtable_table_name = "Royalties & Accounting"

                # Check if this table was originally created
                if airtable_table_name not in record_id:
                    continue

                try:
                    airtable_record_id = record_id[airtable_table_name]
                    table_data = json_data[table_name].copy()

                    # Get the Airtable table
                    table = api.table(AIRTABLE_BASE_ID, airtable_table_name)

                    # Flatten the nested structure
                    flattened_data = flatten_extracted_data(table_data)

                    # Add Contract field to specific tables
                    if table_name in ["Registration Information", "General Information", 
                                      "Licensing Approvals", "R & A", "Documents"]:
                        if agreement_name:
                            flattened_data["Contract"] = agreement_name
                            print(f"  → Adding Contract field: {agreement_name}")

                    # Add linking fields
                    if table_name == "Details" and account_record_id:
                        flattened_data["Contracted Writer Party"] = [account_record_id]

                    if table_name == "Registration Information":
                        if contact_record_id:
                            flattened_data["Writer's Name"] = [contact_record_id]

                    # Update the record
                    table.update(airtable_record_id, flattened_data)
                    updated_tables.append(airtable_table_name)
                    print(f"✓ Airtable updated: {airtable_table_name} "
                          f"(Record ID: {airtable_record_id})")

                except Exception as table_error:
                    print(f"✗ Error updating Airtable table "
                          f"{airtable_table_name}: {table_error}")
                    continue

            # Add Account Name linking to Contacts table if both exist
            if account_record_id and contact_record_id and "Contacts" in record_id:
                try:
                    contacts_table = api.table(AIRTABLE_BASE_ID, "Contacts")
                    contacts_table.update(contact_record_id, {"Account Name": [account_record_id]})
                    print(f"  ✓ Contacts: Linked to Account (ID: {account_record_id})")
                except Exception as e:
                    print(f"  ✗ Contacts: Failed to link Account - {str(e)}")

            # Update Contract Utilities table's Contract field if it exists and agreement_name changed
            if amendment_changes_record_id and agreement_name:
                try:
                    amendment_table = api.table(AIRTABLE_BASE_ID, "Contract Utilities")
                    amendment_table.update(amendment_changes_record_id, {"Contract": agreement_name})
                    print(f"  ✓ Contract Utilities: Updated Contract field to '{agreement_name}' (ID: {amendment_changes_record_id})")
                except Exception as e:
                    print(f"  ✗ Contract Utilities: Failed to update Contract field - {str(e)}")

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
        json_text = json.dumps(response_data, indent=2)
        json_text = compact_coordinates(json_text)
        with open(json_output_path, "w") as json_file:
            json_file.write(json_text)
        result["output_path"] = json_output_path
        result["actual_json"] = response_data
        result["status"] = "success"

        # Upload to Airtable if configured
        airtable_record = None
        agreement_name = None
        if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
            airtable_result = upload_to_airtable(
                filename=filename,
                json_file=json_text,
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
            
            # Update Contract Utilities table in Airtable with contract_id
            amendment_record_id = None
            if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
                amendment_record_id = update_amendment_changes_table(
                    frontend_url=FRONTEND_URL,
                    contract_id=contract_id,
                    agreement_name=agreement_name,
                    airtable_api_key=AIRTABLE_API_KEY,
                    airtable_base_id=AIRTABLE_BASE_ID
                )
                result["amendment_changes_record_id"] = amendment_record_id
            
            mongodb_id = save_to_mongodb(
                contract_id=contract_id,
                file_name=filename,
                s3_link=s3_url,
                record_id=airtable_record or {},
                actual_json=response_data,
                amendment_changes_record_id=amendment_record_id
            )
            result["contract_id"] = contract_id
            result["mongodb_id"] = mongodb_id

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    result["total_time"] = time() - process_start
    return result


# ============================================================================
# API ENDPOINTS
# ============================================================================
@app.get("/")
async def root():
    """Root endpoint providing API information."""
    return {
        "message": "Contract Processing API",
        "version": "1.0.0",
        "endpoints": {
            "/process-pdf": "POST - Upload PDF file(s) for processing",
            "/reviewer_submit": "POST - Submit reviewed JSON data",
            "/get_contract/{contract_id}": "GET - Fetch contract data by ID",
            "/health": "GET - Health check endpoint"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model": "gemini-2.5-flash",
        "timestamp": time()
    }


@app.get("/get_contract/{contract_id}")
async def get_contract(contract_id: str):
    """
    Fetch contract data by contract ID.

    This endpoint retrieves the s3_link and actual_json for a given contract_id
    from MongoDB.

    Args:
        contract_id: The unique contract identifier

    Returns:
        JSON response with s3_link and actual_json
    """
    if mongo_collection is None:
        raise HTTPException(
            status_code=503,
            detail="MongoDB not configured or unavailable"
        )

    try:
        # Find the document in MongoDB by contract_id
        document = mongo_collection.find_one(
            {"contract_id": contract_id},
            {"_id": 0, "s3_link": 1, "actual_json": 1, "file_name": 1}
        )

        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Contract ID '{contract_id}' not found"
            )

        # Get actual_json and remove "Amendment Changes" if it exists
        actual_json = document.get("actual_json", {})
        if "Amendment Changes" in actual_json:
            actual_json = actual_json.copy()  # Create a copy to avoid modifying the original
            del actual_json["Amendment Changes"]

        response_data = {
            "contract_id": contract_id,
            "file_name": document.get("file_name", "unknown"),
            "s3_link": document.get("s3_link"),
            "actual_json": actual_json
        }

        return JSONResponse(content=response_data, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching contract data: {str(e)}"
        )


@app.post("/process-pdf")
async def process_pdf(files: List[UploadFile] = File(...)):
    """
    Process PDF contract file(s).

    This endpoint accepts one or more PDF files,
    processes them with the AI model, and returns results.

    Args:
        files: One or more PDF files to process

    Returns:
        JSON response with processing results for each PDF
    """
    # Validate all files are PDFs
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type for '{file.filename}'. "
                       f"Please upload PDF files only."
            )

    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()

    try:
        results = []

        # Process each uploaded PDF
        for file in files:
            # Save uploaded PDF file
            pdf_path = os.path.join(temp_dir, file.filename)
            with open(pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Process the PDF
            result = process_single_pdf(pdf_path, OUT_DIR)
            results.append(result)

        # Prepare response summary
        successful = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")

        response_data = {
            "summary": {
                "total_files": len(files),
                "successful": successful,
                "failed": failed
            },
            "results": results
        }

        return JSONResponse(content=response_data, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF file(s): {str(e)}"
        )
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


@app.post("/reviewer_submit")
async def reviewer_submit(request: ReviewerSubmitRequest = Body(...)):
    """
    Submit reviewed JSON data for a contract.

    This endpoint accepts a contract_id and updated JSON data,
    finds the corresponding MongoDB record, and updates both
    MongoDB and Airtable with the new data.

    Args:
        request: ReviewerSubmitRequest containing contract_id and json_file

    Returns:
        JSON response with update status
    """
    contract_id = request.contract_id
    json_data = request.json_file

    # Validate inputs
    if not contract_id:
        raise HTTPException(
            status_code=400,
            detail="contract_id is required"
        )

    if not json_data:
        raise HTTPException(
            status_code=400,
            detail="json_file is required"
        )

    try:
        # Update MongoDB and Airtable
        result = update_mongodb_and_airtable(contract_id, json_data)

        if result.get("error"):
            raise HTTPException(
                status_code=404 if "not found" in result["error"].lower()
                else 500,
                detail=result["error"]
            )

        response_data = {
            "status": "success",
            "message": "Contract data updated successfully",
            "contract_id": contract_id,
            "mongodb_updated": result["mongodb_updated"],
            "airtable_updated": result["airtable_updated"],
            "updated_tables": result.get("updated_tables", [])
        }

        return JSONResponse(content=response_data, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating contract data: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
