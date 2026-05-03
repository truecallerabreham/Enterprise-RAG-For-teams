from src.config.settings import get_settings
from src.query.retrieval import embed_text


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    def embed_document(self, text: str) -> list[float]:
        return self._voyage_embed([text], input_type="document")[0]

    def embed_query(self, text: str) -> list[float]:
        return self._voyage_embed([text], input_type="query")[0]

    def _voyage_embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        try:
            import voyageai

            if self._client is None:
                self._client = voyageai.Client()
            result = self._client.embed(texts, model=self.settings.voyage_model, input_type=input_type)
            return [list(embedding) for embedding in result.embeddings]
        except Exception:
            return self._cohere_embed(texts, input_type)
            
    def _cohere_embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        try:
            import cohere
            import os
            
            client = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))
            cohere_input_type = "search_document" if input_type == "document" else "search_query"
            
            response = client.embed(
                texts=texts,
                model=self.settings.cohere_model,
                input_type=cohere_input_type,
                embedding_types=["float"]
            )
            return response.embeddings.float_
        except Exception:
            from src.query.retrieval import embed_text
            return [embed_text(text) for text in texts]
