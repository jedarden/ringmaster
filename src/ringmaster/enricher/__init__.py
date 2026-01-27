"""Context enrichment service for prompt assembly."""

from ringmaster.enricher.code_context import (
    CodeContextExtractor,
    CodeContextResult,
    FileContext,
    format_code_context,
)
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
    DeploymentContextStage,
    HistoryContextStage,
    LogsContextStage,
    ProjectContextStage,
    RefinementStage,
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
    "DeploymentContextStage",
    "HistoryContextStage",
    "LogsContextStage",
    "RefinementStage",
    "RLMSummarizer",
    "CompressionConfig",
    "HistoryContext",
    "get_history_context",
    "CodeContextExtractor",
    "CodeContextResult",
    "FileContext",
    "format_code_context",
]
