import ast
import hashlib
from pathlib import Path

from src.models.schemas import ChunkCandidate


class CodeParser:
    def parse_file(self, path: Path, repo_root: Path) -> list[ChunkCandidate]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        language = detect_language(path)
        if language == "python":
            return self._parse_python(path, repo_root, text)
        return self._fallback_chunks(path, repo_root, text, language)

    def _parse_python(self, path: Path, repo_root: Path, text: str) -> list[ChunkCandidate]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return self._fallback_chunks(path, repo_root, text, "python")

        lines = text.splitlines()
        chunks: list[ChunkCandidate] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            raw = "\n".join(lines[start - 1 : end])
            chunk_type = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(
                ChunkCandidate(
                    file_path=str(path.relative_to(repo_root)),
                    language="python",
                    symbol_name=node.name,
                    chunk_type=chunk_type,
                    start_line=start,
                    end_line=end,
                    raw_text=raw,
                    ast_hash=hashlib.sha256(ast.dump(node).encode("utf-8")).hexdigest(),
                    content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    dependencies=python_dependencies(node),
                )
            )
        if chunks:
            return sorted(chunks, key=lambda chunk: (chunk.start_line, chunk.end_line))
        return self._fallback_chunks(path, repo_root, text, "python")

    def _fallback_chunks(self, path: Path, repo_root: Path, text: str, language: str) -> list[ChunkCandidate]:
        lines = text.splitlines()
        chunk_size = 120
        chunks: list[ChunkCandidate] = []
        for index in range(0, max(len(lines), 1), chunk_size):
            window = lines[index : index + chunk_size]
            raw = "\n".join(window)
            start = index + 1
            end = index + max(len(window), 1)
            chunks.append(
                ChunkCandidate(
                    file_path=str(path.relative_to(repo_root)),
                    language=language,
                    symbol_name=None,
                    chunk_type="text",
                    start_line=start,
                    end_line=end,
                    raw_text=raw,
                    ast_hash=None,
                    content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    dependencies=text_dependencies(raw),
                )
            )
        return chunks


def detect_language(path: Path) -> str:
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".md": "markdown",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
    }.get(path.suffix.lower(), "text")


def python_dependencies(node: ast.AST) -> list[str]:
    dependencies: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            dependencies.update(alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom):
            module = child.module or ""
            for alias in child.names:
                dependencies.add(f"{module}.{alias.name}" if module else alias.name)
        elif isinstance(child, ast.Call):
            name = call_name(child.func)
            if name:
                dependencies.add(name)
    return sorted(dependencies)


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def text_dependencies(raw_text: str) -> list[str]:
    dependencies: set[str] = set()
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            dependencies.add(stripped.removeprefix("import ").split()[0])
        elif stripped.startswith("from "):
            parts = stripped.split()
            if len(parts) >= 4 and parts[2] == "import":
                dependencies.add(f"{parts[1]}.{parts[3].split(',')[0]}")
    return sorted(dependencies)
