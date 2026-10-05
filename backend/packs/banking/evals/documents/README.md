# Sample documents for evals

**These are invented samples, not the bank's policies.** They give the eval questions something
to search until the bank's real documents are ingested. Replace them, and the questions that
depend on them, with the real documents.

One folder per document type, so each is ingested with its type:

    python manage.py ingest_documents packs/banking/evals/documents/policy --doc-type policy --classification internal
    python manage.py ingest_documents packs/banking/evals/documents/reference --doc-type reference --classification internal
    python manage.py ingest_documents packs/banking/evals/documents/circular --doc-type circular --classification internal
