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
       - Extract values must be EXACT as per instructions,format and examples below
       - Do not return empty strings; use "N/A" where applicable
       - Include ALL fields listed below
       - No additional text, no markdown code blocks, no commentary
       - Ensure proper JSON formatting and UTF-8 encoding

    -------------------------
    ### FIELDS TO EXTRACT
    Extract the following fields exactly as defined below. Use the exact field names provided, with no shortening or different wording. Only use the example to understand the output format, NOT to influence the output value.

    --- SECTION 1: GENERAL ---

    1. Catalog
    - **Instruction**: The name of the artist, writer, producer, band, or other creative person(s) whose works are included in the rights acquired by PW. This is typically the primary subject of the APA — the person whose creative works are being bought and sold.
    - **Format**: "[Catalog Name]"
    - **Example**: "John C. Adams"

    2. General Rights Tags
    - **Instruction**: High-level tags for the category(ies) of rights PW may have acquired. Select ALL that apply. Select PUBLISHING if PW is acquiring any interest in musical compositions, including copyrights, administration rights, publisher's share income, writer's share income, or any passive income rights relating to compositions. Select RECORDINGS if PW is acquiring any interest in sound recordings (masters), including copyrights, distribution rights, artist royalties, neighboring rights, or any passive income rights relating to recordings. Select ARTIST INDICIA if PW is acquiring or receiving any rights to use an artist's name, likeness, image, voice, or biographical information. Select BRANDING RIGHTS if PW is acquiring or receiving any branding, merchandising, or endorsement rights. Select ARTIST CONTENT RIGHTS if PW is acquiring or receiving any rights relating to life story, documentary, biopic, live stage, or similar content projects. Select TRADEMARKS if PW is acquiring any registered or unregistered trademarks. Select OTHER if PW is acquiring rights that do not fit into any of the above categories.
    - **Format**: "A newline-separated list of applicable tags, each one of: PUBLISHING, RECORDINGS, ARTIST INDICIA, BRANDING RIGHTS, ARTIST CONTENT RIGHTS, TRADEMARKS, OTHER"
    - **Example**: "PUBLISHING\\nRECORDINGS"

    3. Acquisition Summary
    - **Instruction**: A brief high-level summary of the acquisition using the format below. Fill in each subsection that applies based on the General Rights Tags. Omit any subsection that does not apply. Replace bracketed placeholders with actual deal terms. If PW acquired different percentages for different sub-rights within a category, reflect each percentage separately. If a subsection does not apply to the deal, omit it entirely. If the APA does not specify percentages for a sub-right, describe the right qualitatively.
    - **Format**: "PW owns:\\n(a) Publishing: [X]% of Seller's rights in all musical compositions written by [NAME(S)] as of [DATE] and [X]% of copyrights, [X]% of administration rights, [X]% of contract rights, and [X]% of income related to those compositions.\\n(b) Recordings: [X]% of Seller's rights in all recordings featuring [NAME(S)] as of [DATE] and [X]% of copyrights, [X]% of distribution rights, [X]% of contract rights, and [X]% of income related to those recordings.\\n(c) Artist Indicia: [describe rights].\\n(d) Branding Rights: [describe rights].\\n(e) Artist Content Rights: [describe rights].\\n(f) Trademarks: [describe rights]."
    - **Example**: "PW owns:\\n(a) Publishing: 75% of Seller's rights in all musical compositions written by John Adams as of 01 January 2020 and 75% of copyrights, 100% of administration rights, 75% of contract rights, and 75% of income related to those compositions."

    4. Rights Status
    - **Instruction**: A brief general description of whether PW or a third party own/control the works. Describe the ownership and control status of each major asset category. This should explain, at a practical level, what PW actually owns versus what third parties control.
    - **Format**: "[Description of ownership and control status per asset category]"
    - **Example**: "Compositions written before 01 January 1979 owned by WCM, passive income rights only. Compositions written on or after 01 January 1979, copyrights and administration rights owned by PW."

    5. Additional Acquisition Summary Details
    - **Instruction**: Any quirks with the deal that need to be highlighted up front and are not specifically captured in other fields. This includes collection/administration anomalies, copyright anomalies, multiple purchasers, unusual payment waterfalls, band entity structures, business management intermediaries, or any other atypical structural features. If none, return "None."
    - **Format**: "[Description of quirks or anomalies, or 'None']"
    - **Example**: "Royalty collections are handled by a legacy administrator outside the primary platform, and monthly statements are provided as manual CSV uploads. There may be delays of up to 30 days in revenue reporting and reconciliation."

    6. Date of Acquisition Agreement
    - **Instruction**: The date of the APA as stated in the preamble. Use the date format: DD Month YYYY (e.g., "01 January 2025"). If the APA is undated, use the last signature date. If no date can be determined, use null.
    - **Format**: "DD Month YYYY"
    - **Example**: "01 January 2025"

    7. Cash Date
    - **Instruction**: The Cash Date specified in the APA — the date from which PW is entitled to collect income on the acquired assets. Use the standard date format: DD Month YYYY. If the Cash Date is not specified or is the same as the closing date, state "Same as closing date" or extract the specific date if provided.
    - **Format**: "DD Month YYYY or 'Same as closing date'"
    - **Example**: "01 January 2025"

    8. PW Business Affairs Contact
    - **Instruction**: The name of the internal PW business affairs person who supervised the acquisition, if identifiable from the APA or its notices section. Common contacts include Amy Ortner, Sam Rhulen, and Lexi Todd. If not identifiable from the document, return "Not specified in APA."
    - **Format**: "[Name or 'Not specified in APA']"
    - **Example**: "Amy Ortner"

    9. PW Outside Counsel
    - **Instruction**: The name of the primary outside counsel firm and individual attorneys that worked on the transaction, if identifiable from the APA. Look in the notices section, signature blocks, and any references to counsel. If not identifiable, return "Not specified in APA."
    - **Format**: "[Firm and/or attorney name(s), or 'Not specified in APA']"
    - **Example**: "Smith & Jones LLP (Jane Smith)"

    10. Seller Parties (Individual)
    - **Instruction**: Each Seller contracting party that is an individual (natural person). List each individual separately using newline characters. If there are no individual Seller parties, return "None."
    - **Format**: "A newline-separated list of individual Seller party names, or 'None'"
    - **Example**: "John Adams\\nJane Adams"

    11. Seller Parties (Other)
    - **Instruction**: Each Seller contracting party that is not an individual (i.e., entities such as LLCs, corporations, trusts, estates). List each entity separately with its full legal name and entity type as stated in the APA. Use newline characters to separate multiple entries. If there are no entity Seller parties, return "None."
    - **Format**: "A newline-separated list of entity Seller parties with full legal name and entity type, or 'None'"
    - **Example**: "Adams Music LLC (Delaware limited liability company)\\nAdams Publishing Trust"

    12. Seller Counsel
    - **Instruction**: The name of Seller's counsel, if identifiable from the APA. Look in the notices section, signature blocks, and any references to Seller's counsel or attorneys. If not identifiable, return "Not specified in APA."
    - **Format**: "[Firm and/or attorney name(s), or 'Not specified in APA']"
    - **Example**: "Davis & Moore LLP"

    13. Seller Personal Manager
    - **Instruction**: The name of Seller's personal manager, if identifiable from the APA. Look in the notices section, approval provisions, and any references to personal management. If not identifiable, return "Not specified in APA."
    - **Format**: "[Name, or 'Not specified in APA']"
    - **Example**: "Not specified in APA"

    14. Seller Business Manager
    - **Instruction**: The name of Seller's business manager or business management firm, if identifiable from the APA. Look in the notices section, accounting provisions, and any references to business management. If not identifiable, return "Not specified in APA."
    - **Format**: "[Name or firm, or 'Not specified in APA']"
    - **Example**: "Not specified in APA"

    15. Purchaser
    - **Instruction**: The PW contracting party(ies). Extract the full legal entity name(s) of the Purchaser as stated in the APA preamble or definitions. PW typically acquires through fund-specific entities (e.g., "Primary Wave Music IP Fund 4 US Sub LLC").
    - **Format**: "[Full legal entity name(s) of Purchaser]"
    - **Example**: "Primary Wave Music IP Fund 4 US Sub LLC"

    16. Holdbacks
    - **Instruction**: Details of the Royalties Holdback and other holdbacks (if applicable), including holdback amount(s) at closing and holdback release terms. If there are multiple holdbacks, describe each one separately. If there are no holdbacks, return "None."
    - **Format**: "[Description of each holdback including amount and release terms, or 'None']"
    - **Example**: "None"

    17. Right of First Negotiation / Matching Rights
    - **Instruction**: Details of any first negotiation or matching rights from the APA between Seller and Purchaser. Include the specific trigger, the time period for each right, and the assets to which they apply. If none, return "None."
    - **Format**: "[Description of right including trigger, time period, and assets, or 'None']"
    - **Example**: "None"

    18. Additional Purchase Price
    - **Instruction**: Details of any earnout(s), bonus payments, and other additional money payable to Seller that is triggered by an event from the APA. Include the trigger event, calculation methodology, payment timeline, and any caps or floors. If none, return "None."
    - **Format**: "[Description of each additional payment including trigger, calculation, timeline, caps/floors, or 'None']"
    - **Example**: "None"

    19. Press Releases / Public Announcements
    - **Instruction**: Details of any approval process or restrictions on press releases and public announcements from the APA. If the APA is silent, return "Silent."
    - **Format**: "[Description of approval process or restrictions, or 'Silent']"
    - **Example**: "Silent"

    20. Restrictions on Seller
    - **Instruction**: Details of any non-standard restrictions on the Seller from the APA. Do NOT summarize boilerplate restrictions from PW's standard form APA that appear in all acquisitions (such as no amendments to existing agreements, no advances, no insolvency, indemnification approvals) unless they differ from standard form language or were substantially negotiated. Specifically look for: (1) Re-Recording Restrictions — any restrictions on Seller's ability to create re-recordings of acquired recordings; (2) AI Restrictions — any restrictions on Seller's ability to authorize use of transferred assets for training artificial intelligence; (3) Non-Compete / Non-Solicitation — any restrictions on Seller's competitive activities; (4) Other Negotiated Restrictions — any other restrictions specifically negotiated for this deal. If there are no non-standard restrictions, return "Standard form restrictions only."
    - **Format**: "[Description of non-standard restrictions, or 'Standard form restrictions only']"
    - **Example**: "Standard form restrictions only"

    21. Additional Purchaser Obligations
    - **Instruction**: Details of any additional obligations of the Purchaser from the APA beyond standard form, such as documentary financing, marketing commitments, key-person clauses. Do NOT summarize boilerplate obligations from PW's standard form APA. If none beyond standard form, return "Standard form obligations only."
    - **Format**: "[Description of additional purchaser obligations, or 'Standard form obligations only']"
    - **Example**: "Standard form obligations only"

    22. Additional Seller Obligations
    - **Instruction**: Details of any additional obligations of the Seller from the APA beyond standard form, such as marketing commitments, copyright registrations, PRO registrations, consents, delivery of revised schedules. Do NOT summarize boilerplate obligations from PW's standard form APA. If none beyond standard form, return "Standard form obligations only."
    - **Format**: "[Description of additional seller obligations, or 'Standard form obligations only']"
    - **Example**: "Standard form obligations only"

    23. Governing Law of Acquisition Agreement
    - **Instruction**: The governing law of the APA. Return ONLY the jurisdiction (e.g., "New York") and NOT the forum for disputes.
    - **Format**: "[Jurisdiction]"
    - **Example**: "New York"

    24. Jurisdiction and Venue for Acquisition Agreement Disputes
    - **Instruction**: The jurisdiction and venue for disputes arising under the APA. Include both the court(s) and the geographic location.
    - **Format**: "[Court(s) and geographic location]"
    - **Example**: "State and federal courts located in New York County, NY"

    25. Indemnification
    - **Instruction**: Summary of APA indemnification provisions, procedures, and limitations. Provide a structured summary covering: (1) Scope — who indemnifies whom and for what categories of losses; (2) Joint and Several — whether Seller parties are jointly and severally liable; (3) Claim Requirements — whether claims must be reduced to final judgment or can be settled; (4) Notice — notice requirements and whether failure to give notice is deemed a waiver; (5) Defense — who controls defense of third-party claims, counsel approval rights; (6) Settlement — whether indemnitee can settle without indemnitor consent; (7) Offset Rights — whether PW can offset indemnification claims against amounts due to Seller; (8) Caps and Baskets — any caps on liability, deductible baskets, or tipping baskets; (9) Survival — how long representations and warranties survive closing. Do not extract verbatim text for this field.
    - **Format**: "[Structured summary covering each of the 9 categories above]"
    - **Example**: "1. Scope: Seller indemnifies PW for breaches of representations and excluded liabilities. PW indemnifies Seller for PW's post-closing exploitation of assets.\\n2. Joint and Several: Yes.\\n..."

    26. Additional Notes
    - **Instruction**: Any additional general notes not covered elsewhere — items a PW business affairs or legal team member should be aware of that do not fit neatly into other fields. If none, return "None."
    - **Format**: "[Additional notes, or 'None']"
    - **Example**: "None"

    --- SECTION 2: ASSET DETAILS ---

    27. PW Acquired Interest (%)
    - **Instruction**: The high-level percentage of Seller's interest that PW acquired, expressed as a decimal (e.g., 0.75 for 75%). If PW bought different percentages for different asset categories, use the primary/overall acquisition percentage.
    - **Format**: [Decimal number, e.g. 0.75]
    - **Example**: 0.75

    28. Seller Retained Interest (%)
    - **Instruction**: The high-level percentage of Seller's interest that Seller retained, expressed as a decimal (e.g., 0.25 for 25%). This should be the complement of PW Acquired Interest (%).
    - **Format**: [Decimal number, e.g. 0.25]
    - **Example**: 0.25

    29. Rights Acquired (By Type)
    - **Instruction**: The specific types of assets PW purchased, organized by asset category. For Publishing, select all that apply from: Publishing Copyrights, Publishing Administration Rights, Publisher's Share Income, Writer's Share Non-Performance Income, Writer's Share Performance Income. For Recordings, select all that apply from: Recording Copyrights, Recording Distribution Rights, Copyright Owner Income, Artist Royalties, Neighboring Rights Income (Featured Artist Share), Neighboring Rights Income (Copyright Owner Share), Producer Royalties. For Artist Indicia, describe whether PW acquired an interest in artist indicia or only non-exclusive rights to use artist indicia, including any limitations. For Branding Rights, indicate whether Exclusive or Non-Exclusive and list commission details if applicable. For Artist Content Rights, describe scope and list commission details if applicable. For Trademarks, indicate whether Registered, Unregistered, or both. For Other, describe scope.
    - **Format**: "[Structured description of all rights acquired by category, using newlines to separate categories and items]"
    - **Example**: "Publishing:\\n- Publishing Copyrights\\n- Publishing Administration Rights\\n- Publisher's Share Income\\n\\nRecordings:\\n- Recording Copyrights\\n- Artist Royalties"

    30. Excluded Assets and/or Excluded Rights
    - **Instruction**: Description of specifically excluded assets and/or rights — i.e., rights that PW did not buy. Include any temporal, geographic, or categorical exclusions. If none are specified, return "None specified."
    - **Format**: "[Description of excluded assets and rights, or 'None specified']"
    - **Example**: "None specified"

    31. Income Sources
    - **Instruction**: List of income sources by publishing, recordings, and other. These are the third-party payors (e.g., labels, publishers, PROs, distributors) from which PW will collect income on the acquired assets. List each source separately using newline characters.
    - **Format**: "A newline-separated list of income sources"
    - **Example**: "Universal Music Group (recording royalties)\\nASCAP (performance royalties)\\nSony Music Publishing (mechanical royalties)"

    32. Current PRO
    - **Instruction**: The PRO the writer is currently affiliated with, as well as any other PROs currently licensing any compositions. Examples: ASCAP, BMI, SESAC, GMR, PRS, GEMA, SACEM. If not specified, return "Not specified."
    - **Format**: "[PRO name(s), or 'Not specified']"
    - **Example**: "ASCAP"

    33. Current NRO
    - **Instruction**: The neighboring rights organization(s) currently collecting for the sound recordings. Examples: SoundExchange, PPL, SENA, GVL. If not specified, return "Not specified."
    - **Format**: "[NRO name(s), or 'Not specified']"
    - **Example**: "SoundExchange"

    34. Current Trademark Portfolio
    - **Instruction**: Note whether the APA includes or references a schedule of trademarks with registration information. If so, state "See schedule of trademarks [reference the specific exhibit or schedule]." If no trademark schedule, return "No trademark schedule."
    - **Format**: "'See schedule of trademarks [exhibit/schedule reference]' or 'No trademark schedule'"
    - **Example**: "No trademark schedule"

    --- SECTION 3: POST-CLOSING ASSET MANAGEMENT ---

    35. Go-Forward Arrangements
    - **Instruction**: Any go-forward arrangements arising from the APA. For example, go-forward administration or distribution agreements, management agreements, or service agreements between PW and Seller or third parties. If none, return "N/A."
    - **Format**: "[Description of go-forward arrangements, or 'N/A']"
    - **Example**: "N/A"

    36. Possible Additional Rights
    - **Instruction**: Any purchase options, swap agreements, or similar provisions allowing PW to acquire additional rights in the future (separate from first negotiation or matching rights). If none, return "N/A."
    - **Format**: "[Description of possible additional rights, or 'N/A']"
    - **Example**: "N/A"

    37. Exclusivity Restrictions
    - **Instruction**: Any exclusivity restrictions Seller or Purchaser agreed to post-closing. For example, exclusive licenses, exclusive distribution arrangements, or territorial exclusivity granted to third parties that PW must honor. Include the identity of the third party, the scope of exclusivity, the territory, and the term. If none, return "None."
    - **Format**: "[Description of exclusivity restrictions including third party, scope, territory, and term, or 'None']"
    - **Example**: "None"

    38. Other (Post-Closing)
    - **Instruction**: Any other post-closing asset management provisions. For example, archival budgets, processes for storing physical assets, digitization obligations, joint exploitation committees, or creative consultation rights. If none, return "None."
    - **Format**: "[Description of other post-closing provisions, or 'None']"
    - **Example**: "None"

    39. PW Rights of Distribution Start Date
    - **Instruction**: Only populate if the APA indicates that PW has acquired rights of distribution for sound recordings and PW will be taking over distribution after closing. The first date on which PW will have the contractual right to take over rights of distribution. Use the standard date format: DD Month YYYY. If PW did not acquire distribution rights, return "N/A."
    - **Format**: "DD Month YYYY or 'N/A'"
    - **Example**: "N/A"

    40. Acquired Rights of Distribution Territory
    - **Instruction**: Only populate if PW acquired distribution rights. The territory in which PW has acquired distribution rights. If worldwide, state "Worldwide." If subject to territorial exclusions, state "Worldwide excluding [territories]." If PW did not acquire distribution rights, return "N/A."
    - **Format**: "'Worldwide', 'Worldwide excluding [territories]', or 'N/A'"
    - **Example**: "N/A"

    41. Current Distributor
    - **Instruction**: Only populate if PW acquired distribution rights. The current distributor of the sound recordings, if identified in the APA. If PW did not acquire distribution rights, return "N/A."
    - **Format**: "[Distributor name, or 'N/A']"
    - **Example**: "N/A"

    42. Current Distributor Governing Agreement
    - **Instruction**: Only populate if PW acquired distribution rights. The name of the relevant governing agreement that governs the current distributor's distribution rights. Use the format: "[Party A] f/s/o [Party B] <> [Distributor] - [Agreement Type] - [Date]" if identifiable. If PW did not acquire distribution rights, return "N/A."
    - **Format**: "[Agreement name in specified format, or 'N/A']"
    - **Example**: "N/A"

    43. Termination Notice Required
    - **Instruction**: Only populate if PW acquired distribution rights. Whether termination notice is required to terminate the current distribution agreement and, if so, the notice period and deadline. If PW did not acquire distribution rights, return "N/A."
    - **Format**: "[Yes/No and notice period/deadline, or 'N/A']"
    - **Example**: "N/A"

    44. Videos Included
    - **Instruction**: Only populate if PW acquired distribution rights. Whether the distribution rights include audio-visual recordings (music videos). Select "Yes" or "No." If only audio-only recordings, select "No." If PW did not acquire distribution rights, return "N/A."
    - **Format**: "'Yes', 'No', or 'N/A'"
    - **Example**: "N/A"

    45. Other PW Distribution Obligations
    - **Instruction**: Only populate if PW acquired distribution rights. Any other contractual obligations under the APA relating to PW's exercise of rights of distribution. For example, commercial exploitation deadlines, minimum release commitments, or marketing spend requirements. If PW did not acquire distribution rights, return "N/A." If PW acquired distribution rights but there are no other obligations, return "None."
    - **Format**: "[Description of other distribution obligations, 'None', or 'N/A']"
    - **Example**: "N/A"

    --- SECTION 4: APPROVAL DETAILS ---

    46. PW Obligation to Obtain Seller Approval (Outgoing)
    - **Instruction**: List of Seller's approval rights from the APA — i.e., instances when PW must obtain Seller's approval before taking action. List each approval category separately using newline characters. Do NOT list standard boilerplate approvals that appear in every PW form APA unless they were substantively negotiated. Common approval categories include: Branding licenses; Synchronization licensing for specified categories (e.g., motion pictures, audio-visual use, X-rated films, NC-17 rated content, pornographic material, political uses, religious uses, alcohol, tobacco, firearms, personal hygiene products, drugs, fur products); Lyric reprints; Use of lyrics as a title of a work; Foreign language translations; Samples / interpolations; Grand rights uses; Purchaser-secured branding agreements. If none, return "None."
    - **Format**: "A newline-separated list of approval categories, or 'None'"
    - **Example**: "Synchronization licensing for pornographic material\\nGrand rights uses\\nSamples / interpolations"

    47. Approval Procedure
    - **Instruction**: The timeline for responses, what happens if no response is given, and the procedure when multiple approval parties are involved. Specifically extract: (1) Standard of approval (e.g., "not to be unreasonably withheld or delayed"); (2) Deemed approval provisions (e.g., "deemed approved if not rejected within 3 business days"); (3) Multiple approval party procedures. If silent, return "Silent."
    - **Format**: "[Description of approval procedure covering standard of approval, deemed approval, and multiple party procedures, or 'Silent']"
    - **Example**: "Silent"

    48. Seller Approval Contact
    - **Instruction**: Name and contact information for each approval contact. Include email addresses and any cc requirements. If not specified, return "Not specified."
    - **Format**: "[Name and contact information for each approval contact, or 'Not specified']"
    - **Example**: "Not specified"

    --- SECTION 5: ACCOUNTING & AUDIT ---

    49. Accounting Frequency to Seller
    - **Instruction**: How often PW must account to Seller for Seller Retained Interest. Select ONLY one: Monthly, Quarterly, Semi-Annually, Annually, Other, Silent. If the APA specifies a different frequency for different asset categories, select "Other" and explain.
    - **Format**: "[Monthly / Quarterly / Semi-Annually / Annually / Other / Silent]"
    - **Example**: "Semi-Annually"

    50. Accounting Lag to Seller
    - **Instruction**: How many days after the end of the applicable accounting period PW must account to Seller. Extract the specific number of days (e.g., "90 days," "60 days," "120 days"). If the APA specifies a different calculation (e.g., "45 days after receipt by Purchaser of the applicable third-party statement"), extract that specific language.
    - **Format**: "[Number] days or [specific language]"
    - **Example**: "90 days"

    51. Seller Statement Recipient(s)
    - **Instruction**: Name and contact information for each person that receives royalty statements from PW to Seller. Include email addresses and mailing addresses if specified.
    - **Format**: "[Name and contact information for each statement recipient]"
    - **Example**: "Not specified"

    52. Other Royalty Participants (Companies)
    - **Instruction**: Payments to third-party company payees required under the APA. For each, extract: the identity of the payee, the financial terms (percentage, receipts pool, deductions), accounting frequency, statement recipients, and all other relevant terms. If none, return "None."
    - **Format**: "[Description of each company royalty participant with all relevant terms, or 'None']"
    - **Example**: "None"

    53. Other Royalty Participants (Individuals)
    - **Instruction**: Payments to third-party individual payees required under the APA. For each, extract: the identity of the payee, the financial terms (percentage, receipts pool, deductions), accounting frequency, statement recipients, and all other relevant terms. If none, return "None."
    - **Format**: "[Description of each individual royalty participant with all relevant terms, or 'None']"
    - **Example**: "None"

    54. Seller Rights to Audit PW
    - **Instruction**: Details on Seller's rights to audit the books of PW. Provide a structured summary covering: (1) Auditor qualifications — who can conduct the audit; (2) Audit scope and frequency — duration, notice requirements, business hours, whether audits must be at PW's office; (3) Objection period — how long Seller has to audit or object to a statement; (4) Deadline to sue — time limit for Seller to bring a legal claim based on a statement; (5) Audit frequency limitation — how often statements may be audited; (6) Cost shifting — whether PW must pay for the audit if an underpayment exceeding a threshold is found.
    - **Format**: "[Structured summary of audit rights covering each of the 6 categories above]"
    - **Example**: "1. Auditor Qualifications: CPA experienced in music industry audits.\\n2. Audit Scope: Once per year, upon 30 days' notice, during PW's normal business hours.\\n..."

    55. Pre-Closing Audits by Seller
    - **Instruction**: List of any pre-closing audits conducted by Seller referenced in the APA. Include the auditee, the audit period, and the settlement date/status if known. If none referenced, return "None referenced."
    - **Format**: "[Description of each pre-closing audit, or 'None referenced']"
    - **Example**: "None referenced"

    --- SECTION 6: SELLER RETAINED INTEREST FINANCIAL TERMS ---

    56. Percentage of Revenue Received by PW
    - **Instruction**: The percentage of income PW collects. Clarify whether PW collects both PW's share and the Seller Retained Interest (i.e., PW collects 100% and then accounts to Seller for Seller's share), or only PW's share. Express as a decimal (e.g., 1.0 if PW collects 100%, 0.75 if PW collects only its share).
    - **Format**: [Decimal number, e.g. 1.0]
    - **Example**: 1.0

    57. Seller Retained Interest Percentage
    - **Instruction**: The percentage of income that was retained by the Seller when PW acquires less than 100%. Express as a decimal (e.g., 0.25 for 25%).
    - **Format**: [Decimal number, e.g. 0.25]
    - **Example**: 0.25

    58. Other Payable Percentages
    - **Instruction**: Any other amounts payable to Seller by PW under the APA that are separate from the standard Seller Retained Interest accounting. For example: commissions on Purchaser-secured branding licenses, shares of pre-Cash Date audit recoveries, or other special payments. For each, include the percentage, the receipts pool, and any conditions. If none, return "None."
    - **Format**: "[Description of each other payable percentage, or 'None']"
    - **Example**: "None"

    59. PW Administration Fee
    - **Instruction**: The administration fee PW is entitled to charge Seller as a percentage, per the APA. This typically applies if PW self-administers the compositions. Include the percentage and the base against which it is calculated. If none, return "None."
    - **Format**: "[Percentage and base, or 'None']"
    - **Example**: "15% of gross revenues if PW self-administers Compositions"

    60. PW Distribution Fee
    - **Instruction**: The distribution fee PW is entitled to charge Seller as a percentage, per the APA. This typically applies if PW self-distributes the recordings. Include the percentage and the base against which it is calculated. If none, return "None."
    - **Format**: "[Percentage and base, or 'None']"
    - **Example**: "25% of gross revenues if PW self-distributes Recordings"
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
        "Writer Party": {{
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
        "Publishing Designee(s) IPI Number": {{
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
