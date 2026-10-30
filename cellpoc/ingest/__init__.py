"""Reading the client's experiment table: getting a plain table of text out of a CSV or Excel file safely, with plain-English findings.

Stage 2 builds this in steps. The reader gets the table out of the file (encoding, separator, column names, blank rows); the cleaning step turns text
into numbers, units, dates, missing values and below-detection values. Replicates, failed runs, joins and the quality report come in the next steps. It imports only the setup part
(file-name safety and the shared file-header code) and needs no network.
"""
from .findings import CATALOGUE, Finding, Rule, has_errors, make
from .clean import ColumnReport, CleanResult, Spec, clean_table, read_and_clean
from .join import merge_joins
from .report import DataLabel, build_report, data_label, report_for_setup, write_report
from .rows import RowAccount
from .reader import FileInfo, RawTable, ReadOptions, ReadResult, read_setup_table, read_table

__all__ = ["DataLabel", "build_report", "data_label", "report_for_setup", "write_report", "RowAccount", "merge_joins", "CATALOGUE", "CleanResult", "ColumnReport", "Spec", "clean_table", "read_and_clean", "FileInfo", "Finding", "RawTable", "ReadOptions", "ReadResult", "Rule", "has_errors", "make", "read_setup_table", "read_table"]
