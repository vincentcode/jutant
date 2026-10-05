Summarise a circular or pull key fields from an uploaded document.

To summarise a stored document: call `documents.search` to find it, then always call `documents.get` with its `document_id` to read the whole document before summarising.
For a summary: state the purpose, the key changes and the effective date in up to five bullet points.
For extraction: return only the fields of the matching schema. Use null for a field that is not in the document. Never guess.
