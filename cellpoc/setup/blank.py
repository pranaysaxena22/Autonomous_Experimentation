"""The 'Start blank' setup: every section present with the right shape, nothing filled in that is a client's choice.

Structure and naming conventions (the five step names, the standard column names, the standard hardness conversions) are
filled in; everything a person has to decide (ingredients, ranges, targets, times, dates, counts) is left empty, so the
checker lists exactly what is still to do.
"""
from __future__ import annotations

from .files import list_layouts

STEPS = [("dispense", "Dispense"), ("mix", "Mix"), ("press", "Press"), ("test", "Test"), ("clean", "Clean")]


def blank_setup(banner: str = "Simulation with illustrative values", accent: str = "#86BC25", font: str = "Open Sans") -> dict:
    layouts = list_layouts()
    return {
        "format_version": 1,
        "project": {"name": "", "data_status": "illustrative"},
        "display": {"banner": banner, "accent_colour": accent, "font": font},
        "batch_size_g": None,
        "ingredients": [],
        "recipe_rules": [{"rule": "sum_to", "total": 100, "tolerance": 0.05, "unit": "%", "label": "Ingredients must add up to 100%"}],
        "process_factors": [],
        "context_factors": [],
        "targets": {"constraints": [], "objectives": []},
        "equipment": {
            "layout_file": layouts[0].name if layouts else "",
            "steps": [{"name": name, "label": label, "time_min": None, "stations": []} for name, label in STEPS],
            "measurement_step": "test",
            "phases": {"act": ["dispense", "mix", "press"], "sense": ["test"], "reason_adapt_step": "clean", "reason_min": None},
        },
        "calendar": {"start": "", "duration_h": None, "staffed_days": [], "staffed_from": "", "staffed_until": ""},
        "faults": {"purge_min": None, "clean_after_skip": True, "recovery": {"tap_shake_s": None, "max_retries": None},
                   "scripted": [], "random": []},
        "baseline": {"manual_trials_per_week": None},
        "comparison": {"campaigns": None, "trials_per_campaign": None},
        "engine": {"initial_recipes": None, "candidates_per_decision": None, "model": "auto"},
        "virtual_lab": {"noise": []},
        "seeds": {"run": None},
        "data": {
            "experiments_file": "", "meta_file": "", "encoding": "utf-8", "line_endings": "any",
            "id_columns": {"experiment": "experiment_id", "replicate": "replicate_no", "batch": "batch_id", "date": "date",
                           "status": "status", "failure_reason": "failure_reason"},
            "column_map": {},
            "hardness": {"value_column": "", "unit_column": "", "to": "hardness_kp",
                         "conversions": {"kP": {"divide_by": 1}, "N": {"divide_by": 9.807}}},
            "below_detection": {"note_column": "", "marker": "", "quantity": "", "limit": None, "rule": "use_limit_and_flag"},
            "replicates": {"group_by": ["experiment_id"], "rule": "mean", "keep_individual_rows_for_noise_estimate": True},
            "missing_values": {"policy": "skip_for_that_response"},
            "failed_runs": {"status_column": "status", "failed_value": "failed",
                            "policy": "exclude_from_models_keep_in_failure_statistics"},
        },
    }
