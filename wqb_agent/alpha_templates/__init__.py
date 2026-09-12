"""Standalone, read-only Alpha template catalog and registry."""

from .loader import load_builtin_templates, load_templates
from .model import AlphaTemplate, TemplateNumericSlot
from .registry import (
    DEFAULT_TEMPLATES,
    ECONOMIC_TEMPLATES,
    TEMPLATE_FIXED_NUMERICS,
    AlphaTemplateRegistry,
    template_numeric_audit,
)

__all__ = [
    "AlphaTemplate",
    "TemplateNumericSlot",
    "AlphaTemplateRegistry",
    "DEFAULT_TEMPLATES",
    "ECONOMIC_TEMPLATES",
    "TEMPLATE_FIXED_NUMERICS",
    "template_numeric_audit",
    "load_builtin_templates",
    "load_templates",
]
