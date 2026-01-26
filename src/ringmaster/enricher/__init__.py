"""Context enrichment service for prompt assembly."""

from ringmaster.enricher.pipeline import AssembledPrompt, EnrichmentPipeline
from ringmaster.enricher.stages import (
    BaseStage,
    CodeContextStage,
    HistoryContextStage,
    ProjectContextStage,
    TaskContextStage,
)

__all__ = [
    "EnrichmentPipeline",
    "AssembledPrompt",
    "BaseStage",
    "ProjectContextStage",
    "TaskContextStage",
    "CodeContextStage",
    "HistoryContextStage",
]
