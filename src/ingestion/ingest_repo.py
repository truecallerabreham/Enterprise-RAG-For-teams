import os
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

from src.ingestion.parser import CodeParser
from src.ingestion.processor import ChunkProcessor
from src.storage.qdrant_client import VectorStoreManager
from src.storage.graph_client import GraphStoreManager

load_dotenv()

def ingest_github_repo(repo_url: str):
    repo_name = repo_url.split("/")[-1]
    temp_dir = Path(f"./temp_{repo_name}")
    
    # 1. Clone the repo
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    
    print(f"--- Cloning {repo_url} ---")
    subprocess.run(["git", "clone", "--depth", "1", repo_url, str(temp_dir)], check=True)
    
    # 2. Initialize Managers
    parser = CodeParser()
    processor = ChunkProcessor()
    v_db = VectorStoreManager()
    g_db = GraphStoreManager()
    
    # 3. Walk through the repo
    supported_extensions = {".py": "python", ".js": "javascript", ".ts": "javascript"}
    
    print(f"--- Processing Files in {repo_name} ---")
    all_files = []
    for ext in supported_extensions.keys():
        all_files.extend(list(temp_dir.rglob(f"*{ext}")))
        
    for file_path in all_files:
        rel_path = file_path.relative_to(temp_dir)
        lang = supported_extensions.get(file_path.suffix)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            print(f" -> Indexing: {rel_path} ({lang})")
            
            # AST Slicing
            chunks = parser.get_chunks(content, lang)
            if not chunks:
                continue
                
            # Summaries & Embeddings
            print(f"    -> Processing {len(chunks)} chunks (Respecting Rate Limits...)")
            processed_chunks = processor.process_chunks(chunks)
            
            # Storage (Assigning to engineering group by default)
            v_db.upsert_chunks(processed_chunks, repo_name=repo_name, allowed_groups=["engineering"])
            g_db.upsert_symbols(processed_chunks, repo_name=repo_name, file_path=str(rel_path))
            
            # Rate Limit Guard for Free Tier Keys (Voyage: 3 RPM, Gemini: 5 RPM)
            import time
            time.sleep(20) 
            
        except Exception as e:
            print(f"    [Error] Failed to process {rel_path}: {e}")

    print(f"\n✅ SUCCESS: {repo_name} is now fully indexed in your RAG system!")
    # shutil.rmtree(temp_dir) # Clean up

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/Abem-S/tablo-ai"
    ingest_github_repo(target)
