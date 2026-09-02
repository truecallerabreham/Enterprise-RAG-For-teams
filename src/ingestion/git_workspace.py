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
        if _is_local_path(repo.git_url):
            return _resolve_local_path(repo.git_url)
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
        try:
            return self._run(["git", "rev-parse", "HEAD"], repo_path).strip()
        except RuntimeError:
            return "local"

    def validate_remote(self, repo: RepositoryCreate) -> tuple[bool, str]:
        if _is_local_path(repo.git_url):
            try:
                path = _resolve_local_path(repo.git_url)
            except (FileNotFoundError, RuntimeError) as exc:
                return False, str(exc)
            if not path.is_dir():
                return False, f"Local path '{path}' is not a directory."
            return True, f"Local path '{path}' is reachable."
        git_url = self._url_with_token(repo)
        try:
            self._run(["git", "ls-remote", "--exit-code", "--heads", git_url, repo.default_branch], self.root)
            return True, "Git remote and branch are reachable."
        except RuntimeError as exc:
            return False, str(exc)

    def validate_remote_with_default(
        self, repo: RepositoryCreate
    ) -> tuple[bool, str, RepositoryCreate]:
        """Fallback: detect the remote's default branch via HEAD symref and retry validation."""
        if _is_local_path(repo.git_url):
            return False, "Local path validation does not support auto-default-branch.", repo
        git_url = self._url_with_token(repo)
        try:
            result = self._run(["git", "ls-remote", "--symref", git_url, "HEAD"], self.root)
        except RuntimeError as exc:
            return False, str(exc), repo
        for line in result.splitlines():
            if line.startswith("ref:") and "refs/heads/" in line:
                head_branch = line.split("refs/heads/", 1)[1].split()[0].strip()
                if head_branch and head_branch != repo.default_branch:
                    candidate = repo.model_copy(update={"default_branch": head_branch})
                    try:
                        self._run(["git", "ls-remote", "--exit-code", "--heads", git_url, head_branch], self.root)
                        return True, f"Git remote is reachable. Default branch auto-detected as '{head_branch}'.", candidate
                    except RuntimeError:
                        continue
        return False, "Could not determine the remote's default branch.", repo

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


def _is_local_path(git_url: str) -> bool:
    if not git_url:
        return False
    if git_url.startswith("file://"):
        return True
    parsed = urlparse(git_url)
    if parsed.scheme and parsed.scheme not in {"http", "https", "git", "ssh"}:
        return True
    if parsed.scheme in {"http", "https", "git", "ssh"}:
        return False
    return Path(git_url).exists() or any(part in git_url for part in (":\\", ":/", "/"))


def _resolve_local_path(git_url: str) -> Path:
    if git_url.startswith("file://"):
        parsed = urlparse(git_url)
        raw = parsed.path
        if parsed.netloc:
            raw = f"//{parsed.netloc}{raw}"
        return Path(_local_path_from(raw))
    return Path(_local_path_from(git_url))


def _local_path_from(raw: str) -> str:
    cleaned = raw.strip().strip('"').strip("'")
    if len(cleaned) >= 2 and cleaned[1] == ":":
        return cleaned
    return cleaned.replace("/", os.sep)