"""Stage 3a: preparing modelling tables and, in the later steps, the candidate models and the grouped validation.

Step 3a-1 builds the modelling table: which rows and which inputs each result is predicted from, with every exclusion recorded.
Step 3a-2 adds the grouped splitters (whole batches, whole suppliers, later dates; never random rows) and the guards that check every split.
It imports only the data reader (ingest) and the setup part, and needs no network. It never sees the virtual lab's hidden truth.
"""
from .findings import CATALOGUE, COPY_CORRELATION, MIN_ROWS, PROXY_PHRASE, Finding, Rule, has_errors, make
from .splits import Fold, FoldPlan, SplitError, make_fold_plan, make_fold_plans, plan_problems
from .table import GroupSpec, ModellingTable, ResponseTable, build_table, build_table_for_setup

__all__ = ["CATALOGUE", "COPY_CORRELATION", "MIN_ROWS", "PROXY_PHRASE", "Finding", "Fold", "FoldPlan", "GroupSpec", "ModellingTable", "ResponseTable", "Rule",
           "SplitError", "build_table", "build_table_for_setup", "has_errors", "make", "make_fold_plan", "make_fold_plans", "plan_problems"]
