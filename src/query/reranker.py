from src.config.settings import get_settings
from src.models.schemas import SearchResult
from src.query.retrieval import tokenize


class CrossEncoderReranker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None

    def rerank(self, question: str, results: list[SearchResult], limit: int) -> list[SearchResult]:
        if not results:
            return []
        try:
            model = self._load_model()
            pairs = [(question, f"{result.file_path}\n{result.summary}\n{result.preview}") for result in results]
            scores = model.predict(pairs)
            reranked = [
                result.model_copy(update={"score": float(score), "source": "reranked"})
                for result, score in zip(results, scores)
            ]
            return sorted(reranked, key=lambda result: result.score, reverse=True)[:limit]
        except Exception:
            return lexical_rerank(question, results, limit)

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.settings.cross_encoder_model)
        return self._model


def lexical_rerank(question: str, results: list[SearchResult], limit: int) -> list[SearchResult]:
    question_terms = set(tokenize(question))
    reranked: list[SearchResult] = []
    for result in results:
        text_terms = set(tokenize(f"{result.file_path} {result.summary} {result.preview}"))
        overlap = len(question_terms & text_terms)
        reranked.append(result.model_copy(update={"score": result.score + overlap * 0.1, "source": "reranked"}))
    return sorted(reranked, key=lambda result: result.score, reverse=True)[:limit]
