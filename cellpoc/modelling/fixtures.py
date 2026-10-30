"""The five tables the modelling is tested on: three synthetic mock files and two real public datasets, each as a setup that says how to model it.

The mocks use the bundled example setup. The two public datasets start from the ingestion fixtures (which say how to read the files) and add only
what modelling needs: the columns it uses, which results to predict, which columns say what a batch, a supplier or a date is, and what is calculated
from what. Nothing here reads a file; the table builder does. The public data is never presented as client data, and is never in git.
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from cellpoc.setup import PROJECT_ROOT, example_setup_path, load_setup

INGEST_FIXTURES = Path(__file__).resolve().parents[1] / "ingest" / "fixtures"
MOCK_FILES = {"mock_easy": "mock_formulation_experiments.csv", "mock_hard": "mock_formulation_hard.csv", "mock_small": "mock_formulation_small.csv"}
NAMES = ("mock_easy", "mock_hard", "mock_small", "batch_production", "batch_production_extended", "literature")
PUBLIC = ("batch_production", "batch_production_extended", "literature")        # real public data: only present on a computer that downloaded it

# ---- the batch dataset: raw-material properties and process summaries are inputs; every test of the finished tablet is a result, never an input
BATCH_RAW = {"api_code": "api_code", "api_batch": "api_batch", "api_total_impurities": "api_total_impurities", "api_l_impurity": "api_l_impurity",
             "api_ps01": "api_ps01", "api_ps05": "api_ps05", "api_ps09": "api_ps09", "lactose_water": "lactose_water", "lactose_sieve0045": "lactose_sieve0045",
             "lactose_sieve015": "lactose_sieve015", "lactose_sieve025": "lactose_sieve025", "smcc_water": "smcc_water", "smcc_td": "smcc_td",
             "smcc_bd": "smcc_bd", "smcc_ps01": "smcc_ps01", "smcc_ps05": "smcc_ps05", "smcc_ps09": "smcc_ps09", "starch_ph": "starch_ph",
             "starch_water": "starch_water", "tbl_tensile": "tbl_tensile", "tbl_max_diameter": "tbl_max_diameter", "tbl_min_thickness": "tbl_min_thickness",
             "tbl_max_thickness": "tbl_max_thickness", "tbl_yield": "tbl_yield"}
BATCH_PROCESS = ["tbl_speed_change", "tbl_speed_0_duration", "fom_mean", "fom_change", "SREL_startup_mean", "SREL_production_mean", "SREL_production_max",
                 "main_CompForce mean", "main_CompForce_sd", "main_CompForce_median", "pre_CompForce_mean", "tbl_fill_mean", "tbl_fill_sd",
                 "cyl_height_mean", "stiffness_mean", "stiffness_max", "stiffness_min", "ejection_mean", "ejection_max", "ejection_min",
                 "Startup_tbl_fill_maxDifference", "Startup_main_CompForce_mean", "Startup_tbl_fill_mean"]
BATCH_INPUTS = (["product_code", "strength", "weekend", "api_water", "api_content", "tbl_speed_mean"] + [k for k in BATCH_RAW if k.split("_")[0] in ("api", "lactose", "smcc", "starch")
                and k not in ("api_code", "api_batch")])


def _process_id(raw: str) -> str:
    return raw.lower().replace(" ", "_")


def _mock(name: str) -> dict:
    setup = copy.deepcopy(load_setup(example_setup_path()).setup)
    data = setup["data"]
    data["experiments_file"] = f"data/mock/{MOCK_FILES[name]}"
    data.pop("meta_file", None)
    data["provenance"] = {"data_status": "synthetic", "label": "SYNTHETIC mock data made by tools/make_mock_data.py: it says nothing about real tablets",
                          "source": "tools/make_mock_data.py", "contains_real_client_data": False}
    data["validation"] = {"responses": ["dissolution_30min_pct", "hardness_kp", "friability_pct"],
                          "groups": {"batch": {"column": "batch_id"}, "supplier": {"column": "binder_supplier", "confirmed": True,
                                                                                  "note": "the mock's three binder suppliers, whole suppliers are held out"},
                                     "date": {"column": "date"}}}
    return setup


def synthetic_file_setup(relative_path: str, source: str) -> dict:
    """A setup for a synthetic experiments file in the mock data's 21-column format (the development lab's histories), with the same reading and modelling sections as the mocks.
    The path is relative to the project folder. Nothing here is real data."""
    setup = _mock("mock_easy")
    setup["data"]["experiments_file"] = relative_path
    setup["data"]["provenance"] = {"data_status": "synthetic", "label": f"SYNTHETIC development-lab data made by {source}: it says nothing about real tablets", "source": source,
                                   "contains_real_client_data": False}
    return setup


# Two impurity measurements are empty for most batches of one API code (370 of its 481 batches lack the first; 67 lack the second). Requiring them removes whole
# API lots (91 of 238) and thins the supplier and forward-in-time folds, so there are two comparisons: the main one without them, and an exploratory one with them.
IMPURITY_INPUTS = ("api_l_impurity", "api_total_impurities")
EXPLORATORY_BATCH = ("exploratory, smaller and non-random sample (only batches where both impurity measurements exist), missingness tied to one API source "
                     "(confirmed in the source paper's Missing data section; every missing value is in the batches of a single API code), not part of the main comparison")


def _batch(extended: bool = False) -> dict:
    setup = yaml.safe_load((INGEST_FIXTURES / "batch_production_joined_setup.yaml").read_text(encoding="utf-8"))
    data = setup["data"]
    data["column_map"].update(BATCH_RAW)
    data["column_map"].update({f"process_{raw}": _process_id(raw) for raw in BATCH_PROCESS})
    inputs = BATCH_INPUTS + [_process_id(raw) for raw in BATCH_PROCESS]
    if not extended:
        inputs = [i for i in inputs if i not in IMPURITY_INPUTS]
    data["validation"] = {
        "responses": ["dissolution_av", "tbl_av_hardness", "tbl_tensile", "batch_yield"],
        "inputs": inputs,
        # tensile strength is calculated from the crushing force (hardness), the diameter and the thickness
        "derived_from": {"tbl_tensile": ["tbl_av_hardness", "tbl_max_diameter", "tbl_min_thickness", "tbl_max_thickness"]},
        "groups": {"batch": {"column": "api_batch", "note": "the API lot: 238 lots, the finest raw-material lot in the file. The file's own batch column has one row per batch, so it cannot be held out"},
                   "supplier": {"column": "api_code", "confirmed": False,
                                "note": "the file has no supplier column. api_code (5 values) is the coarsest source-like split it offers; what the code stands for is not stated"},
                   "date": {"column": "date", "note": "the month the batch started: every batch in a month shares one time value"}},
        "left_out": [{"id": "drug_release_average", "why": "an exact copy of dissolution_av that Process.csv carries; never an input"},
                     {"id": "tbl_yield", "why": "tbl_yield and batch_yield correlate at 0.95 (near-duplicates), so only batch_yield is modelled and the two must never be presented as independent findings"}],
    }
    if extended:
        data["validation"]["exploratory"] = EXPLORATORY_BATCH
    else:
        data["validation"]["left_out"].append({"id": "api_l_impurity", "why": "empty in 370 of 1,005 batches (all in one API code); required only in the exploratory comparison"})
        data["validation"]["left_out"].append({"id": "api_total_impurities", "why": "empty in 67 of 1,005 batches (all in one API code); required only in the exploratory comparison"})
    return setup


def _literature() -> dict:
    setup = yaml.safe_load((INGEST_FIXTURES / "literature_setup.yaml").read_text(encoding="utf-8"))
    data = setup["data"]
    descriptors = {"Molecular Weight": "molecular_weight", "XLogP3-AA": "xlogp3_aa", "Hydrogen Bond Donor Count": "h_bond_donors",
                   "Hydrogen Bond Acceptor Count": "h_bond_acceptors", "Rotational bond count": "rotatable_bonds",
                   "Topological surface area": "topological_surface_area", "Heavy atom count": "heavy_atoms", "Complexity": "complexity", "LogS": "logs"}
    data["column_map"].update(descriptors)
    amounts = [v for v in data["column_map"].values() if v.endswith("_mg") and v != "tablet_weight_mg"]
    data["validation"] = {
        "responses": ["hardness_kp", "friability_pct", "disintegration_time_s"],
        "inputs": [a[:-3] + "_pct" for a in amounts] + list(descriptors.values()) + ["tablet_weight_mg"],
        "groups": {"api": {"column": list(descriptors.values()),
                           "note": "the file has no API name or paper ID. An API is inferred from identical molecular descriptors (126 groups, matching the dataset's own list of 126 APIs). "
                                   "Rows from one paper that studies several APIs can still share conditions across groups"}},
        "left_out": [{"id": "drug_content_pct", "why": "755 zeros that cannot be confirmed as real measurements (more likely 'not measured'); no one on the team can confirm"},
                     {"id": "water_absorption_pct", "why": "1,046 zeros that cannot be confirmed as real measurements (more likely 'not measured'); no one on the team can confirm"},
                     {"id": "wetting_time_s", "why": "462 zeros that cannot be confirmed as real measurements (more likely 'not measured'); no one on the team can confirm"}],
    }
    return setup


def fixture_setup(name: str) -> dict:
    """The setup that says how to read and model one of the five tables."""
    if name in MOCK_FILES:
        return _mock(name)
    if name in ("batch_production", "batch_production_extended"):
        return _batch(extended=name.endswith("extended"))
    if name == "literature":
        return _literature()
    raise KeyError(f"no such fixture: {name} (the fixtures are {', '.join(NAMES)})")


def fixture_available(name: str) -> bool:
    """The mocks are in the project; the public data is only there if it was downloaded (it is never committed)."""
    data = fixture_setup(name)["data"]
    files = [data["experiments_file"]] + [j["file"] for j in data.get("joins", [])]
    return all((PROJECT_ROOT / f).exists() for f in files)
