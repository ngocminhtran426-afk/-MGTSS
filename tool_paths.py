from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Iterable


@dataclass(frozen=True)
class ToolPaths:
    root: Path

    def __post_init__(self):
        object.__setattr__(self, "root", self.root.resolve())
        self.ensure_layout()

    @classmethod
    def from_root(cls, root: str | Path | None = None) -> "ToolPaths":
        if root is None:
            root = Path(__file__).resolve().parent
        return cls(Path(root))

    @classmethod
    def from_file(cls, file_path: str | Path, levels_up: int = 0) -> "ToolPaths":
        path = Path(file_path).resolve()
        return cls(path.parents[levels_up])

    @property
    def storage_dir(self) -> Path:
        return self.root / "storage"

    @property
    def config_dir(self) -> Path:
        return self.storage_dir / "config"

    @property
    def data_dir(self) -> Path:
        return self.storage_dir / "data"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def cache_dir(self) -> Path:
        return self.storage_dir / "cache"

    @property
    def output_dir(self) -> Path:
        return self.storage_dir / "output"

    @property
    def temp_dir(self) -> Path:
        return self.storage_dir / "temp"

    @property
    def logs_dir(self) -> Path:
        return self.storage_dir / "logs"

    def ensure_layout(self) -> None:
        for directory in self._layout_directories():
            directory.mkdir(parents=True, exist_ok=True)

    def _layout_directories(self) -> Iterable[Path]:
        yield self.storage_dir
        yield self.config_dir
        yield self.data_dir
        yield self.assets_dir
        yield self.cache_dir
        yield self.output_dir
        yield self.temp_dir
        yield self.logs_dir
        yield self.config_dir / "modules"

    def ensure_file(self, target: str | Path) -> Path:
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return target_path

    def ensure_parent_dir(self, path: str | Path) -> Path:
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return target_path

    def ensure_dir(self, target: str | Path) -> Path:
        target_path = Path(target)
        target_path.mkdir(parents=True, exist_ok=True)
        return target_path

    def mirror_file(self, source: str | Path, destinations) -> None:
        source_path = Path(source)
        if not source_path.exists():
            return

        for destination in destinations:
            destination_path = Path(destination)
            if source_path.resolve() == destination_path.resolve():
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            self._safe_copy_file(source_path, destination_path)

    def config_file(self, *parts) -> Path:
        return self.ensure_file(self.config_dir.joinpath(*parts))

    def data_file(self, *parts) -> Path:
        return self.ensure_file(self.data_dir.joinpath(*parts))

    def cache_file(self, *parts) -> Path:
        target = self.cache_dir.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def cache_dir_for(self, *parts) -> Path:
        return self.ensure_dir(self.cache_dir.joinpath(*parts))

    def output_dir_for(self, *parts) -> Path:
        return self.ensure_dir(self.output_dir.joinpath(*parts))

    def temp_dir_for(self, *parts) -> Path:
        return self.ensure_dir(self.temp_dir.joinpath(*parts))



    def template_file(self) -> Path:
        return self.data_file("templates.json")

    def ui_profiles_file(self) -> Path:
        return self.config_file("ui_profiles.json")

    def api_keys_file(self) -> Path:
        return self.config_file("apiKeys.json")

    def series_contexts_file(self) -> Path:
        return self.config_file("seriesContexts.json")

    def yt_dlp_config_file(self) -> Path:
        return self.config_file("yt-dlp.conf")

    def template_manager_cache_dir(self) -> Path:
        return self.cache_dir_for("template_manager")

    def template_preview_file(self) -> Path:
        return self.cache_file("template_manager", "temp_thumb.jpg")

    def template_preview_video_file(self) -> Path:
        return self.cache_file("template_manager", "sample_video_preview.mp4")

    def viet_hoa_video_config_file(self) -> Path:
        return self.config_file("modules", "viet_hoa_video.json")

    def viet_hoa_video_output_dir(self) -> Path:
        return self.output_dir_for("viet_hoa_video")

    def viet_hoa_video_browser_profile_dir(self, browser: str = "chrome") -> Path:
        return self.cache_dir_for(
            "viet_hoa_video",
            "browser_profiles",
            browser.lower()
        )

    def viet_hoa_video_download_dir(self) -> Path:
        return self.cache_dir_for("viet_hoa_video", "downloads")

    def capcut_temp_dir(self) -> Path:
        return self.temp_dir_for("capcut_dubbing")

    @staticmethod
    def _safe_copy_file(source: Path, destination: Path) -> None:
        try:
            shutil.copy2(source, destination)
        except OSError:
            pass

