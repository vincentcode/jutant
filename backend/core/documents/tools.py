"""The platform's documents tools, which every pack can use (`mcp_servers/documents`).

Templates that work with documents in code call them by these names, through the gateway like
any other call, so the caller's access to each document is still checked.
"""

SEARCH_TOOL = "documents.search"  # {query} -> [{document_id, title, section, text}, ...]
GET_TOOL = "documents.get"  # {document_id, part} -> {document_id, title, text, part, parts}
