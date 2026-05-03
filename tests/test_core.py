import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app
from src.ingestion.git_workspace import GitFileChange
from src.ingestion.parser import CodeParser
from src.ingestion.service import IngestionService
from src.models.schemas import Citation, RepositoryCreate, SearchResult
from src.query.citations import validate_citations
from src.query.retrieval import reciprocal_rank_fusion
from src.storage.qdrant_store import chunk_payload, qdrant_point_id
from src.storage.memory import AppState


class ParserTests(unittest.TestCase):
    def test_python_parser_extracts_class_and_function_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "example.py"
            source.write_text(
                "class Service:\n"
                "    def run(self):\n"
                "        return True\n\n"
                "def helper():\n"
                "    return 'ok'\n",
                encoding="utf-8",
            )

            chunks = CodeParser().parse_file(source, root)

        symbols = {chunk.symbol_name for chunk in chunks}
        self.assertIn("Service", symbols)
        self.assertIn("run", symbols)
        self.assertIn("helper", symbols)
        self.assertTrue(all(chunk.content_hash for chunk in chunks))

    def test_python_parser_extracts_call_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "example.py"
            source.write_text(
                "def save_user():\n"
                "    validate_user()\n"
                "    return True\n\n"
                "def validate_user():\n"
                "    return True\n",
                encoding="utf-8",
            )

            chunks = CodeParser().parse_file(source, root)

        save_chunk = next(chunk for chunk in chunks if chunk.symbol_name == "save_user")
        self.assertIn("validate_user", save_chunk.dependencies)


class IngestionTests(unittest.TestCase):
    def test_ingestion_indexes_local_workspace_path(self) -> None:
        state = AppState()
        repo = state.add_repository(
            RepositoryCreate(name="demo", git_url="https://github.com/example/demo.git", default_branch="main")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("def authenticate_user():\n    return True\n", encoding="utf-8")

            chunks = IngestionService(state)._ingest_path(repo, root)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].symbol_name, "authenticate_user")
        self.assertTrue(chunks[0].embedding)
        self.assertIn("authenticate_user", state.chunks[chunks[0].id].raw_text)

    def test_ingestion_populates_graph_symbols_and_edges(self) -> None:
        state = AppState()
        repo = state.add_repository(
            RepositoryCreate(name="demo-graph", git_url="https://github.com/example/demo-graph.git")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text(
                "def save_user():\n"
                "    validate_user()\n\n"
                "def validate_user():\n"
                "    return True\n",
                encoding="utf-8",
            )

            IngestionService(state)._ingest_path(repo, root)

        symbols, edges = state.graph.snapshot(repo.id)
        self.assertEqual({symbol.symbol_name for symbol in symbols}, {"save_user", "validate_user"})
        self.assertIn("validate_user", {edge.target_symbol for edge in edges})

    def test_incremental_ingestion_removes_deleted_file_chunks(self) -> None:
        state = AppState()
        repo = state.add_repository(
            RepositoryCreate(name="demo-delete", git_url="https://github.com/example/demo-delete.git")
        )
        service = IngestionService(state)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "app.py"
            source.write_text("def removed_function():\n    return True\n", encoding="utf-8")
            service._ingest_path(repo, root)
            self.assertEqual(len(state.repo_chunks[repo.id]), 1)

            source.unlink()
            service._ingest_path(repo, root, changes=[GitFileChange(status="D", path="app.py")])

        self.assertEqual(state.repo_chunks[repo.id], [])
        self.assertEqual(state.chunks, {})

    def test_incremental_ingestion_replaces_modified_file_chunks(self) -> None:
        state = AppState()
        repo = state.add_repository(
            RepositoryCreate(name="demo-modify", git_url="https://github.com/example/demo-modify.git")
        )
        service = IngestionService(state)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "app.py"
            source.write_text("def old_function():\n    return True\n", encoding="utf-8")
            service._ingest_path(repo, root)

            source.write_text("def new_function():\n    return False\n", encoding="utf-8")
            service._ingest_path(repo, root, changes=[GitFileChange(status="M", path="app.py")])

        symbols = {chunk.symbol_name for chunk in state.chunks.values()}
        self.assertEqual(symbols, {"new_function"})


class RetrievalTests(unittest.TestCase):
    def test_rrf_merges_sources(self) -> None:
        result = SearchResult(
            chunk_id="chunk-1",
            repo_name="repo",
            file_path="app.py",
            start_line=1,
            end_line=2,
            score=10,
            source="dense",
            retrieval_sources=["dense"],
            summary="summary",
            preview="preview",
        )
        sparse = result.model_copy(update={"source": "sparse", "score": 8})

        fused = reciprocal_rank_fusion([[result], [sparse]], limit=10)

        self.assertEqual(len(fused), 1)
        self.assertEqual(fused[0].source, "fused")
        self.assertEqual(fused[0].retrieval_sources, ["dense", "sparse"])

    def test_citation_validator_rejects_unknown_file(self) -> None:
        result = SearchResult(
            chunk_id="chunk-1",
            repo_name="repo",
            file_path="app.py",
            start_line=1,
            end_line=5,
            score=1,
            source="reranked",
            summary="summary",
            preview="preview",
        )

        valid, errors = validate_citations([Citation(repo="repo", file="missing.py", start_line=1, end_line=2)], [result])

        self.assertFalse(valid)
        self.assertTrue(errors)


class StorageTests(unittest.TestCase):
    def test_qdrant_payload_keeps_original_chunk_id(self) -> None:
        state = AppState()
        repo = state.add_repository(
            RepositoryCreate(name="demo-storage", git_url="https://github.com/example/demo-storage.git")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("def search_code():\n    return True\n", encoding="utf-8")
            chunk = IngestionService(state)._ingest_path(repo, root)[0]

        payload = chunk_payload(chunk)

        self.assertEqual(payload["chunk_id"], chunk.id)
        self.assertEqual(payload["repo_name"], "demo-storage")
        self.assertNotEqual(qdrant_point_id(chunk.id), chunk.id)


class ApiTests(unittest.TestCase):
    def test_api_registers_repo_and_requires_ingestion_permission(self) -> None:
        client = TestClient(app)

        health = client.get("/health")
        self.assertEqual(health.status_code, 200)

        repo_response = client.post(
            "/repositories",
            json={"name": "demo-api", "git_url": "https://github.com/example/demo-api.git"},
        )
        self.assertEqual(repo_response.status_code, 200)
        repo_id = repo_response.json()["id"]

        ingestion = client.post(f"/repositories/{repo_id}/ingest", json={"confirm": False})
        self.assertEqual(ingestion.status_code, 200)
        self.assertEqual(ingestion.json()["status"], "needs_permission")

    def test_graph_endpoint_returns_repository_snapshot(self) -> None:
        client = TestClient(app)
        repo_response = client.post(
            "/repositories",
            json={"name": "graph-api", "git_url": "https://github.com/example/graph-api.git"},
        )
        repo_id = repo_response.json()["id"]

        graph = client.get(f"/repositories/{repo_id}/graph")

        self.assertEqual(graph.status_code, 200)
        self.assertEqual(graph.json()["repo_id"], repo_id)


if __name__ == "__main__":
    unittest.main()
