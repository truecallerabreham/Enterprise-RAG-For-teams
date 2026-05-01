# AI Implementation Plan: Enterprise RAG

## 🛑 RULES OF ENGAGEMENT FOR AI AGENTS
**Read this before writing any code.**
You are acting as a Junior/Mid-level Software Engineer (Intern). The Human User is the **Lead Engineer**.
1. **Never build the entire system in one go.** You will follow this plan phase-by-phase.
2. **Mandatory Checkpoints:** At the end of every phase, you will reach a `[🛑 CHECKPOINT]`. You must stop, present the code you have written, and ask the Lead Engineer for a code review.
3. **Do not proceed** to the next phase until the Lead Engineer explicitly approves the current phase.
4. **Focus on modularity:** Write code that is testable in isolation. 

---

## Phase 1: Environment & Foundation
**Goal:** Establish the project skeleton and dependency management.
1. Initialize the Python environment (using `uv` or `poetry`).
2. Define the core directory structure (`src/ingestion`, `src/storage`, `src/query`, `tests/`).
3. Set up the `pyproject.toml` with strict dependencies (e.g., `llama-index`, `langgraph`, `qdrant-client`, `tree-sitter`, `anthropic`).
4. Create an `.env` template for API keys.
* **[🛑 CHECKPOINT 1]** Present the directory structure and dependency list to the Lead Engineer for approval. Do not write feature code yet.

---

## Phase 2: The AST Parser & Hashing Engine
**Goal:** Build the tool that accurately reads and slices code.
1. Create `src/ingestion/parser.py`.
2. Implement Tree-sitter to parse a sample Python and JavaScript file.
3. Write the logic to extract logical boundaries (Functions, Classes).
4. Implement the AST Hashing algorithm (ignoring whitespace/comments) to generate a unique fingerprint for each chunk.
* **[🛑 CHECKPOINT 2]** Run the parser on a dummy file. Show the Lead Engineer the extracted chunks and their corresponding AST hashes. Wait for approval.

---

## Phase 3: The Three-Pronged Processing Pipeline
**Goal:** Generate Embeddings, Sparse Vectors, and Summaries for the extracted chunks.
1. Create `src/ingestion/processor.py`.
2. Implement the API call to Claude Haiku 4.5 for chunk summarization. Include prompt caching logic.
3. Implement the Voyage-code-3 client for dense embeddings.
4. Mock the Tantivy BM25 indexing (or set up a local testing pipeline).
* **[🛑 CHECKPOINT 3]** Present the processing script. Highlight how rate limits and API costs are being managed for the LLM calls. Wait for approval.

---

## Phase 4: Storage & Graph Schemas
**Goal:** Push the processed data into Qdrant and Neo4j/Kuzu.
1. Create `src/storage/qdrant_client.py`. Define the collection schema, explicitly including the `allowed_groups` metadata field for RBAC.
2. Create `src/storage/graph_client.py`. Define the schema for Nodes (Files, Symbols) and Edges (Imports, Calls).
3. Write an integration script that takes the outputs from Phase 3 and safely loads them into both databases.
* **[🛑 CHECKPOINT 4]** Show the Lead Engineer the Vector DB schema and Graph DB schema. Explain how cross-repo symbols are uniquely identified. Wait for approval.

---

## Phase 5: The LangGraph Query Node (Retrieval & RRF)
**Goal:** Build the first half of the LangGraph agent—retrieving the data.
1. Create `src/query/agent.py`.
2. Implement the `Auth Node` (mocking an SSO token that returns `["engineering_team"]`).
3. Implement the `Retrieve Node`. It must query Qdrant using the `allowed_groups` filter.
4. Implement the Reciprocal Rank Fusion (RRF) logic to merge the Dense and Sparse results.
* **[🛑 CHECKPOINT 5]** Run a test query. Show the Lead Engineer the raw retrieved chunks and explain how RRF scored them. Wait for approval.

---

## Phase 6: Synthesis & Citation Loop
**Goal:** Build the LLM reasoning and citation enforcement.
1. Implement the `Reranker Node` (using a local Cross-Encoder like `bge-reranker`).
2. Implement the `Synthesis Node` calling Claude Sonnet 4.7. Provide a strict prompt demanding JSON citations (Repo, Path, Lines).
3. Implement the `Validation Edge` in LangGraph. Write the logic that checks if the cited JSON files actually exist in the retrieved context. If they don't, route back to the Synthesis Node with an error prompt.
* **[🛑 CHECKPOINT 6]** Execute an end-to-end test query. Show the Lead Engineer the LangGraph trace (including any hallucinated citations that were caught and fixed). Wait for final approval.

---

## Phase 7: Webhook Integration & Eval
**Goal:** Make the system automatic and measurable.
1. Create a FastAPI endpoint to receive Git webhooks.
2. Connect the webhook to the Ingestion pipeline, ensuring it only processes the `git diff`.
3. Create the `eval/` directory. Write a script to measure MRR@10 and Citation Faithfulness against a golden dataset of 10 questions.
* **[🛑 FINAL CHECKPOINT]** Present the eval results and the webhook architecture. Prepare for production deployment.
