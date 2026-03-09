"""URL constants for rag domain."""

RAG_BASE = "/api/rag"
RAG_DOCUMENT_UPLOAD = f"{RAG_BASE}/documents/upload"
RAG_DOCUMENTS = f"{RAG_BASE}/documents"
RAG_DOCUMENT_DETAIL = f"{RAG_BASE}/documents/{{document_id:uuid}}"
RAG_QUERY = f"{RAG_BASE}/query"
