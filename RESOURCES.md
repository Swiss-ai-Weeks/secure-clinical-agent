# NVIDIA RAG Learning Resources

## Knowledge

- [NVIDIA RAG Blueprint, pinned v2.6.2](https://github.com/NVIDIA-AI-Blueprints/rag/tree/v2.6.2#workflow)
  Primary architecture overview and workflow. Read the Workflow section after lesson 1.
- [NVIDIA model and endpoint configuration](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/docs/change-model.md)
  Explains changing model servers. Use when distinguishing local inference from hosted inference.
- [Docker: What is a container?](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)
  Primary introduction to isolated application processes. Use for the next lesson about how multiple services share a server.
- [NVIDIA NIM documentation](https://docs.nvidia.com/nim/index.html)
  Primary documentation for packaged model services. Use when explaining the local GPU model containers.
- [Our actual configuration](backend/deploy/hybrid.env)
  Source of truth for our selected endpoints, features, and GPU assignments; more specific than upstream defaults.
- [Our Compose overlay](backend/deploy/compose.hybrid.yaml)
  Source of truth for enabled containers, local port bindings, and storage volumes.

## Wisdom (Communities)

No community activity is needed for the first lesson. User preferences about communities have not been established.

## Gaps

- User understanding has not yet been assessed; do not infer mastery from lesson delivery.
- Real model startup and end-to-end ingestion remain unverified pending credentials.
