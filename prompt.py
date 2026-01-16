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

    1. Account Name
    - **Instruction**: Full legal name of the songwriter or artist party. If an entity acts on behalf of the writer, treat the writer as the party or account instead. Use title case. Do not include aliases, p/k/a, or f/s/o names.
    - **Format**: "[Full Legal Name of Writer]"
    - **Example**: "John C. Adams"

    2. First Name
    - **Instruction**: First name of the songwriter or artist party.
    - **Format**: "[First Name of Writer]"
    - **Example**: "John"

    3. Last Name
    - **Instruction**: Last name of the songwriter or artist party.
    - **Format**: "[Last Name of Writer]"
    - **Example**: "Adams"

    4. Type
    - **Instruction**: The role of the songwriter or artist party. Either "Artist" or "Songwriter".
    - **Format**: "[Artist / Songwriter]"
    - **Example**: "Songwriter"

    5. Billing Street
    - **Instruction**: Street address of the songwriter or artist party as stated in the agreement.
    - **Format**: "[Street Address]"
    - **Example**: "114 El Camino Real"

    6. Billing City
    - **Instruction**: City of the songwriter or artist party as stated in the agreement.
    - **Format**: "[City]"
    - **Example**: "Berkeley"

    7. Billing Zip/Postal Code
    - **Instruction**: ZIP or postal code of the songwriter or artist party as stated in the agreement.
    - **Format**: "[ZIP / Postal Code]"
    - **Example**: "94705"

    8. Billing State/Province
    - **Instruction**: State or province of the songwriter or artist party as stated in the agreement.
    - **Format**: "[State / Province]"
    - **Example**: "California"

    9. Billing Country
    - **Instruction**: Country of the songwriter or artist party as stated in the agreement. If the country is not present but the city and/or state are, infer the country from the city or state.
    - **Format**: "[Country]"
    - **Example**: "United States"

    10. Concord Party
    - **Instruction**: The full organization name (as appeared in the contract) of the Concord entity acting as the publisher party of the contract.
    - **Format**: "[Concord Entity Name]"
    - **Example**: "Hendon Music Limited"

    11. Performing Rights Organization
    - **Instruction**: The performing rights organization (or PRO) of either the writer or the publisher party. There should only be at most one PRO in the contract, so only include one PRO in this field.
    - **Format**: "[BMI / ASCAP / SESAC / GMR / SOCAN / PRS / AllTrack / SoundExchange / ...]"
    - **Example**: "BMI"

    12. Agreement Type
    - **Instruction**: Type of the contract. Always use one of the pre-defined types below, and do not use any other type. Predefined types are: "Full Publishing": assignment of entire copyright, "Co-Publishing": shared ownership, "Admin": administration only, no ownership, "JV": joint venture language, "Cut-in": applies only to specific compositions.
    - **Format**: [Full Publishing / Co-Publishing / Admin / JV / Cut-in]"
    - **Example**: "Full Publishing"

    13. Agreement Name
    - **Instruction**: Name of the agreement according to the defined format below.
    - **Format**: "[Account Name (field 1)] - [Date of Agreement in DD Month YYYY] - [Agreement Type (field 12)] Agreement"
    - **Example**: "John C. Adams - 01 January 1992 - Full Publishing Agreement"

    14. Year
    - **Instruction**: The year the contract was created or executed.
    - **Format**: "YYYY"
    - **Example**: "1992"

    15. Effective Date
    - **Instruction**: Effective date of the contract, or the starting date of the contract term. If no specific effective or starting date is given but the term is provided, use phrases from the contract language such as 'date of execution of contract', but only if no exact date is available. Always try to extract an exact start date if possible.
    - **Format**: "[DD Month YYYY] if exact date, or [Text] if not"
    - **Example**: "01 January 1992"

    16. Execution Date
    - **Instruction**: Date the contract was executed or signed.
    - **Format**: "DD Month YYYY"
    - **Example**: "01 January 1992"

    17. Commitment End Date
    - **Instruction**: The committed ending date of the contract term, or the date the contract is no longer effective. If no specific end date is given but a specific start date and term duration are provided, calculate the end date based on the start date and the initial term duration. For this calculation, only consider the initial term and ignore any option periods, extensions, or renewals. If a term exists but the end date cannot be extracted or calculated, you may ignore the date formatting guidelines and use phrases from the contract language such as '5 years after beginning of term', 'until X event happens', or 'perpetuity', but only if no exact date is available. Always try to extract or calculate an exact end date if possible.
    - **Format**: "[DD Month YYYY] if exact date, or [Text] if not"
    - **Example**: "01 January 1992"

    18. Currency
    - **Instruction**: The 3-letter code of the main currency used throughout the contract.
    - **Format**: "[3-Letter Currency Code]"
    - **Example**: "USD"

    19. Assignability of Contract Details
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes information about assignability. Also include information about anti-assignment clauses that block the transfer or purchase of ownership rights to another party. Only include cases where assignability can be actively triggered by a party, not passive transfers to a party's successor such as through acquisition or bankruptcy. If the contract has no Assignability Provision, set it to "N/A".
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 23) We shall have the right to assign... [rest of Assignability Provision]"

    20. Change of Control Details
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes information about change of control. This covers cases where a third party buys or takes over the equity of a company involved in the contract, or merges that company into a subsidiary. If the contract has no Change of Control Provision, set it to "N/A".
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 23) Should control of B&H pass into the hands... [rest of Change of Control Provision]"

    21. Key Person Provision Details
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes information about key person provision. This covers situations where a key person representing a contract party no longer works for or is involved with that party anymore. If the contract has no Key Person Provision, set it to "N/A".
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 23) In the case that the representative of B&H is no longer involved with... [rest of Key Person Provision]"

    22. Territory
    - **Instruction**: The main territories of the contract. Return the value as a comma-separated list. Always use one or some of the pre-defined values below. If the territories do not include the pre-defined values, leave the value "N/A".
    - **Format**: "A comma-separated list where each element is one of: "USA", "Canada", "Mexico", "Universe"."
    - **Example**: "Universe" or "USA, Canada, Japan"

    23. Other Territory
    - **Instruction**: If the territories of the contract include some territories not part of the pre-defined values in Territory (field 22), list those territories here. Return the value as a comma-separated list. If there is no territory to be defined in this field, leave the value "N/A".
    - **Format**: "A comma-separated list where each element is NOT one of: "USA", "Canada", "Mexico", "Universe"."
    - **Example**: "Japan" or "Japan, Korea"

    24. Excluded Territories
    - **Instruction**: Any territories explicitly excluded from the contract. Return the value as a comma-separated list. If there is no excluded territory, leave the value "N/A".
    - **Format**: "A comma-separated list of excluded territories"
    - **Example**: "Japan" or "Japan, Korea"

    25. Term Definition
    - **Instruction**: Definition of the term as written in the contract. Include both the initial term and any option periods, renewals, or extensions afterwards.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 1) For the period commencing on the date first written above, up to and including December 31, 1998 (hereinafter referred to as the "Term")"

    26. Number of Contract Periods
    - **Instruction**: The number of contract periods or extensions after the initial term. Always use one of the pre-defined values below, or leave the value as "Other".
    - **Format**: "Choose one of: 'Initial Period', 'Initial Period + 1 Option', 'Initial Period + 2 Options', 'Initial Period + 3 Options'; or leave as 'Other'."
    - **Example**: "Initial Period + 2 Options"

    27. Other number of Contract Periods
    - **Instruction**: If Number of Contract Periods (field 26) is "Other", use this field to express the number of contract periods or extensions.
    - **Format**: "Initial Period + [Number] Options" or "Initial Period + [Text]"
    - **Example**: "Initial Period + 4 Options" or "Initial Period + Automatic Extensions"

    28. Are there Options?
    - **Instruction**: Whether the agreement includes option periods. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    29. Length of Each Contract Period
    - **Instruction**: The length or duration of each contract period or extension after the initial term.
    - **Format**: "[Duration]"
    - **Example**: "1 year"

    30. Minimum Delivery Commitment Amount
    - **Instruction**: The number of songs the writer needs to deliver to the publisher during the contract term to satisfy the delivery commitment. Set to 0 if not present.
    - **Format**: [Number]
    - **Example**: 10

    31. Min Delivery Release Commitment Amount
    - **Instruction**: The number of songs that need to get recorded and released to satisfy the delivery release commitment. Set to 0 if not present.
    - **Format**: [Number]
    - **Example**: 4

    32. Catalog (Full / Partial)
    - **Instruction**: Whether the agreement covers all songs in the writer's catalog. Output only either of "Full" or "Partial".
    - **Format**: "[Full / Partial]"
    - **Example**: "Partial"

    33. All Songs Written During Term
    - **Instruction**: Whether the agreement covers all songs written during the contract term. Output only either of "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    34. All Songs Acquired during Term
    - **Instruction**: Whether the agreement covers all songs acquired by the writer or their entity during the contract term. Output only either of "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    35. All Songs Prior to Term
    - **Instruction**: Whether the agreement covers all existing songs written or acquired by the writer before the contract term. Output only either of "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    36. Only Songs on Artist's Album
    - **Instruction**: Whether the agreement covers only songs on one or some specific albums created by the writer or artist. Output only either of "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    37. [Prior] Pass-Through Income Included in Concord
    - **Instruction**: Whether the contract mentions any prior pass-through income that is included in Concord or the Concord entity. Output only either of "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    38. Rights Granted: Assignment Copyrights
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about the publisher owning the copyright to the songs originally owned, written or acquired by the writer.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Section 4) You hereby irrevocably sell, transfer and assign to... [rest of Copyright Assignment Provision]"

    39. Rights Granted: General
    - **Instruction**: Whether the rights granted only include publishing or both publishing and master. 
    - **Format**: "[Publishing / Publishing + Master]"
    - **Example**: "Publishing + Master"

    40. Rights Granted: Master Representation
    - **Instruction**: Whether master representation rights are granted, and if so, whether master representation rights are exclusive or not. Output only one of the following options: "Exclusive", "Non-Exclusive", "No Master Rep".
    - **Format**: "[Exclusive / Non-Exclusive / No Master Rep]"
    - **Example**: "No Master Rep"

    41. Rights Granted: Sync Camp
    - **Instruction**: Whether granted synchronization rights are exclusive or not. If there is no information about this, leave the value as "Yes". Output only one of the following options: "Exclusive", "Non-Exclusive", "Yes".
    - **Format**: "[Exclusive / Non-Exclusive / Yes]"
    - **Example**: "Exclusive"

    42. Rights Granted: Demos
    - **Instruction**: Whether the contract grants rights to the publisher for demos created by the writer. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    43. Rights Excluded
    - **Instruction**: List of all rights mentioned in the contract that are excluded and not granted to the publisher. Return the value as a list separated by the newline character. If there is no excluded right, leave the value "N/A".
    - **Format**: "A newline-separated list of excluded rights"
    - **Example**: "[Excluded Right 1]\\n[Excluded Right 2]"

    44. Right of First Negotiation / Match Right
    - **Instruction**: Whether the publisher has the right of first negotiation, first match or first refusal. These rights require the writer to first come to the publisher to discuss a renewal or a competing offer so the publisher gets the chance to negotiate the renewal or match that offer. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    45. Choice of Law
    - **Instruction**: The state or country whose laws govern the interpretation and enforcement of the contract and apply for any dispute. Always choose one of the pre-defined options below, or leave the value as "Other".
    - **Format**: "Choose one of: 'California', 'Florida', 'New York', 'Tennessee', 'United States', 'Australia', 'Canada', 'Germany', 'Denmark', 'England & Wales', 'France', 'United Kingdom of Great Britain and Northern Ireland', 'Ireland', 'Japan', 'Korea', 'Mexico', 'New Zealand', 'Puerto Rico'; or leave as 'Other'."
    - **Example**: "New York"

    46. Choice of Law - Other
    - **Instruction**: If Choice of Law (field 45) is "Other", use this field to provide the state or country whose law governs the contract.
    - **Format**: "[State or Country]"
    - **Example**: "Texas"

    47. Licensing Approval Notes
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about whether the publisher needs approval or consent from the writer for all licensing matters.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 4) Publisher shall not, without your prior written consent, ... [rest of Licensing Approval Provision]"

    48. Licensing: Any ad for personal hygiene, firearms or tobacco products
    - **Instruction**: Whether the publisher needs approval or consent from the writer for licensing of songs for advertisements for personal hygiene, firearms or tobacco products. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    49. Licensing: Any political or religious use
    - **Instruction**: Whether the publisher needs approval or consent from the writer for licensing of songs for political or religious use. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    50. Licensing: Samples and interpolations
    - **Instruction**: Whether the publisher needs approval or consent from the writer for licensing of songs used for samples or interpolations. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "Consent Required"

    51. Licensing: Fundamental adaptations / translations / etc. to music, lyrics, title, or harmonic structure
    - **Instruction**: Whether the publisher needs approval or consent from the writer for adapting or translating the music, lyrics, title, or harmonic structure of songs and licensing of these versions. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "Consent Required"

    52. Licensing: Issue blanket licenses including the Comps
    - **Instruction**: Whether the publisher needs approval or consent from the writer for issuing a blanket license for the publisher's entire catalog, which includes the writer's songs. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    53. Licensing: Licence the Compositions for period with extends beyond the Rights Period
    - **Instruction**: Whether the publisher needs approval or consent from the writer for licensing of songs beyond the period that the publisher has licensing rights. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    54. Name & Likeness Approval Notes
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about whether or not the publisher needs approval or consent from the writer for all matters relating to name, image or likeness of the songwriter or artist. If the contract does not mention whether the publisher needs approvals for name and likeness, extract exact wording from the contract for any relevant section about the songwriter or artist's name and likeness matters instead.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 17) We shall have the right to use your name... [rest of Name & Likeness Approval Provision]"

    55. Name & Likeness Approvals
    - **Instruction**: Whether the publisher needs approval or consent from the writer for using or licensing the writer's name, image or likeness. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "Consent Required"

    56. Sync Master Rep Approval Notes
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about whether the publisher needs approval or consent from the writer for all matters relating to synchronization licensing for the master side (or sound recordings) of songs. Do NOT include info about synchronization licensing matters for the composition side of songs.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Section 4) Publisher will have the right to license the master recording rights for third party synchronization... [rest of Sync Master Rep Approval Provision]"

    57. Synchronization: Films, Television Programmes, Advertisements, Computer Games, Interactive Devices, Videos
    - **Instruction**: Whether the publisher needs approval or consent from the writer for synchronization licensing of the master (or sound recordings, NOT compositions) of songs in films, TV, advertisements, games, videos, interactive devices, etc. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    58. Miscellaneous Licensing Notes
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about whether the publisher needs approval or consent from the writer for all matters relating to Print, Mechanical Licensing, Performance or Dramatization.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 8) Grant a "first use" mechanical license... [rest of Miscellaneous Licensing Approval Provision]"

    59. Print: Print, publish and vend, and license the same
    - **Instruction**: Whether the publisher needs approval or consent from the writer for print relating to the songs. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    60. Mechanical: Issue "first use" mechanical licenses
    - **Instruction**: Whether the publisher needs approval or consent from the writer for issuing 'first use' mechanical licenses to create initial recordings of songs. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "Consent Required"

    61. Mechanical: Issue mechanical reproduction licenses at less than full statutory rate for the US
    - **Instruction**: Whether the publisher needs approval or consent from the writer for issuing mechanical reproduction licenses at less than full statutory rate for the US. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "No Restriction"

    62. Performance: Grand rights licenses and right to dramatize
    - **Instruction**: Whether the publisher needs approval or consent from the writer for dramatizing the songs or granting licenses to dramatize the songs. If nothing is mentioned about this in the contract, return "No Restriction".
    - **Format**: "[Consent Required / No Restriction]"
    - **Example**: "Consent Required"

    63. Terms of Approval for Licensing
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about approval terms for all items that require consent from the writer. This includes the procedure for obtaining the approval or consent from the writer, timeline for responses, what happens if no response is received, etc. Also include any deemed approval mechanisms or exceptions.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 19) As for all matters to be subject to your approval, such approval shall be deemed received if... [rest of Terms of Approval]"

    64. Royalty Basis
    - **Instruction**: The royalty basis, or calculation method, used for calculating royalties. Always use one of the following options: "Net Receipts", "Limited Net Receipts", "At Source", "NPS". "Net Receipts" means royalties are calculated based on the publisher's actual income received after cost or fee deductions. "Limited Net Receipts" is the same as "Net Receipts" but with only limited types or limited caps of deductions allowed. "At Source" means royalties are calculated based on the gross income received at the first point of collection, before any deductions. "NPS" (Net Publisher Share) means the artist also earns a portion of the publisher's retained income after the artist is already paid, usually in a co-publishing deal.
    - **Format**: "[Net Receipts / Limited Net Receipts / At Source / NPS]"
    - **Example**: "Net Receipts"

    65. Definition of Royalty Basis
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that defines or describes the royalty basis used for the contract. This defines the source and calculation method used to calculate royalties or income for the songwriter or artist. Do NOT confuse this with accounting statement, which is something different and not related to this field.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 7) All royalties payable to you are to be calculated on... [rest of Royalty Basis Definition]"

    66. Definition of Gross Income
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that defines or describes the meaning of gross income used for calculating royalties.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 19) "Gross Income" shall mean... [rest of Gross Income Definition]"

    67. At Source
    - **Instruction**: Whether royalties (or any income amounts) are calculated based on gross income received at source, or the first point of collection, before any deductions. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    68. Frequency of Accounting / Statements
    - **Instruction**: The frequency in which accounting happens, or how often royalty statements and payments must be issued. Either "Quarterly" or "Semi-Annually".
    - **Format**: "[Quarterly / Semi-Annually]"
    - **Example**: "Semi-Annually"

    69. Payments/Statements Due within
    - **Instruction**: The permitted delay (or accounting lag) between the end of a statement period (or payment period) and when payment must be issued to the writer.
    - **Format**: "[Number] days"
    - **Example**: "90 days"

    70. Agreement Royalties
    - **Instruction**: List of all royalties by type. Return the value as a list separated by the newline character. Each item should clearly identify the type of royalty and its rate (if present). Use percent symbol "%" to denote percentages. Use concise language when describing the type and rates, unless detailed language is required to describe the type of royalty (such as for territories). Include information, if applicable, about rates that are tied to specific conditions or thresholds.
    - **Format**: "A newline-separated list of royalties"
    - **Example**: "Sheet Music: 12.5% of marked retail selling price\\nMechanical Fees: 50%\\n..."

    71. General Master Rep Royalty
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about royalties for general master representation (of master recording).
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Section 7) In connection with such master exploitation, Company shall pay to you... [rest of General Master Rep Royalty Provision]"

    72. Camp Master Rep Royalty
    - **Instruction**: Exact wording from the contract (with clause/section/page number) that includes info about royalties for master representation for a camp.
    - **Format**: "([Text Location, if applicable]) [Exact Verbatim Contract Language]"
    - **Example**: "(Paragraph 5.2) In connection with Sync Camp Masters exploitation, Publisher shall credit Writer... [rest of Camp Master Rep Royalty Provision]"

    73. Royalty Escalation
    - **Instruction**: Whether royalty escalation provisions exist. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    74. Retroactive Collection
    - **Instruction**: Whether retroactive royalty collection is permitted. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    75. Schedule A Received
    - **Instruction**: Whether there exists a Schedule A with the contract that lists the songs the contract term applies to, or whether there exists a Schedule A delivered separately but mentioned in the contract. Output only either "Yes" or "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    76. Description
    - **Instruction**: Use the value of Year (field 14) to make the value.
    - **Format**: "[This is the contractual address as of [Year] of agreement]"
    - **Example**: "This is the contractual address as of 1992 of agreement"

    77. Assignability of Contract
    - **Instruction**: If `"Assignability of Contract Details"` (field 19) is not null or "N/A", then the value is "Yes", else the value is "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    78. Change of Control
    - **Instruction**: If `"Change of Control Details"` (field 20) is not null or "N/A", then the value is "Yes", else the value is "No".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    79. Key Person Provision
    - **Instruction**: If `"Key Person Provision Details"` (field 21) is not null or "N/A", then the value is "Yes", else the value is "No".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    80. Minimum Delivery Commitment?
    - **Instruction**:  If "Minimum Delivery Commitment Amount" (field 30) is 0, then the value is "No", else the value is "Yes".
    - **Format**: "[Yes / No]"
    - **Example**: "Yes"

    81. Minimum Delivery Release Commitment?
    - **Instruction**: If "Min Delivery Release Commitment Amount" (field 31) is 0, then the value is "No", else the value is "Yes".
    - **Format**: "[Yes / No]"
    - **Example**: "No"

    82. Writer(s) CAE/IPI Name
    - **Instruction**: Always leave the value "N/A".
    - **Format**: "N/A"
    - **Example**: "N/A"

    83. Writer(s) CAE/IPI Number
    - **Instruction**: The IPI or CAE number of the writer party.
    - **Format**: "9-to-11-digit IPI number"
    - **Example**: "12345678901"

    84. Publishing Designee(s) IPI Name
    - **Instruction**: Always leave the value "N/A".
    - **Format**: "N/A"
    - **Example**: "N/A"

    85. Publishing Designee(s) IPI Number
    - **Instruction**: Always leave the value "N/A".
    - **Format**: "N/A"
    - **Example**: "N/A"

    86. Other Performing Rights Organization
    - **Instruction**: **Instruction**: Always leave the value "N/A".
    - **Format**: "N/A"
    - **Example**: "N/A"
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
