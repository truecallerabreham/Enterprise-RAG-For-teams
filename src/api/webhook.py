import os
from fastapi import FastAPI, Request, BackgroundTasks
import uvicorn
from dotenv import load_dotenv

# Import our modular components
from src.ingestion.parser import CodeParser
from src.ingestion.processor import ChunkProcessor
from src.storage.qdrant_client import VectorStoreManager
from src.storage.graph_client import GraphStoreManager

# Load API Keys
load_dotenv()

app = FastAPI(title="Enterprise RAG Webhook", version="1.0.0")

# Initialize global managers
parser = CodeParser()
processor = ChunkProcessor()
v_db = VectorStoreManager()
g_db = GraphStoreManager()

def process_github_push(payload: dict):
    """
    Background task to orchestrate the ingestion pipeline.
    """
    repo_name = payload.get("repository", {}).get("full_name", "unknown/repo")
    print(f"--- [Webhook] Processing push for {repo_name} ---")
    
    # In a real GitHub webhook, 'commits' contains the list of changed files
    # For this implementation, we simulate processing a set of files
    files_to_process = [
        {"path": "src/auth.py", "language": "python", "content": "def login():\n    return True"},
        {"path": "src/utils.py", "language": "python", "content": "def format_date():\n    pass"}
    ]
    
    # 1. Parse -> 2. Process -> 3. Store
    for file in files_to_process:
        print(f" -> Slicing {file['path']} into AST chunks...")
        chunks = parser.get_chunks(file["content"], file["language"])
        
        print(f" -> Generating Summaries & Voyage Embeddings for {len(chunks)} chunks...")
        processed_chunks = processor.process_chunks(chunks)
        
        print(f" -> Upserting to Qdrant (RBAC: engineering_team)...")
        v_db.upsert_chunks(processed_chunks, repo_name=repo_name, allowed_groups=["engineering_team"])
        
        print(f" -> Updating Symbol Graph...")
        g_db.upsert_symbols(processed_chunks, repo_name=repo_name, file_path=file["path"])

    print(f"--- [Webhook] Ingestion successful for {repo_name} ---")

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives push events from GitHub and triggers asynchronous ingestion."""
    # Note: In production, validate the X-Hub-Signature-256 header here
    payload = await request.json()
    
    # Send to background to avoid timing out the GitHub webhook request
    background_tasks.add_task(process_github_push, payload)
    
    return {"status": "Accepted", "message": "Ingestion pipeline triggered."}

if __name__ == "__main__":
    uvicorn.run("src.api.webhook:app", host="0.0.0.0", port=8000, reload=True)
