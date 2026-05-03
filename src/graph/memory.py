from collections import defaultdict

from src.models.schemas import DependencyEdge, SymbolRecord


class MemoryGraph:
    def __init__(self) -> None:
        self.edges: list[DependencyEdge] = []
        self.symbols: dict[str, SymbolRecord] = {}
        self._by_source_chunk: dict[str, list[DependencyEdge]] = defaultdict(list)
        self._symbols_by_repo: dict[str, list[str]] = defaultdict(list)
        self._chunks_by_symbol: dict[str, list[str]] = defaultdict(list)

    def upsert_symbols(self, symbols: list[SymbolRecord]) -> None:
        for symbol in symbols:
            self.symbols[symbol.chunk_id] = symbol
            if symbol.chunk_id not in self._symbols_by_repo[symbol.repo_id]:
                self._symbols_by_repo[symbol.repo_id].append(symbol.chunk_id)
            normalized = normalize_symbol(symbol.symbol_name)
            if symbol.chunk_id not in self._chunks_by_symbol[normalized]:
                self._chunks_by_symbol[normalized].append(symbol.chunk_id)

    def upsert_edges(self, edges: list[DependencyEdge]) -> None:
        existing = {(edge.source_chunk_id, edge.target_symbol, edge.relationship) for edge in self.edges}
        for edge in edges:
            key = (edge.source_chunk_id, edge.target_symbol, edge.relationship)
            if key not in existing:
                self.edges.append(edge)
                self._by_source_chunk[edge.source_chunk_id].append(edge)
                existing.add(key)

    def related_symbols(self, chunk_id: str) -> list[str]:
        return [edge.target_symbol for edge in self._by_source_chunk.get(chunk_id, [])]

    def related_chunk_ids(self, chunk_id: str) -> list[str]:
        related: list[str] = []
        for symbol in self.related_symbols(chunk_id):
            for target_chunk_id in self._chunks_by_symbol.get(normalize_symbol(symbol), []):
                if target_chunk_id != chunk_id and target_chunk_id not in related:
                    related.append(target_chunk_id)
        return related

    def snapshot(self, repo_id: str) -> tuple[list[SymbolRecord], list[DependencyEdge]]:
        symbol_ids = set(self._symbols_by_repo.get(repo_id, []))
        symbols = [self.symbols[symbol_id] for symbol_id in symbol_ids if symbol_id in self.symbols]
        edges = [edge for edge in self.edges if edge.source_chunk_id in symbol_ids]
        return symbols, edges

    def remove_chunks(self, chunk_ids: list[str]) -> None:
        removing = set(chunk_ids)
        if not removing:
            return
        for chunk_id in removing:
            symbol = self.symbols.pop(chunk_id, None)
            self._by_source_chunk.pop(chunk_id, None)
            if symbol and chunk_id in self._symbols_by_repo.get(symbol.repo_id, []):
                self._symbols_by_repo[symbol.repo_id].remove(chunk_id)
            if symbol:
                normalized = normalize_symbol(symbol.symbol_name)
                if chunk_id in self._chunks_by_symbol.get(normalized, []):
                    self._chunks_by_symbol[normalized].remove(chunk_id)
        self.edges = [
            edge
            for edge in self.edges
            if edge.source_chunk_id not in removing and edge.target_symbol not in removing
        ]


def normalize_symbol(symbol: str) -> str:
    return symbol.rsplit(".", maxsplit=1)[-1].strip().lower()
