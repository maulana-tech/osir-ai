"""Runtime configuration, all from environment variables.

STUDIO_URL          Base URL of the Osir AI Studio instance (https://studio.example.com)
STUDIO_API_KEY      Workspace-scoped API key (bb_studio_...) issued from Organization → API Keys
BEDROCK_MODEL_ID    Bedrock model id for the agent (default: Claude Sonnet, global inference profile)
AWS_REGION          Bedrock region (default: us-west-2)
OSIR_DRY_RUN        "1" to hide every write tool so the agent can only observe and report
OSIR_BRAND_VOICE    Optional one-paragraph description of the brand's voice for replies and drafts
OSIR_MAX_REPLIES    Max inbox replies per run (default 10)
OSIR_MAX_DRAFTS     Max drafts per calendar run (default 3)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    studio_url: str
    studio_api_key: str
    model_id: str
    region: str
    dry_run: bool
    brand_voice: str
    max_replies: int
    max_drafts: int

    @property
    def mcp_url(self) -> str:
        return self.studio_url.rstrip("/") + "/api/v1/mcp/"


def load_settings() -> Settings:
    url = os.environ.get("STUDIO_URL", "").strip()
    key = os.environ.get("STUDIO_API_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("STUDIO_URL and STUDIO_API_KEY must be set")
    return Settings(
        studio_url=url,
        studio_api_key=key,
        model_id=os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
        region=os.environ.get("AWS_REGION", "us-west-2"),
        dry_run=_flag("OSIR_DRY_RUN"),
        brand_voice=os.environ.get("OSIR_BRAND_VOICE", "").strip(),
        max_replies=int(os.environ.get("OSIR_MAX_REPLIES", "10")),
        max_drafts=int(os.environ.get("OSIR_MAX_DRAFTS", "3")),
    )
