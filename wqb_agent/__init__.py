from .diversity import deduplicate, extract_fields, is_redundant
from .search_policy import BudgetAllocator, SearchPolicy
from .failures import (
    FailureKind,
    classify_error,
    classify_experiment,
    is_research_relevant,
)

__all__ = [
    "Agent",
    "WQBClient",
    "extract_fields",
    "is_redundant",
    "deduplicate",
    "BudgetAllocator",
    "SearchPolicy",
    "HighSignalValidator",
    "FailureKind",
    "classify_error",
    "classify_experiment",
    "is_research_relevant",
]


def __getattr__(name):
    """保持包级 API，同时避免导入纯工具时加载生产编排链。

    ``main.py`` 仍可使用 ``from wqb_agent import Agent, WQBClient``；只有
    访问这两个生产入口时才懒加载 Agent/HTTP client，模板工厂和审计工具
    因此不会因包初始化产生网络依赖。
    """
    if name == "Agent":
        from .agent import Agent

        globals()[name] = Agent
        return Agent
    if name == "WQBClient":
        from .client import WQBClient

        globals()[name] = WQBClient
        return WQBClient
    if name == "HighSignalValidator":
        from .validation import HighSignalValidator

        globals()[name] = HighSignalValidator
        return HighSignalValidator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
