# Kubernetes

Not used yet. The first deployments run Docker Compose on a single server (`../docker-compose.yml`).

When a client needs Kubernetes, the manifests or Helm chart go here. They should run the same images (`backend/Dockerfile`, `web/Dockerfile`) and the same services as the Compose file: db, ollama, migrate (as a Job), api, mcp-documents, mcp-transactions, mcp-services, worker and web.
