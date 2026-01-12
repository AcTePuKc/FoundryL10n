from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote
from urllib.request import Request, urlopen

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins"
DEFAULT_OWNER = "FoundryL10n"
DEFAULT_REPO = "FoundryL10n-Providers"
DEFAULT_BRANCH = "main"
DEFAULT_PLUGINS_PATH = "src/plugins"


@dataclass(frozen=True)
class GitHubRepoConfig:
    owner: str = DEFAULT_OWNER
    repo: str = DEFAULT_REPO
    branch: str = DEFAULT_BRANCH
    plugins_path: str = DEFAULT_PLUGINS_PATH


@dataclass(frozen=True)
class RemotePlugin:
    name: str
    path: str
    download_url: str | None


@dataclass(frozen=True)
class PluginSyncResult:
    downloaded: tuple[Path, ...]
    updated: tuple[Path, ...]
    skipped: tuple[Path, ...]
    conflicts: tuple[Path, ...]
    errors: tuple[str, ...]


class GitHubPluginSyncService:
    """
    Explicit, user-triggered sync for provider plugins.

    This service performs no background updates; callers must invoke sync_plugins
    in response to user actions.
    """

    def __init__(
        self,
        *,
        repo: GitHubRepoConfig | None = None,
        plugin_dir: Path | None = None,
        requester: Callable[[str], bytes] | None = None,
    ) -> None:
        self.repo = repo or GitHubRepoConfig()
        self.plugin_dir = plugin_dir or PLUGIN_DIR
        self._requester = requester or self._default_requester

    def build_manifest_url(self) -> str:
        path = quote(self.repo.plugins_path.strip("/"))
        return (
            f"https://api.github.com/repos/{self.repo.owner}/{self.repo.repo}"
            f"/contents/{path}?ref={self.repo.branch}"
        )

    def build_raw_url(self, path: str) -> str:
        sanitized = path.lstrip("/")
        return (
            f"https://raw.githubusercontent.com/{self.repo.owner}/{self.repo.repo}"
            f"/{self.repo.branch}/{sanitized}"
        )

    def fetch_manifest(self) -> list[RemotePlugin]:
        payload = self._fetch_json(self.build_manifest_url())
        if not isinstance(payload, list):
            raise ValueError("Manifest response must be a list of files.")
        items: list[RemotePlugin] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", ""))
            path = str(entry.get("path", ""))
            download_url = entry.get("download_url")
            if not name or not path:
                continue
            items.append(
                RemotePlugin(
                    name=name,
                    path=path,
                    download_url=str(download_url) if download_url else None,
                )
            )
        return items

    def sync_plugins(self, *, allow_overwrite: bool = False) -> PluginSyncResult:
        """Synchronize provider JSON files into the plugin directory.

        Safe overwrite rules:
        - Existing files are left untouched if content differs and allow_overwrite is False.
        - Identical files are skipped.
        - Overwrites are only performed when allow_overwrite is True.
        """
        downloaded: list[Path] = []
        updated: list[Path] = []
        skipped: list[Path] = []
        conflicts: list[Path] = []
        errors: list[str] = []

        try:
            manifest = self.fetch_manifest()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return PluginSyncResult((), (), (), (), (str(exc),))

        self.plugin_dir.mkdir(parents=True, exist_ok=True)

        for entry in self._filter_plugin_entries(manifest):
            target_name = Path(entry.path).name
            target_path = self.plugin_dir / target_name
            download_url = entry.download_url or self.build_raw_url(entry.path)
            try:
                content = self._requester(download_url)
            except OSError as exc:
                errors.append(f"{download_url}: {exc}")
                continue

            if target_path.exists():
                try:
                    existing = target_path.read_bytes()
                except OSError as exc:
                    errors.append(f"{target_path}: {exc}")
                    continue
                if existing == content:
                    skipped.append(target_path)
                    continue
                if not allow_overwrite:
                    conflicts.append(target_path)
                    continue
                self._atomic_write(target_path, content)
                updated.append(target_path)
            else:
                self._atomic_write(target_path, content)
                downloaded.append(target_path)

        return PluginSyncResult(
            downloaded=tuple(downloaded),
            updated=tuple(updated),
            skipped=tuple(skipped),
            conflicts=tuple(conflicts),
            errors=tuple(errors),
        )

    def _filter_plugin_entries(self, manifest: Iterable[RemotePlugin]) -> list[RemotePlugin]:
        entries: list[RemotePlugin] = []
        for entry in manifest:
            name = entry.name.lower()
            if not name.endswith(".json"):
                continue
            if name == "schema.json":
                continue
            entries.append(entry)
        return entries

    def _fetch_json(self, url: str) -> object:
        raw = self._requester(url)
        return json.loads(raw.decode("utf-8"))

    def _default_requester(self, url: str) -> bytes:
        request = Request(url)
        request.add_header("Accept", "application/vnd.github+json")
        with urlopen(request, timeout=10) as response:
            return response.read()

    def _atomic_write(self, path: Path, content: bytes) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_bytes(content)
        tmp_path.replace(path)
