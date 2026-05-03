from src.models.schemas import AssistantEvent, Citation, QueryRequest, QueryResponse, SearchResult
from src.llm.synthesis import AnswerSynthesizer
from src.query.citations import validate_citations
from src.query.embedding import EmbeddingService
from src.query.reranker import CrossEncoderReranker
from src.query.retrieval import dense_search, graph_expand, reciprocal_rank_fusion, sparse_search
from src.storage.memory import AppState


class QueryService:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.embedding = EmbeddingService()
        self.reranker = CrossEncoderReranker()
        self.synthesizer = AnswerSynthesizer()

    def answer(self, request: QueryRequest) -> QueryResponse:
        events = [
            AssistantEvent(type="planning", message="Planning retrieval across registered repositories."),
            AssistantEvent(type="searching", message="Running dense and sparse retrieval over indexed chunks."),
        ]
        repo_ids = set(request.repo_ids)
        unindexed = [
            repo
            for repo_id, repo in self.state.repositories.items()
            if (not repo_ids or repo_id in repo_ids) and repo.chunk_count == 0
        ]
        if unindexed:
            names = ", ".join(repo.name for repo in unindexed)
            events.append(
                AssistantEvent(
                    type="needs_permission",
                    message=f"{names} has no indexed chunks yet. Confirm ingestion before expecting search results.",
                )
            )
        query_vector = self.embedding.embed_query(request.question)
        dense = dense_search(self.state, query_vector, repo_ids)
        sparse = sparse_search(self.state, request.question, repo_ids)
        fused = reciprocal_rank_fusion([dense, sparse], limit=max(request.top_k * 4, 20))
        events.append(AssistantEvent(type="expanding_graph", message="Expanding top results through the symbol graph."))
        expanded = graph_expand(self.state, fused, repo_ids, limit=10)
        events.append(AssistantEvent(type="reranking", message="Reranking candidates with cross-encoder adapter."))
        reranked = self.reranker.rerank(request.question, expanded, request.top_k)
        events.append(AssistantEvent(type="validating_citations", message="Validating citations against retrieved chunks."))
        citations = [
            Citation(
                repo=result.repo_name,
                file=result.file_path,
                start_line=result.start_line,
                end_line=result.end_line,
                url=result.url,
            )
            for result in reranked[:3]
        ]
        valid, errors = validate_citations(citations, reranked)
        if not valid:
            events.append(AssistantEvent(type="failed", message="Citation validation failed: " + "; ".join(errors)))
            citations = []
        events.append(AssistantEvent(type="synthesizing", message="Synthesizing answer from retrieved code context."))
        answer = self.synthesizer.synthesize(request.question, reranked)
        events.append(AssistantEvent(type="completed", message="Query completed with validated citations."))
        return QueryResponse(answer=answer, citations=citations, assistant_events=events, retrieved_chunks=reranked)
