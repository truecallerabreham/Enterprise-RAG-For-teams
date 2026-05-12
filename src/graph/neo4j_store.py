from src.models.schemas import DependencyEdge, SymbolRecord
from src.graph.memory import normalize_symbol


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        self._verify_connectivity()

    def _verify_connectivity(self) -> None:
        try:
            self._driver.verify_connectivity()
        except Exception as exc:
            self._driver.close()
            raise RuntimeError(f"Neo4j connection failed: {exc}") from exc

    def close(self) -> None:
        self._driver.close()

    def upsert_symbols(self, symbols: list[SymbolRecord]) -> None:
        if not symbols:
            return
        with self._driver.session(database=self._database) as session:
            for symbol in symbols:
                session.run(
                    """
                    MERGE (c:Chunk {chunk_id: $chunk_id})
                    SET c.repo_id = $repo_id,
                        c.repo_name = $repo_name,
                        c.file_path = $file_path,
                        c.symbol_name = $symbol_name,
                        c.symbol_type = $symbol_type,
                        c.start_line = $start_line,
                        c.end_line = $end_line
                    """,
                    chunk_id=symbol.chunk_id,
                    repo_id=symbol.repo_id,
                    repo_name=symbol.repo_name,
                    file_path=symbol.file_path,
                    symbol_name=symbol.symbol_name,
                    symbol_type=symbol.symbol_type,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )

    def upsert_edges(self, edges: list[DependencyEdge]) -> None:
        if not edges:
            return
        with self._driver.session(database=self._database) as session:
            for edge in edges:
                normalized = normalize_symbol(edge.target_symbol)
                session.run(
                    """
                    MERGE (s:Symbol {normalized_name: $normalized})
                    SET s.name = $target_symbol
                    WITH s
                    MATCH (c:Chunk {chunk_id: $source_chunk_id})
                    MERGE (c)-[r:REFERENCES {relationship: $relationship}]->(s)
                    """,
                    source_chunk_id=edge.source_chunk_id,
                    target_symbol=edge.target_symbol,
                    normalized=normalized,
                    relationship=edge.relationship,
                )

    def related_symbols(self, chunk_id: str) -> list[str]:
        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (c:Chunk {chunk_id: $chunk_id})-[r:REFERENCES]->(s:Symbol)
                RETURN s.name AS symbol_name
                """,
                chunk_id=chunk_id,
            )
            return [record["symbol_name"] for record in result]

    def related_chunk_ids(self, chunk_id: str) -> list[str]:
        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (c:Chunk {chunk_id: $chunk_id})-[r:REFERENCES]->(s:Symbol)
                MATCH (other:Chunk)-[:REFERENCES]->(s)
                WHERE other.chunk_id <> $chunk_id
                RETURN DISTINCT other.chunk_id AS chunk_id
                """,
                chunk_id=chunk_id,
            )
            return [record["chunk_id"] for record in result]

    def snapshot(self, repo_id: str) -> tuple[list[SymbolRecord], list[DependencyEdge]]:
        with self._driver.session(database=self._database) as session:
            symbols_result = session.run(
                """
                MATCH (c:Chunk {repo_id: $repo_id})
                RETURN c.chunk_id AS chunk_id,
                       c.repo_id AS repo_id,
                       c.repo_name AS repo_name,
                       c.file_path AS file_path,
                       c.symbol_name AS symbol_name,
                       c.symbol_type AS symbol_type,
                       c.start_line AS start_line,
                       c.end_line AS end_line
                """,
                repo_id=repo_id,
            )
            symbols = [
                SymbolRecord(
                    chunk_id=record["chunk_id"],
                    repo_id=record["repo_id"],
                    repo_name=record["repo_name"],
                    file_path=record["file_path"],
                    symbol_name=record["symbol_name"],
                    symbol_type=record["symbol_type"],
                    start_line=record["start_line"],
                    end_line=record["end_line"],
                )
                for record in symbols_result
            ]
            chunk_ids = [s.chunk_id for s in symbols]
            if not chunk_ids:
                return [], []
            edges_result = session.run(
                """
                MATCH (c:Chunk)-[r:REFERENCES]->(s:Symbol)
                WHERE c.chunk_id IN $chunk_ids
                RETURN c.chunk_id AS source_chunk_id,
                       s.name AS target_symbol,
                       r.relationship AS relationship
                """,
                chunk_ids=chunk_ids,
            )
            edges = [
                DependencyEdge(
                    source_chunk_id=record["source_chunk_id"],
                    target_symbol=record["target_symbol"],
                    relationship=record["relationship"],
                )
                for record in edges_result
            ]
            return symbols, edges

    def remove_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        with self._driver.session(database=self._database) as session:
            session.run(
                """
                MATCH (c:Chunk)
                WHERE c.chunk_id IN $chunk_ids
                DETACH DELETE c
                """,
                chunk_ids=chunk_ids,
            )
