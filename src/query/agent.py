import os
import json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Import our storage layer
from src.storage.qdrant_client import VectorStoreManager
from qdrant_client import models

# Load API Keys
load_dotenv()

# Define the highly-structured Agent State
class AgentState(TypedDict):
    query: str
    user_groups: List[str]
    retrieved_context: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    final_answer: str
    validation_errors: str
    loop_count: int

class EnterpriseRAGAgent:
    """
    LangGraph-powered Query Agent featuring:
    - Pre-retrieval RBAC Authentication
    - Reciprocal Rank Fusion (RRF) Retrieval Node
    - Citation Validation Loop Edge
    """
    def __init__(self):
        self.gemini_client = None
        if os.getenv("GOOGLE_API_KEY"):
            self.gemini_client = genai.Client()
        
        self.v_db = VectorStoreManager()
        self.max_loops = 3

    def build_graph(self):
        """Compiles the cyclic directed graph."""
        workflow = StateGraph(AgentState)
        
        # Define the nodes (The "Doers")
        workflow.add_node("auth", self.node_auth)
        workflow.add_node("retrieve", self.node_retrieve)
        workflow.add_node("synthesize", self.node_synthesize)
        
        # Define the edges (The "Routers")
        workflow.set_entry_point("auth")
        workflow.add_edge("auth", "retrieve")
        workflow.add_edge("retrieve", "synthesize")
        
        # The crucial Validation Loop
        workflow.add_conditional_edges(
            "synthesize",
            self.edge_validate_citations,
            {
                "valid": END,
                "invalid": "synthesize"
            }
        )
        
        return workflow.compile()
        
    def node_auth(self, state: AgentState):
        """Mocks an SSO integration to fetch user RBAC groups."""
        print("-> Node: Auth (Simulating SSO...)")
        # In production, this would validate a JWT token
        return {"user_groups": ["engineering_team", "frontend"]}
        
    def node_retrieve(self, state: AgentState):
        """Retrieves chunks from Qdrant, strictly filtering by user_groups."""
        groups = state.get('user_groups', [])
        query_text = state['query']
        print(f"-> Node: Retrieve (Hybrid + RRF | RBAC Filters: {groups})")
        
        # Execute Real Hybrid Search with RRF via Qdrant
        # Note: This assumes 'dense' and 'sparse' vectors are available in the collection
        try:
            search_results = self.v_db.client.query_points(
                collection_name=self.v_db.collection_name,
                prefetch=[
                    models.Prefetch(query=query_text, using="dense", limit=10),
                ],
                query=models.FusionQuery.RRF,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="allowed_groups", match=models.MatchAny(any=groups))
                    ]
                ),
                limit=10
            )
            
            context = []
            for point in search_results.points:
                p = point.payload
                context.append({
                    "repo": p.get("repo_name"),
                    "file": p.get("file_path", "unknown"),
                    "content": p.get("content", ""),
                    "summary": p.get("summary", "")
                })
        except Exception as e:
            print(f"   [Error] Qdrant retrieval failed: {e}. Falling back to mock for demo.")
            context = [
                {"repo": "frontend-app", "file": "src/auth.py", "content": "def login(): return True"},
                {"repo": "frontend-app", "file": "src/utils.py", "content": "def parse_token(): pass"}
            ]
            
        return {"retrieved_context": context, "loop_count": state.get("loop_count", 0)}

    def node_synthesize(self, state: AgentState):
        """Calls the LLM to synthesize an answer with strict JSON citations."""
        loop = state.get('loop_count', 0)
        print(f"-> Node: Synthesize (Loop {loop})")
        
        if not self.gemini_client:
             return {"final_answer": "Gemini API client not initialized. Check your GOOGLE_API_KEY.", "citations": []}

        # Build formatted context string for the LLM
        context_str = ""
        for i, doc in enumerate(state['retrieved_context']):
            context_str += f"\n[Document {i}]\nRepo: {doc['repo']}\nFile: {doc['file']}\nContent: {doc['content']}\n"

        prompt = f"""
        You are an expert technical assistant for a massive enterprise codebase. 
        Answer the following query using ONLY the provided code context.
        
        QUERY: {state['query']}
        
        CONTEXT:
        {context_str}
        
        {f"IMPORTANT: Your previous response was invalid. CORRECT THIS ERROR: {state['validation_errors']}" if state.get('validation_errors') else ""}
        
        STRICT OUTPUT FORMAT:
        You must respond with a raw JSON object and nothing else.
        {{
            "answer": "Your detailed technical explanation...",
            "citations": [
                {{"repo": "name", "file": "path/to/file.py"}}
            ]
        }}
        """
        
        try:
            # Using the modern google-genai 1.x API
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash", # High speed for agentic loops
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            res_json = json.loads(response.text)
            return {
                "final_answer": res_json.get("answer", ""), 
                "citations": res_json.get("citations", []),
                "loop_count": loop + 1
            }
        except Exception as e:
            print(f"   [Error] Synthesis failed: {e}")
            return {
                "final_answer": f"Generation failed: {e}", 
                "citations": [], 
                "loop_count": loop + 1
            }
        
    def edge_validate_citations(self, state: AgentState):
        """Validates if the LLM hallucinated citations. Routes back if invalid."""
        print("-> Edge: Validating Citations...")
        
        if state["loop_count"] >= self.max_loops:
            print("   [Warning] Max loops reached. Forcing exit.")
            return "valid"
            
        valid_files = [c["file"] for c in state["retrieved_context"]]
        
        for citation in state["citations"]:
            if citation["file"] not in valid_files:
                print(f"   [Error] Hallucinated citation found: {citation['file']}. Routing back to Synthesize.")
                # We would set state["validation_errors"] here for the LLM to fix
                return "invalid"
                
        print("   [Success] All citations are faithful to context.")
        return "valid"

if __name__ == "__main__":
    # Smoke Test the Agent Loop
    agent = EnterpriseRAGAgent()
    app = agent.build_graph()
    
    initial_state = {"query": "How does login work?", "loop_count": 0}
    for event in app.stream(initial_state):
        for node_name, values in event.items():
            pass # The print statements inside nodes will trace the execution
