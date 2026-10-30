"""Reports and exports (Stage 9): from a run record, a branded report page and PDF, an Excel workbook and CSV tables, all labelled illustrative or synthetic. It reads the run record and nothing else, and needs no network."""
from .builder import FILES, ReportError, ReportResult, label_of, write_reports

__all__ = ["FILES", "ReportError", "ReportResult", "label_of", "write_reports"]
