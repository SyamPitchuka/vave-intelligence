# Known limitations

- The default embedding in `.env.example` is `all-MiniLM-L6-v2` through sentence-transformers, in `offline` mode. `fallback` mode always uses `deterministic-hash-v1`, a hashed lexical vector that needs no model download and is not a neural semantic model.
- On the synthetic labels, MiniLM gives every pair a higher cosine than the hashed vector, but the gap between duplicates and similar-but-distinct ideas is smaller: 0.041 against 0.144 (re-measured on deterministic embeddings, 28 October 2026; see `docs/evaluation-results.md`). A higher cosine is not evidence of a duplicate.
- Similarity scores are retrieval signals. The interface does not present them as calibrated probabilities.
- Thresholds are configuration. The evaluation page can compare them. They have not been calibrated on production VAVE history.
- The labelled set shipped with the app is synthetic and small. Metrics from it are not a production accuracy claim. The evaluation payload sets `small_set` when fewer than 30 labelled cases are present.
- Stage letters A–F in the synthetic guideline are a demonstration convention, not an OEM standard.
- Department labels are kept as supplied, including `steeting`.
- Ollama embedding models that are not 384 dimensions, including the common `nomic-embed-text` at 768, are refused. A new dimension needs a migration and a full re-index.
- `sentence-transformers` is in `requirements.txt` and pulls in PyTorch. If the package is missing, the app reports that. If the model files are missing, `SentenceTransformer` downloads them from Hugging Face unless `HF_HUB_OFFLINE=1` is set. The documented start command sets it, so download the model once beforehand.
- Offline mode does not download Ollama models. If Ollama is down and the language model is not required, analysis continues with the deterministic comparison and a visible warning.
- The corporate connector can test and read a fixed view. It does not commit those rows. An administrator still uses import preview.
- The rate limiter is in memory for a single process.
- Playwright browser tests were not executed in this environment. The API integration test covers login, import validation, search, analysis, review, savings, copilot citations, offline blocking, and the read-only role.
- Docker Compose files are included. The Docker daemon was not installed here, so a compose startup was not run.
- No regulatory, functional-safety, or production-approval claim is made.
