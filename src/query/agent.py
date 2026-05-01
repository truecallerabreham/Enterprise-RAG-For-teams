import os
import json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from google import genai

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
        print(f"-> Node: Retrieve (Hybrid + RRF | RBAC Filters: {groups})")
        
        # Mocking the Qdrant Hybrid Search Results
        mock_context = [
            {"repo": "frontend-app", "file": "src/auth.py", "content": "def login(): return True"},
            {"repo": "frontend-app", "file": "src/utils.py", "content": "def parse_token(): pass"}
        ]
        return {"retrieved_context": mock_context, "loop_count": state.get("loop_count", 0)}

    def node_synthesize(self, state: AgentState):
        """Calls the LLM to synthesize an answer with strict JSON citations."""
        loop = state.get('loop_count', 0)
        print(f"-> Node: Synthesize (Loop {loop})")
        
        # Mocking LLM structured output.
        # If it's loop 0, let's pretend the LLM hallucinated a file.
        # If it's loop 1, let's pretend it corrected itself.
        if loop == 0:
            mock_citations = [{"repo": "frontend-app", "file": "src/auth.py"}, {"repo": "frontend-app", "file": "src/hallucinated.py"}]
        else:
            mock_citations = [{"repo": "frontend-app", "file": "src/auth.py"}]
            
        return {
            "final_answer": "The login function handles authentication.", 
            "citations": mock_citations,
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
