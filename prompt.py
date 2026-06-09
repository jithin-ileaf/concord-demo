extraction_prompt = """
You are given an `"Extracted Text"` of a legal contract along with a dictionary containing the `"Text Positions"` of various text segments within the contract.

Your task: Use the provided text and positional data to accurately extract specific fields from the contract as per the detailed instructions below.
The `"Text Positions"` dictionary is organized by pages, lines and coordinates in the below format:
"Page 1":{{
            "line": text_in_line,
            "coordinates": coordinates_of_line_in_normalized_format
        }}

    -------------------------
    ### KEY INSTRUCTIONS (HIGH-PRIORITY)
    1. Read and understand the `"Extracted Text"` which contains all text from the contract as a single string.
    2. For each field below, identify the relevant value from the Extracted Text and store in the `"Extracted Value"` key.
    3. Locate the text under `"Extracted Value"` in the `"Text Positions"` dictionary to determine its position
    - If the extracted value is in single line, use the coordinates of that line directly
    - If the extracted value spans multiple lines or words from multiple lines, apply the below `"Position Calculation Rules"` to compute the bounding box coordinates
    4. Position Calculation Rules:
       - Find the minimum x-coordinate (left edge) and minimum y-coordinate (top edge) from all relevant text segments
       - Find the maximum x-coordinate (right edge) and maximum y-coordinate (bottom edge) from all relevant text segments
       - Construct the bounding box as: [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]
       - All coordinates are normalized (0.0 to 1.0) relative to page dimensions
    5. If a value spans multiple pages, use the bounding box from the first page only, unless otherwise stated.
    6. If a field's value cannot be found or is not applicable:
       - Set `"Extracted Value"` to "N/A"
       - If Extracted Value is "N/A", omit the Position object entirely for that field. The output schema example should reflect this
    7. Output Requirements:
       - Return a SINGLE valid JSON object
       - Extract values must be EXACT as per instructions, format and examples below
       - Do not return empty strings; use "N/A" where applicable
       - Include ALL fields listed below
       - No additional text, no markdown code blocks, no commentary
       - Ensure proper JSON formatting and UTF-8 encoding

    -------------------------
    ### FIELDS TO EXTRACT
    Extract the following fields exactly as defined below. Use the exact field names provided, with no shortening or different wording. Only use the example to understand the output format, NOT to influence the output value.

    1. Agreement Name
    - **Instruction**: The name of the agreement using the format below. Extract the rights holder party (the entity or person whose rights are being transferred), the rights recipient party (the entity acquiring the rights), the type of agreement, and the date of the agreement in DD Month YYYY format.
    - **Format**: "[Rights Holder Party] <> [Rights Recipient Party] | [Agreement Type] | [Agreement Date in DD Month YYYY format]"
    - **Example**: "Lee Merton Bunnell, Gerald Linford Beckley, Daniel Milton Peek <> Kinney Record Group Limited | Exclusive Recording Agreement | 17 May 1971"

    2. Agreement Type
    - **Instruction**: Only choose one of the following options. The specific type of agreement governing the relationship between the rights holder and rights recipient. Select only one actual type, not the category.
    - **Format**: "[Agreement Type]"
    - **Options**: Publishing: "100% Copyright Assignment", "50% Copyright Assignment", "Co-Publishing Agreement", "Administration Agreement", "Sub-Publishing Agreement", "Songwriter Agreement", "PRO Affiliation Agreement", "MLC Membership Agreement", "Mechanical Licensing Agency Agreement". Recording: "Exclusive Recording Artist Agreement", "Producer Agreement", "Distribution Agreement", "Recording Assignment", "Settlement Agreement", "NRO Mandate", "Production Agreement". Licenses: "Synchronization License", "Master Use License", "Mechanical License", "Public Performance License", "Print License", "Lyric License". Transactional: "Asset Purchase Agreement", "Stock Purchase Agreement", "Copyright Assignment", "Catalog Acquisition Agreement". Other: "Management Agreement", "Talent Agency Agreement", "Merchandising License", "Sponsorship Agreement", "Split Sheet", "Band Agreement", "Side Letter", "Amendment", "Termination Agreement"
    - **Example**: "Exclusive Recording Artist Agreement"

    3. Agreement Date
    - **Instruction**: Date of the agreement.
    - **Format**: "DD Month YYYY"
    - **Example**: "01 March 1972"

    4. Agreement Summary
    - **Instruction**: A concise summary of the agreement in 2-3 sentences, at most 150 characters. Must include: type of agreement, date of agreement, and term of agreement.
    - **Format**: "[Agreement Summary]"
    - **Example**: "Co-Publishing and Administration Agreement covering all compositions written between January 1, 1990 and December 31, 1997."

    5. Rights Holder Party
    - **Instruction**: The party that gives out, transfers, or provides music copyright ownership or rights as denoted in the contract. This party is usually a songwriter, an artist or a licensor, but can also be a publisher or a label giving out rights to another publisher, label, distributor, etc.
    - **Format**: "Comma-separated list of all rights holder parties"
    - **Example**: "Lee Merton Bunnell, Gerald Linford Beckley, Daniel Milton Peek"

    6. Rights Holder Party IPI
    - **Instruction**: The CAE or IPI number of the Rights Holder party, if present.
    - **Format**: "[IPI Number]"
    - **Example**: "I-112549600-8"

    7. Rights Holder Party Address
    - **Instruction**: Address of Rights Holder party, if present.
    - **Format**: "[Address]"
    - **Example**: "123 Music Boulevard, Nashville, Tennessee 37201, USA"

    8. Rights Recipient Party
    - **Instruction**: The party that receives or gets assigned music copyright ownership or other rights as denoted in the contract. This party is usually a publisher, a label, a licensee, or a distributor, etc. 
    - **Format**: "Comma-separated list of all rights recipient parties"
    - **Example**: "Daniel Milton Peek"

    9. Rights Recipient Party IPI
    - **Instruction**: The CAE or IPI number of the Rights Recipient party, if present.
    - **Format**: "[IPI Number]"
    - **Example**: "I-234567890-1"

    10. Rights Recipient Party Address
    - **Instruction**: Address of Rights Recipient party, if present.
    - **Format**: "[Address]"
    - **Example**: "456 Corporate Drive, Los Angeles, California 90001, USA"

    11. Performing Rights Organization
    - **Instruction**: The performing rights organization (PRO) of either the writer or the publisher party. There should only be at most one PRO in the contract, so only return at most one PRO for this field. Examples: BMI, ASCAP, SESAC, GMR, SOCAN, PRS, etc.
    - **Format**: "[PRO Name]"
    - **Example**: "BMI"

    12. Term Start
    - **Instruction**: The start date of the agreement term. If the term does not have a clear start date, it is acceptable to use contract language to substitute for the date.
    - **Format**: "DD Month YYYY or [contract language]"
    - **Example**: "01 March 1972"

    13. Term End
    - **Instruction**: The end date of the agreement term. Try to calculate an exact end date if possible, if the start date and term duration are provided. Include any optional renewals/extensions when determining the end date. If the term does not have a clear end date, it is acceptable to use contract language to substitute for the date (e.g., "Perpetuity", "Until terminated by either party").
    - **Format**: "DD Month YYYY or [contract language]"
    - **Example**: "31 December 1978"

    14. Term Description
    - **Instruction**: The specified term of the agreement between parties. Capture the exact term definition, along with any renewals, extension options, or conditional term structures.
    - **Format**: "[DD Month YYYY] through [DD Month YYYY]", or "[contract language]"
    - **Example**: "01 January 2020 through 01 January 2025"

    15. Territory
    - **Instruction**: The geographic scope where rights are granted under the agreement. Music contracts may be worldwide or limited to specific countries/regions. Note any territory exclusions or special terms for certain regions.
    - **Format**: "[Worldwide/Specific Countries/Regions]"
    - **Example**: "Worldwide" or "United States and Canada excluding Quebec"

    16. Minimum Delivery Commitment
    - **Instruction**: The total number of songs that the writer or artist needs to deliver to the publisher or label during the contract term to satisfy the delivery commitment. Set to 0 if not present.
    - **Format**: [Number]
    - **Example**: 10

    17. Rights Granted
    - **Instruction**: List of all rights given by the Rights Holder Party to the Rights Recipient Party as part of this contract. This should detail all exploitation rights transferred, including but not limited to: reproduction, distribution, public performance, synchronization, mechanical, digital, derivative works, merchandising, audio-visual, and any other enumerated rights. Include any limitations on these rights, exclusivity provisions, and reserved rights that remain with the original rights holder. If multiple rights are granted, list them separated by newlines. Each line of right must begin with a capital letter.
    - **Format**: "[List of rights granted, separated by newlines]", for example: "[Right 1]\\n[Right 2]\\n..."
    - **Example**: "100% of all rights in the recordings (copyright and distribution rights included).\\nExclusive administration rights.\\nNon-exclusive distribution license.\\n..."

    18. Copyright Percentage Assigned
    - **Instruction**: The percentage of music copyright ownership that the Rights Holder Party transfers to the Rights Recipient Party as part of this contract. Return 0 if the contract does not include a transfer of copyright ownership, such as for administration only contracts, subpublishing contracts, or contracts not involving copyright ownership.
    - **Format**: [Number between 0 and 100, no % symbol]
    - **Example**: 100

    19. Exclusivity
    - **Instruction**: Whether the rights granted are exclusive, non-exclusive, or a mix. Capture all details about exclusivity during the term plus any tail/post-term provisions; use-specific exclusivity (e.g., exclusive for some uses, non-exclusive for others); territorial exclusivity variations; any carve-outs to exclusivity. Do not return a one-word "Exclusive" when nuance exists. If there are multiple rights to explain, return a newline-separated list, with each line beginning with a capital letter.
    - **Format**: "[Details]"
    - **Example**: "Exclusive for streaming platforms during the term.\\nNon-exclusive for radio broadcasts."

    20. Reserved Rights
    - **Instruction**: Rights specifically reserved by the Rights Holder Party - rights not transferred or licensed under the contract. Common reservations include sync rights, derivative works rights, merchandising, or specific uses subject to approval. If multiple rights are reserved, list them separated by newlines. Each line of right must begin with a capital letter.
    - **Format**: "[List of reserved rights, separated by newlines]", for example: "[Right 1]\\n[Right 2]\\n..."
    - **Example**: "Synchronization rights for motion pictures\\nMerchandising rights\\nDerivative works rights"

    21. Approval Rights
    - **Instruction**: Specific uses of copyrighted material that require the original rights holder's explicit approval. Common examples include synchronization licenses, sampling, merchandise, and other high-value or reputation-impacting uses. If multiple approval rights apply, list them separated by newlines. Each line of right must begin with a capital letter.
    - **Format**: "[List of uses requiring approval, separated by newlines]", for example: "[Right 1]\\n[Right 2]\\n..."
    - **Example**: "Commercial exploitation of demos\\nUse of Artist's name, likeness, and biographical data in connection with exploitation"

    22. Reversion Rights
    - **Instruction**: Specific provisions describing when and how rights return to the original owner, often a songwriter or recording artist, but can also be a rightsholder who granted rights to an administrator or subpublisher. Include all contractual reversions and whether they occur automatically or require formal notices. Include triggers.
    - **Format**: "[conditions when rights revert]"
    - **Example**: "Rights will automatically revert to the Artist upon expiration of the term unless the Publisher provides written notice of intent to renew at least 90 days prior to term end."

    23. Assignability
    - **Instruction**: Provisions governing whether and how the agreement can be transferred to another party. May be freely assignable, require prior written consent, or contain specific assignment restrictions or requirements.
    - **Format**: "[Details]"
    - **Example**: "Either party may assign this Agreement without the other party's consent to any affiliate or in connection with a merger, acquisition, or sale of all or substantially all of its assets."

    24. Advances
    - **Instruction**: Details about any advance payments made by the Rights Recipient Party to the Rights Holder Party, including amounts, payment schedule, and recoupment provisions.
    - **Format**: "[Details]"
    - **Example**: "$50,000 advance payable upon signing; recoupable from the first royalties earned"

    25. Royalty Rates
    - **Instruction**: List of all royalty rates by type. Use concise language when describing the type and rates, unless detailed language is required to describe the type of royalty. Where rates are tied to specific conditions or thresholds, note those dependencies. Always use "%" instead of the word "percentage". If there are multiple types of royalty rates, list them separated by newlines.
    - **Format**: "[List of all royalty rates by type, separated by newlines]"
    - **Example**: "Records sold in the U.S. and Canada: 13%\\nRecords sold in the UK, Australia and Germany: 9%\\nStreaming: 8% per stream"

    26. Accounting Frequency
    - **Instruction**: How often royalty statements and payments must be issued to rights holders. Usually "Annually", "Quarterly", "Semi-annually", etc.
    - **Format**: "[Accounting frequency]"
    - **Example**: "Semi-annually"

    27. Accounting Lag
    - **Instruction**: The contractually permitted delay between the end of a statement period and when payment must be issued. Express this in number of days.
    - **Format**: "[Number] days"
    - **Example**: "60 days"

    28. Audit Rights
    - **Instruction**: Provisions allowing the Artist party to examine accounting records to verify proper royalty payments. Include audit frequency, scope limitations, frequency restrictions, lookback periods, and any special procedures or penalties.
    - **Format**: "[details of audit rights]"
    - **Example**: "Licensee's books may be audited once per calendar year, no more than once per accounting period, by an independent certified public accountant. Audit must be initiated within three years after statement date. Auditor bound by confidentiality agreement."

    29. Governing Law and Jurisdiction
    - **Instruction**: Details about the state and/or country whose laws govern the interpretation and enforcement of the contract, as well as the venues, courts, arbitration forums within the governing law location where disputes about the contract must be resolved.
    - **Format**: "[Location of governing law and jurisdiction]"
    - **Example**: "State and federal courts located in Los Angeles County, California"

    -------------------------
    ### EXTRACTION RULES
    - Output format (strict):
    Each field must be returned as:
    "Field Name": {{
    "Extracted Value": "",
    "Position": {{
        "Page": "",
        "Coordinates": [
        [x1, y1],
        [x2, y2],
        [x3, y3],
        [x4, y4]
        ],
    }},
    }}
    - Correct obvious typos, garbled text or formatting issues by applying logic and common sense.

    -------------------------
    ### OUTPUT SCHEMA (EXAMPLE)
    Return exactly one JSON object with these entries (example with two fields shown):
    {{
        "Rights Holder Party": {{
            "Extracted Value": "John C. Adams",
            "Position": {{
                "Page": 1,
                "Coordinates": [
                    [0.114, 0.147],
                    [0.924, 0.147],
                    [0.924, 0.993],
                    [0.114, 0.993]
                ],
            }}
        }},
        "Rights Holder Party IPI": {{
            "Extracted Value": "N/A",
        }},
    }}

    -------------------------
    ### FINAL RULES
    - Output **only** the JSON object. No markdown, no commentary, no debug output.
    - Ensure JSON is valid, parseable and UTF-8 clean.

    ### INPUTS
    Extracted Text: {Extracted_text}
    Text Positions: {Text_positions}

    -------------------------
"""
