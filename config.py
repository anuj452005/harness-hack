"""Runtime configuration, loaded from environment / .env file.

Only the dynamic (live) stage needs Harness credentials; the static stage runs
with nothing configured. The Anthropic key is optional — without it the LLM
checks are skipped and the run falls back to deterministic findings only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
# The harness-openapi checkout lives next to the p1/ folder.
OPENAPI_ROOT = REPO_ROOT.parent / "harness-openapi"
RESULTS_DIR = REPO_ROOT / "results"


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Config:
    harness_api_key: str | None
    harness_account: str | None
    anthropic_api_key: str | None
    base_url: str
    # Optional existing org to host project scenarios; if unset a temp org is created.
    harness_org: str | None = None

    @property
    def can_run_live(self) -> bool:
        return bool(self.harness_api_key and self.harness_account)

    @property
    def can_run_llm(self) -> bool:
        return bool(self.anthropic_api_key)


def load_config() -> Config:
    _load_dotenv()
    return Config(
        harness_api_key=os.environ.get("HARNESS_API_KEY"),
        harness_account=os.environ.get("HARNESS_ACCOUNT"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        base_url=os.environ.get("HARNESS_BASE_URL", "https://app.harness.io").rstrip("/"),
        harness_org=os.environ.get("HARNESS_ORG"),
    )


def module_spec_path(module: str) -> Path:
    """Path to a module's openapi.yaml, e.g. 'ng-manager'."""
    return OPENAPI_ROOT / module / "openapi.yaml"
