# solver.py
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model


def build_and_solve(
    df: pd.DataFrame,
    roles: List[int],
    role_weights: Dict[int, float],
    num_teams: int,
    captain_policy: str,
    captain_hard: bool,
    conflict_weight: float,
    balance_weight: float,
    captain_weight: float,
    presets: Dict[str, int],
    random_seed: int,
) -> Tuple[pd.DataFrame, Dict]:
    """
    Returns (assignments_df, diagnostics)
    assignments_df includes a new 'Team' column with 1..num_teams
    diagnostics contains objective parts and feasibility notes.
    """
    rng = np.random.default_rng(random_seed)

    players = df["Name"].tolist()
    P = len(players)
    name_to_idx = {n: i for i, n in enumerate(players)}

    team_ids = list(range(num_teams))  # 0..T-1 internally
    roles = list(sorted(set(roles)))
    R = len(roles)

    skill = df["Skill"].to_numpy().astype(float)
    pos = df["Position"].to_numpy().astype(int)
    is_capt = df["Captain"].to_numpy().astype(int)

    weight_by_role = np.array([role_weights.get(r, 1.0) for r in pos], dtype=float)
    weighted_skill = skill * weight_by_role

    # Directed "avoid" pairs (A avoids B)
    avoid_pairs = []
    for _, row in df.iterrows():
        a = row["Name"]
        b = row["Avoid"]
        if b is not None and b in name_to_idx:
            avoid_pairs.append((name_to_idx[a], name_to_idx[b]))

    model = cp_model.CpModel()

    # Decision vars
    x = {(p, t): model.NewBoolVar(f"x_p{p}_t{t}") for p in range(P) for t in team_ids}

    # Each player exactly one team
    for p in range(P):
        model.Add(sum(x[(p, t)] for t in team_ids) == 1)

    # For each team and role: exactly one player with that role
    for t in team_ids:
        for r in roles:
            model.Add(sum(x[(p, t)] for p in range(P) if pos[p] == r) == 1)

    # Presets (team indexes in presets are 1-based)
    for name, team1 in (presets or {}).items():
        if name not in name_to_idx:
            raise ValueError(f"Preset player '{name}' not found in signups.")
        if not (1 <= int(team1) <= num_teams):
            raise ValueError(f"Preset team index for '{name}' out of range 1..{num_teams}.")
        p = name_to_idx[name]
        t = int(team1) - 1
        for tt in team_ids:
            model.Add(x[(p, tt)] == (1 if tt == t else 0))

    # Team weighted scores (scaled to int)
    SCALE = 100
    scaled_ws = np.round(weighted_skill * SCALE).astype(int)

    s = {t: model.NewIntVar(0, int(1e9), f"s_t{t}") for t in team_ids}
    for t in team_ids:
        model.Add(s[t] == sum(int(scaled_ws[p]) * x[(p, t)] for p in range(P)))

    total_score = int(np.sum(scaled_ws))
    target = total_score // num_teams

    d = {t: model.NewIntVar(0, int(1e9), f"d_t{t}") for t in team_ids}
    for t in team_ids:
        diff = model.NewIntVar(-int(1e9), int(1e9), f"diff_t{t}")
        model.Add(diff == s[t] - int(target))
        model.Add(d[t] >= diff)
        model.Add(d[t] >= -diff)

    # Conflicts
    y = {}
    conflict_terms = []
    for (pa, pb) in avoid_pairs:
        for t in team_ids:
            var = model.NewBoolVar(f"y_pa{pa}_pb{pb}_t{t}")
            y[(pa, pb, t)] = var
            model.Add(var <= x[(pa, t)])
            model.Add(var <= x[(pb, t)])
            model.Add(var >= x[(pa, t)] + x[(pb, t)] - 1)
            conflict_terms.append(var)

    # Captain policy
    c_t = {t: model.NewIntVar(0, R, f"captains_t{t}") for t in team_ids}
    for t in team_ids:
        model.Add(c_t[t] == sum(is_capt[p] * x[(p, t)] for p in range(P)))

    captain_penalty_terms = []
    num_captains = int(np.sum(is_capt))
    feasibility_warnings = []

    if captain_policy not in ("none", "at_least_one", "separate"):
        raise ValueError("captain_policy must be one of: none, at_least_one, separate")

    if captain_policy == "at_least_one":
        if captain_hard and num_captains < num_teams:
            feasibility_warnings.append(
                "Not enough captains for 'at_least_one' hard constraint; downgrading to soft penalty."
            )
            captain_hard = False
        if captain_hard:
            for t in team_ids:
                model.Add(c_t[t] >= 1)
        else:
            for t in team_ids:
                m_t = model.NewIntVar(0, 1, f"capt_min_violation_t{t}")
                model.Add(m_t >= 1 - c_t[t])
                captain_penalty_terms.append(m_t)

    elif captain_policy == "separate":
        if captain_hard and num_captains > num_teams:
            feasibility_warnings.append(
                "Too many captains for 'separate' hard constraint; downgrading to soft penalty."
            )
            captain_hard = False
        if captain_hard:
            for t in team_ids:
                model.Add(c_t[t] <= 1)
        else:
            for t in team_ids:
                k_t = model.NewIntVar(0, R, f"capt_max_violation_t{t}")
                model.Add(k_t >= c_t[t] - 1)
                captain_penalty_terms.append(k_t)

    # Objective
    obj_terms = []
    if balance_weight != 0:
        obj_terms.append(balance_weight * sum(d[t] for t in team_ids))
    if conflict_weight != 0 and conflict_terms:
        obj_terms.append(int(conflict_weight * SCALE) * sum(conflict_terms))
    if captain_weight != 0 and captain_penalty_terms:
        obj_terms.append(int(captain_weight * SCALE) * sum(captain_penalty_terms))
    model.Minimize(sum(obj_terms))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.random_seed = random_seed
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No feasible assignment found. Try relaxing constraints or presets.")

    # Extract assignment
    team_for_p = {}
    for p in range(P):
        for t in team_ids:
            if solver.Value(x[(p, t)]) == 1:
                team_for_p[p] = t + 1
                break

    out = df.copy()
    out["Team"] = [team_for_p[p] for p in range(P)]

    team_scores = {t + 1: solver.Value(s[t]) / SCALE for t in team_ids}
    devs = {t + 1: solver.Value(d[t]) / SCALE for t in team_ids}
    captain_counts = {t + 1: solver.Value(c_t[t]) for t in team_ids}

    diagnostics = {
        "status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        "team_scores": team_scores,
        "target_score": target / SCALE,
        "deviations": devs,
        "captain_counts": captain_counts,
        "num_captains": num_captains,
        "feasibility_warnings": feasibility_warnings,
    }

    return out, diagnostics
