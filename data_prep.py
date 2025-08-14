# data_prep.py
from __future__ import annotations

import os
from typing import List, Optional

import numpy as np
import pandas as pd
import yaml


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # Defaults
    cfg.setdefault("run_name", "team_run")
    cfg.setdefault("output_root", "./outputs")
    cfg.setdefault("num_teams", None)
    cfg.setdefault("roles", [1, 2, 3, 4, 5])
    cfg.setdefault("role_weights", {r: 1.0 for r in cfg["roles"]})
    cfg.setdefault("captain_policy", "none")  # "none"|"at_least_one"|"separate"
    cfg.setdefault("captain_hard", False)
    cfg.setdefault("conflict_weight", 1.0)
    cfg.setdefault("balance_weight", 1.0)
    cfg.setdefault("captain_weight", 5.0)
    cfg.setdefault("presets", {})
    cfg.setdefault("random_seed", 42)
    cfg.setdefault("plot_dpi", 140)
    return cfg


def prepare_data(signups_csv: str, roles: List[int]) -> pd.DataFrame:
    df = pd.read_csv(signups_csv)
    expected = ["Name", "Skill", "Position", "Captain", "Avoid"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in signups CSV: {missing}")

    df["Name"] = df["Name"].astype(str).str.strip()
    df["Position"] = df["Position"].astype(int)
    df["Captain"] = df["Captain"].astype(int)
    df["Skill"] = df["Skill"].astype(float)

    def clean_avoid(x):
        if pd.isna(x):
            return None
        s = str(x).strip()
        return s if len(s) else None

    df["Avoid"] = df["Avoid"].map(clean_avoid)

    bad_roles = set(df["Position"].unique()) - set(roles)
    if bad_roles:
        raise ValueError(f"Found unknown roles {bad_roles}; allowed roles are {roles}")

    if df["Name"].duplicated().any():
        dups = df[df["Name"].duplicated()]["Name"].tolist()
        raise ValueError(f"Duplicate player names found: {dups}. Names must be unique.")

    return df


def infer_num_teams(df: pd.DataFrame, roles: List[int], num_teams_cfg: Optional[int]) -> int:
    if num_teams_cfg is not None:
        num_teams = int(num_teams_cfg)
    else:
        counts = df.groupby("Position")["Name"].count()
        if set(counts.index) != set(roles):
            raise ValueError(
                f"Dataset roles {sorted(counts.index)} don't match configured roles {roles}."
            )
        vals = counts.values
        if not np.all(vals == vals[0]):
            raise ValueError("Each role must have the same number of players to form balanced teams.")
        num_teams = int(vals[0])

    R = len(roles)
    if len(df) != num_teams * R:
        raise ValueError(
            f"Player count ({len(df)}) != num_teams ({num_teams}) * roles ({R}). "
            f"Fix the input or num_teams."
        )
    return num_teams


def save_effective_config(cfg: dict, used_dir: str, signups_csv: str) -> str:
    eff = dict(cfg)
    eff["signups_csv"] = os.path.abspath(signups_csv)
    path = os.path.join(used_dir, "used_config.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(eff, f, sort_keys=False, allow_unicode=True)
    return path
