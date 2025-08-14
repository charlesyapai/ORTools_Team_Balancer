# Team Balancer — README

A role-constrained, captain-aware, conflict-avoidant team assignment solver.
It reads a signups CSV and a YAML config, then assigns players to teams so that:

* Each team has exactly **one player per role** (e.g., roles 1–5).
* Teams are **balanced by weighted MMR** (optional per-role weights).
* **Captain policy** can be enforced or encouraged (at least one per team or spread captains out).
* **Avoid-pair** preferences are respected where possible.
* **Presets** allow pinning specific players to specific teams.
* Produces a Markdown roster, a CSV with team labels, and PNG reports.

---

## Quick start

1. **Download the code** (place `main.py` and your YAML/CSV in a folder).
2. **Create a conda environment** (ORTools can be picky about old deps):

   ```bash
   conda create -n team_balancer python=3.10 -y
   conda activate team_balancer
   pip install --upgrade pip
   pip install pandas numpy pyyaml matplotlib ortools
   ```
3. **Run it**:

   ```bash
   python main.py --signups signups.csv --config config.yaml
   ```

The solver creates an output folder (e.g., `./outputs/<run_name>/`) containing all artifacts for the run.

---

## Input formats

### Signups CSV (columns must match exactly)

* **Name** — string (unique)
* **Skill** — numeric (recommended range 5000–9000)
* **Position** — integer role ID (e.g., 1–5)
* **Captain** — 0/1 flag
* **Avoid** — string with a **Name** value to avoid (or empty/NaN)

Example:

```csv
Name,Skill,Position,Captain,Avoid
Alice,7800,1,1,Bob
Bob,7600,2,0,Alice
Carol,8200,3,1,
...
```

### Config YAML (fully configurable; example)

```yaml
run_name: "draft_aug"
output_root: "./outputs"

num_teams: 8            # If null, inferred from data: must have equal count per role
roles: [1, 2, 3, 4, 5]

# Per-role multipliers for balancing weighted team MMR
role_weights:
  1: 1.0
  2: 1.0
  3: 1.0
  4: 1.0
  5: 1.0

# Captain handling ("none" | "at_least_one" | "separate")
captain_policy: "at_least_one"
captain_hard: false      # true=enforce as hard constraint (only if feasible)
captain_weight: 5.0      # penalty when not hard

# Objective weights
balance_weight: 1.0      # team MMR balance (sum of abs deviations)
conflict_weight: 1.0     # penalize avoid-pairs placed together

# Pin players to teams (1-based team index)
presets:
  # "Player A": 1
  # "Player B": 3

random_seed: 42
plot_dpi: 140
```

> **Feasibility requirements:**
>
> * For each role in `roles`, the CSV must contain **exactly `num_teams` players** with that role.
> * Total players must equal `num_teams * len(roles)`.
> * Names must be unique.
> * If `captain_hard: true` is infeasible (e.g., fewer captains than teams for “at\_least\_one”), the solver automatically **softens** it and prints a warning.

---

## What it produces

Inside `./outputs/<run_name>/`:

1. `used_config.yaml` — the exact config used for this run (for reproducibility).
2. `teams.md` — Markdown roster per team (roles, names, MMR, captain marks + averages).
3. `assignments.csv` — original CSV plus a `Team` column.
4. `mmr_bars_per_team.png` — bars of per-player MMR by role for each team.
5. `avg_role_mmr_by_team.png` — heatmap of role MMR per team.
6. `team_reports.png` — compact boards with each team’s roster, overall avg, **Core(1–3)** avg, and **Support(4–5)** avg.

---

## How the solver works (math)

The solver uses **OR-Tools CP-SAT** (mixed integer model).

**Decision variables**

* $x_{p,t} \in \{0,1\}$: player $p$ assigned to team $t$.

**Role coverage constraints**

* For each team $t$ and each role $r$:
  $\sum_{p:\,\text{role}(p)=r} x_{p,t} = 1$

**One team per player**

* For each player $p$:
  $\sum_{t} x_{p,t} = 1$

**Presets (optional)**

* If player $p$ is preset to team $\hat{t}$:
  $x_{p,\hat{t}} = 1,\; x_{p,t\neq\hat{t}} = 0$

**Weighted team score**
Each player has skill $s_p$ and role weight $w_{\text{role}(p)}$.
Team $t$ score: $S_t = \sum_{p} (w_{\text{role}(p)} s_p) \, x_{p,t}$

**Balance target**
Let $\bar{S} = \frac{1}{T} \sum_t S_t$ be the average team score.
We minimize the **sum of absolute deviations**: $\sum_t |S_t - \bar{S}|$.
This is linearized with auxiliary variables $d_t \ge |S_t - \bar{S}|$.

**Avoid-pair penalty**
For every directed avoid pair $(a \to b)$ and team $t$, introduce $y_{a,b,t}\in\{0,1\}$ with:

* $y_{a,b,t} \le x_{a,t}$, $y_{a,b,t} \le x_{b,t}$,
* $y_{a,b,t} \ge x_{a,t} + x_{b,t} - 1$.
  Penalty adds $\lambda_{\text{conflict}} \sum_{a\to b,t} y_{a,b,t}$.

**Captain policy** (soft or hard)
Let $C_t = \sum_p \text{captain}_p \, x_{p,t}$.

* `at_least_one` hard: $C_t \ge 1$. Soft: penalize $m_t = \max(0, 1 - C_t)$.
* `separate` hard: $C_t \le 1$. Soft: penalize $k_t = \max(0, C_t - 1)$.

**Objective**

$$
\min \quad
\alpha \sum_t d_t
\;+\;
\beta \sum_{a\to b,t} y_{a,b,t}
\;+\;
\gamma \sum_t \text{captain\_violation}_t
$$

where $\alpha=$ `balance_weight`, $\beta=$ `conflict_weight`, $\gamma=$ `captain_weight`.

---

## Tuning & performance

### ⚠️ CPU usage (important)

CP-SAT **parallelizes aggressively** and can peg all CPU cores. If you’re on a shared or low-power machine, **dial it down**:

In `main.py`, look for the solver parameters (near the end of the model build):

```python
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60.0
solver.parameters.random_seed = random_seed
solver.parameters.num_search_workers = 8   # <- change this
```

* Set `num_search_workers = 1` to run single-threaded (lowest CPU).
* Reduce `max_time_in_seconds` (e.g., 10–30) to cap runtime and CPU time.
* (Optional) You can further limit solver aggressiveness:

  ```python
  solver.parameters.cp_model_presolve = True  # default; keep on
  solver.parameters.linearization_level = 1   # 0..2; lower can be lighter
  # solver.parameters.search_branching = cp_model.FIXED_SEARCH  # advanced; usually leave default
  ```

**Tip:** If you routinely need to tune CPU per run, expose `num_search_workers` and `max_time_in_seconds` in the YAML and pass them into the solver (simple to add next to other config keys).

### Solver tips

* Start with `captain_hard: false` (soft penalties) to ensure feasibility; then try `true`.
* If you get infeasible, check:

  * equal counts per role (must be exactly `num_teams` for each role),
  * presets don’t collide (e.g., two role-1 players preset to the same team),
  * captain hard constraints are actually possible (enough/few enough captains).
* For consistent results, keep `random_seed` fixed.

---

## Typical workflows

### A) Neutral weights, spread captains, penalize conflicts

```yaml
role_weights: {1:1, 2:1, 3:1, 4:1, 5:1}
captain_policy: "separate"
captain_hard: false
balance_weight: 1.0
conflict_weight: 1.0
```

### B) Core roles weighted higher

```yaml
role_weights: {1:1.2, 2:1.2, 3:1.2, 4:1.0, 5:1.0}
```

### C) Require a captain per team (if feasible)

```yaml
captain_policy: "at_least_one"
captain_hard: true
```

---

## Output interpretation

* **`teams.md`**: human-readable rosters per team, with per-team averages and ✓ for captains.
* **`assignments.csv`**: programmatic artifact if you need to post-process or audit.
* **`mmr_bars_per_team.png`**: quick glance of role MMR spread within each team.
* **`avg_role_mmr_by_team.png`**: check that each role’s strength is distributed fairly.
* **`team_reports.png`**: “presentation board” with overall and Core/Support averages.

---

## Troubleshooting

* **“No feasible assignment found”**

  * Check per-role counts match `num_teams`.
  * Remove/relax presets that collide.
  * Set `captain_hard: false`.
  * Temporarily set `conflict_weight: 0` to see if avoid pairs are the blocker.

* **ORTools install issues**

  * Ensure Python ≥ 3.8 (we recommend 3.10 in the conda step).
  * Upgrade pip: `pip install --upgrade pip` before `pip install ortools`.
  * On Apple Silicon/Windows, keep to the conda+pip combo above.

* **High CPU usage**

  * Lower `num_search_workers` to `1`.
  * Lower `max_time_in_seconds`.
  * Run fewer experiments in parallel.

---

## Reproducibility

* Every run saves `used_config.yaml` with absolute path to the signups file and all effective parameters.
* Keep the same CSV, YAML, and `random_seed` to reproduce the same result (CP-SAT may still find equivalent optima with different assignments; if you need strict determinism, set `num_search_workers: 1` and keep the seed fixed).

