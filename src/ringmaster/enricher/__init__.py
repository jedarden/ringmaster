"""Context enrichment service for prompt assembly."""

from ringmaster.enricher.pipeline import AssembledPrompt, EnrichmentPipeline, get_pipeline
from ringmaster.enricher.rlm import (
    CompressionConfig,
    HistoryContext,
    RLMSummarizer,
    get_history_context,
)
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
    "get_pipeline",
    "BaseStage",
    "ProjectContextStage",
    "TaskContextStage",
    "CodeContextStage",
    "HistoryContextStage",
    "RLMSummarizer",
    "CompressionConfig",
    "HistoryContext",
    "get_history_context",
]
