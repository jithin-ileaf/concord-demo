import re
import os
import json
from time import time
from pathlib import Path
from google import generativeai as genai
from dotenv import load_dotenv
from pdf2image import convert_from_path
from collections import defaultdict
import pytesseract
import psycopg2
import psycopg2.extras
psycopg2.extras.register_uuid()
load_dotenv()


def create_model(model_name="gemini-2.5-pro",
                 temperature=0.2,
                 response_mime_type="application/json"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "temperature": temperature,
            "response_mime_type": response_mime_type,
        },
    )
    return model


def upload_pdf_to_model(pdf_path: str):
    file = genai.upload_file(
        path=pdf_path,
        display_name=os.path.basename(pdf_path)
    )
    return file


def extract_from_pdf(pdf_path: str, model, prompt) -> dict:
    start_time_to_upload = time()
    uploaded_file = upload_pdf_to_model(pdf_path)
    end_time_to_upload = time()
    print(f"    Time taken to upload file: {end_time_to_upload - start_time_to_upload} seconds")

    start_time_to_generate_response = time()
    response = model.generate_content(
        contents=[prompt, uploaded_file],       # deterministic extraction
        )
    end_time_to_generate_response = time()
    print(f"    Time taken to generate response: {end_time_to_generate_response - start_time_to_generate_response} seconds")
    # Get raw model text output
    text = response.text.strip()

    # Parse JSON
    try:
        return json.loads(text)
    except Exception as e:
        return {"raw_output": text, "error": str(e)}


def extract_text_with_positions(file: str) -> tuple[dict, str]:
    file_name = Path(file).stem
    pages = convert_from_path(
        file,
        dpi=150,
        grayscale=True,
        fmt='jpg'
    )

    # Page-wise output container
    output = defaultdict(list)
    # Container for all text
    all_text = []

    for page_num, page in enumerate(pages, start=1):
        width, height = page.size

        # Use PIL Image directly instead of saving/loading
        data_raw = pytesseract.image_to_data(
            page,
            output_type=pytesseract.Output.DICT
        )

        # Pre-build word lookup by (line_num, par_num, block_num)
        word_lookup = defaultdict(list)
        for j in range(len(data_raw["text"])):
            if data_raw["level"][j] == 5 and data_raw["text"][j].strip():
                key = (data_raw["line_num"][j], data_raw["par_num"][j], data_raw["block_num"][j])
                word_lookup[key].append(data_raw["text"][j])

        for i in range(len(data_raw["text"])):
            # Line-level box
            if data_raw["level"][i] == 4:
                line_num = data_raw["line_num"][i]
                par_num = data_raw["par_num"][i]
                block_num = data_raw["block_num"][i]

                # Quick lookup instead of nested loop
                words = word_lookup.get((line_num, par_num, block_num), [])

                if words:
                    final_text = " ".join(words)

                    x, y, w, h = (
                        data_raw["left"][i],
                        data_raw["top"][i],
                        data_raw["width"][i],
                        data_raw["height"][i],
                    )

                    coordinates = [
                        [round(x / width, 3), round(y / height, 3)],
                        [round((x + w) / width, 3), round(y / height, 3)],
                        [round((x + w) / width, 3), round((y + h) / height, 3)],
                        [round(x / width, 3), round((y + h) / height, 3)],
                    ]

                    output[f"Page {page_num}"].append({
                        "line": final_text,
                        "coordinates": coordinates
                    })
                    all_text.append(final_text)

    return dict(output), " ".join(all_text)


def compact_coordinates(json_data):
    # Remove newlines inside lists of numbers
    return re.sub(r'\[\s+([\d\.\,\s\-eE]+?)\s+\]',
                  lambda m: '[' + ' '.join(m.group(1).split()) + ']',
                  json_data)

