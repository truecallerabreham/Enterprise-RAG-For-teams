from src.models.schemas import AssistantEvent, Citation, QueryRequest, QueryResponse, SearchResult
from src.query.citations import validate_citations
from src.query.retrieval import dense_search, graph_expand, reciprocal_rank_fusion, rerank, sparse_search
from src.storage.memory import AppState


class QueryService:
    def __init__(self, state: AppState) -> None:
        self.state = state

    def answer(self, request: QueryRequest) -> QueryResponse:
        events = [
            AssistantEvent(type="planning", message="Planning retrieval across registered repositories."),
            AssistantEvent(type="searching", message="Running dense and sparse retrieval over indexed chunks."),
        ]
        repo_ids = set(request.repo_ids)
        dense = dense_search(self.state, request.question, repo_ids)
        sparse = sparse_search(self.state, request.question, repo_ids)
        fused = reciprocal_rank_fusion([dense, sparse], limit=max(request.top_k * 4, 20))
        events.append(AssistantEvent(type="expanding_graph", message="Expanding top results through the symbol graph."))
        expanded = graph_expand(self.state, fused, repo_ids, limit=10)
        events.append(AssistantEvent(type="reranking", message="Reranking candidates with local scoring stub."))
        reranked = rerank(request.question, expanded, request.top_k)
        events.append(AssistantEvent(type="validating_citations", message="Validating citations against retrieved chunks."))
        citations = [
            Citation(repo=result.repo_name, file=result.file_path, start_line=result.start_line, end_line=result.end_line)
            for result in reranked[:3]
        ]
        valid, errors = validate_citations(citations, reranked)
        if not valid:
            events.append(AssistantEvent(type="failed", message="Citation validation failed: " + "; ".join(errors)))
            citations = []
        answer = self._synthesize(request.question, reranked)
        events.append(AssistantEvent(type="completed", message="Query completed with validated citations."))
        return QueryResponse(answer=answer, citations=citations, assistant_events=events, retrieved_chunks=reranked)

    def _synthesize(self, question: str, results: list[SearchResult]) -> str:
        if not results:
            return "I could not find indexed code that matches the question yet. Register and ingest repositories, then try again."
        top = results[0]
        return (
            f"The strongest match for '{question}' is in {top.repo_name}/{top.file_path} "
            f"around lines {top.start_line}-{top.end_line}. Review the cited chunks for the grounded context."
        )
