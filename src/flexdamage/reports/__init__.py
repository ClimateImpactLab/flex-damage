"""
Reports module: Quarto-based report generation.
"""

from .generator import generate_report
from .schema import ReportConfig

__all__ = ["generate_report", "ReportConfig"]
