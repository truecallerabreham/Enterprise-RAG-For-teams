import os
from typing import List, Dict, Any
from google import genai
from google.genai import types
import voyageai

class ChunkProcessor:
    """
    Handles the 'Three-Pronged' representation of code chunks:
    1. Summarization (LLM)
    2. Dense Embeddings (Voyage AI)
    3. Sparse Vectors (BM25 / FastEmbed via Qdrant later)
    """

    def __init__(self):
        # Initialize Google GenAI for Summarization
        self.gemini_client = None
        if os.getenv("GOOGLE_API_KEY"):
            self.gemini_client = genai.Client()
            self.summary_model = "gemini-2.5-flash" # Fast & cheap for summarization

        # Initialize Voyage AI for Embeddings
        self.voyage_client = None
        if os.getenv("VOYAGE_API_KEY"):
            self.voyage_client = voyageai.Client()
            self.embed_model = "voyage-code-3"

    def process_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhances raw code chunks with summaries and embeddings.
        """
        processed_chunks = []
        for chunk in chunks:
            # 1. Generate Summary (Contextual Enrichment)
            summary = self._generate_summary(chunk["content"], chunk.get("type", "code"))
            chunk["summary"] = summary
            
            # The payload to embed is the code PLUS its summary for better retrieval
            embed_payload = f"Summary: {summary}\n\nCode:\n{chunk['content']}"

            # 2. Generate Dense Embeddings
            chunk["dense_embedding"] = self._generate_dense_embedding(embed_payload)
            
            # Note: Sparse vectors (BM25) are typically handled natively by Qdrant 1.17+ 
            # if configured with FastEmbed, or generated at ingestion time. 
            # We'll rely on Qdrant's internal sparse indexing for this implementation.

            processed_chunks.append(chunk)
            
        return processed_chunks

    def _generate_summary(self, code: str, node_type: str) -> str:
        """Calls Gemini to summarize what the code does."""
        if not self.gemini_client:
            return "Summarization unavailable (No API Key)"
            
        prompt = f"Explain what this {node_type} does in 2-3 sentences. Focus on logic and inputs/outputs.\n\nCode:\n{code}"
        try:
            response = self.gemini_client.models.generate_content(
                model=self.summary_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1, # Low temp for factual summaries
                )
            )
            return response.text
        except Exception as e:
            print(f"Summarization error: {e}")
            return "Error generating summary."

    def _generate_dense_embedding(self, text: str) -> List[float]:
        """Calls Voyage AI code model to get dense vectors."""
        if not self.voyage_client:
            # Return dummy vector for local testing if no API key
            return [0.0] * 1024 
            
        try:
            result = self.voyage_client.embed([text], model=self.embed_model, input_type="document")
            return result.embeddings[0]
        except Exception as e:
            print(f"Embedding error: {e}")
            return [0.0] * 1024

if __name__ == "__main__":
    # Smoke Test
    processor = ChunkProcessor()
    dummy_chunks = [{
        "type": "function_definition",
        "content": "def add(a, b): return a + b",
        "start_line": 1,
        "end_line": 1,
        "hash": "abc123hash"
    }]
    res = processor.process_chunks(dummy_chunks)
    print(f"Processed chunks: {len(res)}")
    print(f"Summary generated: {res[0].get('summary')}")
    print(f"Dense vector length: {len(res[0].get('dense_embedding', []))}")
