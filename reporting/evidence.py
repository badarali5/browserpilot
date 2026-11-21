from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from database.repository import ReportRepository


SENSITIVE_NAMES = re.compile(
    r"(password|passwd|token|secret|authorization|cookie|session)",
    re.IGNORECASE,
)


def safe_artifact_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or "artifact"


class EvidenceCollector:
    def __init__(
        self,
        repository: ReportRepository,
        run_id: str,
        artifact_root: str | Path,
    ) -> None:
        self.repository = repository
        self.run_id = run_id
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.errors: list[str] = []

    def collect_screenshots(
        self,
        paths: Iterable[str | Path],
        *,
        step_number: int | None = None,
    ) -> list[str]:
        collected: list[str] = []
        for raw_path in paths:
            try:
                source = Path(raw_path)
                if not source.is_file():
                    raise FileNotFoundError(str(source))
                resolved = source.resolve()
                if self.artifact_root not in resolved.parents and resolved != self.artifact_root:
                    raise ValueError("Artifact path is outside the configured artifact root")
                relative = resolved.relative_to(Path.cwd().resolve())
            except Exception as exc:
                message = f"Screenshot collection failed: {exc}"
                self.errors.append(message)
                continue
            artifact_id = self.repository.store_artifact(
                self.run_id,
                relative_path=str(relative),
                artifact_type="screenshot",
                step_number=step_number,
                mime_type="image/png",
            )
            collected.append(artifact_id)
        return collected

    def record_error(self, artifact_type: str, error: str) -> None:
        message = f"{artifact_type} evidence collection failed: {error}"
        self.errors.append(message)
        self.repository.store_artifact(
            self.run_id,
            relative_path="",
            artifact_type=artifact_type,
            collection_error=message,
            mime_type="text/plain",
        )

    def collect_artifact(
        self,
        path: str | Path,
        artifact_type: str,
        *,
        step_number: int | None = None,
        mime_type: str = "application/octet-stream",
    ) -> str | None:
        try:
            source = Path(path)
            if not source.is_file():
                raise FileNotFoundError(str(source))
            resolved = source.resolve()
            if self.artifact_root not in resolved.parents and resolved != self.artifact_root:
                raise ValueError("Artifact path is outside the configured artifact root")
            relative = resolved.relative_to(Path.cwd().resolve())
            return self.repository.store_artifact(
                self.run_id,
                relative_path=str(relative),
                artifact_type=artifact_type,
                step_number=step_number,
                mime_type=mime_type,
            )
        except Exception as exc:
            message = f"{artifact_type} evidence collection failed: {exc}"
            self.errors.append(message)
            return None
