"""Data models and configuration for local-board tracker synchronization."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SyncSettings:
    board_dir: Path
    sync_dir: Path
    relations_path: Path
    tracker_config_path: Path
    project_key: str
    board_label: str
    remote_link_namespace: str
    entity_glob: str
    type_map: dict[str, str]
    status_map: dict[str, str]
    parent_strategy: dict[str, str]
    aliases: dict[str, str]

    @property
    def remote_to_local_status(self) -> dict[str, str]:
        return {remote: local for local, remote in self.status_map.items()}

    @property
    def accounts_to_aliases(self) -> dict[str, str]:
        return {account: alias for alias, account in self.aliases.items() if account}

    @property
    def type_order(self) -> dict[str, int]:
        canonical = ("epic", "story", "task", "sub-task")
        return {asset_type: index for index, asset_type in enumerate(canonical)}


@dataclass
class LocalEntity:
    id: str
    type: str
    summary: str
    status: str
    assignee: str
    assignee_account_id: str
    parent: str | None
    children: list[str]
    jira_key: str
    labels: list[str]
    path: Path
    mtime: datetime
    body: str = ""


@dataclass
class PlanAction:
    entity_id: str
    action: str
    reason: str
    fields: dict[str, Any] = field(default_factory=dict)
    jira_key: str = ""
