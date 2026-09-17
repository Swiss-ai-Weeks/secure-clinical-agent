# Teaching notes

- Mission is taken from the user's explicit request to understand and deploy this repository, and their choice of local retrieval/storage with a hosted language model. No repeated mission interview needed.
- The repository is the teaching workspace, rather than the broader `/home/nvidia` home directory.
- Stated prior experience: new to NVIDIA infrastructure. Docker, Python, and Kubernetes knowledge have not been assessed.
- Lesson 0001: distinguish document preparation, local retrieval, and hosted generation using `backend/examples/demo.txt`.
- Learning evidence: none yet. Do not create a learning record merely because the lesson was delivered.
- Next conversational check: can the user explain why a hosted LLM still receives document excerpts when storage is local?
- Candidate next lesson: one server, several containers; map a single service to its Compose definition.
- Live status inspected 2026-09-15: Elasticsearch, SeaweedFS, and Redis healthy. No application/model containers shown. Teaching does not require deploying more services.
