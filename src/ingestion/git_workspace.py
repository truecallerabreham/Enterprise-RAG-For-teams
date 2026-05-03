import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from src.config.settings import get_settings
from src.models.schemas import RepositoryCreate, RepositoryRecord


class GitFileChange:
    def __init__(self, status: str, path: str, previous_path: str | None = None) -> None:
        self.status = status
        self.path = path
        self.previous_path = previous_path


class GitWorkspace:
    def __init__(self) -> None:
        self.root = get_settings().workspace_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def prepare(self, repo: RepositoryRecord) -> Path:
        repo_path = self.path_for(repo)
        git_url = self._url_with_token(repo)
        if (repo_path / ".git").exists():
            self._run(["git", "fetch", "--all", "--prune"], repo_path)
        else:
            self._run(["git", "clone", git_url, str(repo_path)], self.root)
        self._run(["git", "checkout", repo.default_branch], repo_path)
        self._run(["git", "pull", "--ff-only"], repo_path)
        return repo_path

    def current_commit(self, repo_path: Path) -> str:
        return self._run(["git", "rev-parse", "HEAD"], repo_path).strip()

    def validate_remote(self, repo: RepositoryCreate) -> tuple[bool, str]:
        git_url = self._url_with_token(repo)
        try:
            self._run(["git", "ls-remote", "--exit-code", "--heads", git_url, repo.default_branch], self.root)
            return True, "Git remote and branch are reachable."
        except RuntimeError as exc:
            return False, str(exc)

    def changed_files(self, repo_path: Path, base_ref: str | None, head_ref: str | None) -> list[str]:
        if not base_ref or not head_ref:
            return []
        result = self._run(["git", "diff", "--name-only", base_ref, head_ref], repo_path)
        return [line.strip() for line in result.splitlines() if line.strip()]

    def changed_file_statuses(self, repo_path: Path, base_ref: str | None, head_ref: str | None) -> list[GitFileChange]:
        if not base_ref or not head_ref:
            return []
        result = self._run(["git", "diff", "--name-status", base_ref, head_ref], repo_path)
        changes: list[GitFileChange] = []
        for line in result.splitlines():
            parts = line.split("\t")
            if not parts:
                continue
            status = parts[0]
            if status.startswith("R") and len(parts) >= 3:
                changes.append(GitFileChange(status="R", previous_path=parts[1], path=parts[2]))
            elif len(parts) >= 2:
                changes.append(GitFileChange(status=status[:1], path=parts[1]))
        return changes

    def path_for(self, repo: RepositoryRecord) -> Path:
        safe_id = repo.id.replace("/", "_").replace("\\", "_")
        path = (self.root / safe_id).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("Resolved repository path escaped workspace root")
        return path

    def _url_with_token(self, repo: RepositoryRecord) -> str:
        if not repo.credential_env_var:
            return repo.git_url
        token = os.getenv(repo.credential_env_var)
        if not token:
            return repo.git_url
        parsed = urlparse(repo.git_url)
        if parsed.scheme not in {"http", "https"}:
            return repo.git_url
        netloc = f"{token}@{parsed.netloc}"
        return urlunparse(parsed._replace(netloc=netloc))

    def _run(self, args: list[str], cwd: Path) -> str:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            command = " ".join(args[:3])
            detail = (result.stderr or result.stdout or "No Git error output was provided.").strip()
            raise RuntimeError(f"{command} failed with exit code {result.returncode}: {detail}")
        return result.stdout


def source_web_url(git_url: str) -> str | None:
    parsed = urlparse(git_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "github.com":
        path = parsed.path.removesuffix(".git").strip("/")
        return f"https://github.com/{path}"
    if git_url.startswith("git@github.com:"):
        path = git_url.removeprefix("git@github.com:").removesuffix(".git")
        return f"https://github.com/{path}"
    return None
