import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    opencode_stream_timeout: int
    opencode_idle_timeout: int
    log_dir: str
    use_frontend_dist: bool
    frontend_dist_dir: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            db_path=os.path.expanduser(
                os.environ.get("OPENCODE_DB_PATH", "~/.local/share/opencode/opencode.db")
            ),
            opencode_stream_timeout=int(os.environ.get("OPENCODE_STREAM_TIMEOUT", "600")),
            opencode_idle_timeout=int(os.environ.get("OPENCODE_IDLE_TIMEOUT", "25")),
            log_dir=os.environ.get(
                "OPENCODE_WEB_LOG_DIR",
                str(Path.home() / ".opencode-session-web" / "logs"),
            ),
            use_frontend_dist=os.environ.get("OPENCODE_USE_FRONTEND_DIST", "").lower()
            in {"1", "true", "yes", "on"},
            frontend_dist_dir=os.environ.get(
                "OPENCODE_FRONTEND_DIST_DIR",
                str(Path(__file__).resolve().parent / "frontend" / "dist"),
            ),
        )

    def to_flask_config(self) -> dict:
        return {
            "OPENCODE_DB_PATH": self.db_path,
            "OPENCODE_STREAM_TIMEOUT": self.opencode_stream_timeout,
            "OPENCODE_IDLE_TIMEOUT": self.opencode_idle_timeout,
            "OPENCODE_WEB_LOG_DIR": self.log_dir,
            "OPENCODE_USE_FRONTEND_DIST": self.use_frontend_dist,
            "OPENCODE_FRONTEND_DIST_DIR": self.frontend_dist_dir,
        }
