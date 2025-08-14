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
   <!-- pip install --upgrade pip -->
   conda install pandas numpy pyyaml matplotlib ortools
   ```
3. **Run it**:

   ```bash
   python main.py
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

## How the solver works (math, explained)

This solver uses **[OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver)**, which is a constraint programming solver capable of handling binary and integer optimization problems.

We represent the assignment of players to teams with **binary decision variables**:

* **Assignment variable:**
  $x_{p,t} = 1$ if player **p** is assigned to team **t**,
  $x_{p,t} = 0$ otherwise.

---

### 1. Constraints

#### **a) One player per role per team**

For each **team** $t$ and **role** $r$:

$$
\sum_{\text{player } p \text{ with role } r} x_{p,t} = 1
$$

This means each team must have **exactly one** player for every role.

---

#### **b) Each player on exactly one team**

For each player $p$:

$$
\sum_{\text{all teams } t} x_{p,t} = 1
$$

No player can be in multiple teams or left unassigned.

---

#### **c) Preset placements (optional)**

If the config forces player $p$ into a fixed team $t^{\ast}$ (“team star” means a specific chosen team):

$$
x_{p,\,t^{\ast}} = 1 \quad\text{and}\quad x_{p,\,t} = 0 \ \forall\ t \neq t^{\ast}
$$


---

### 2. Weighted team scores

Each player has:

* **Skill rating**: $s_p$
* **Role weight** (from YAML config): $w_{\text{role}(p)}$

The **weighted team score** is:

$$
S_t = \sum_{\text{all players } p} \big( w_{\text{role}(p)} \cdot s_p \big) \cdot x_{p,t}
$$

---

### 3. Balancing the teams

We compute the **target score**:

$$
\bar{S} = \frac{1}{T} \sum_{t=1}^T S_t
$$

We try to make every team’s score **as close as possible** to $\bar{S}$.
This is done by minimizing the **sum of absolute deviations**:

$$
\sum_{t=1}^T \left| S_t - \bar{S} \right|
$$

In CP-SAT, absolute values are handled with **extra variables** $d_t$ such that:

$$
d_t \ge S_t - \bar{S}, \quad d_t \ge \bar{S} - S_t
$$

---

### 4. Avoid-pair penalties

Some players don’t want to be on the same team.
For every “avoid” request $a \to b$ and team $t$, we define:

* $y_{a,b,t} = 1$ if both **a** and **b** are in team $t$, else $0$.

This is linked to $x$ by:

$$
y_{a,b,t} \le x_{a,t}, \quad
y_{a,b,t} \le x_{b,t}, \quad
y_{a,b,t} \ge x_{a,t} + x_{b,t} - 1
$$

We penalize these cases by adding:

$$
\lambda_{\text{conflict}} \sum_{a\to b,t} y_{a,b,t}
$$

---

### 5. Captain policy

Let:

$$
C_t = \sum_{\text{all players } p} \text{captain}_p \cdot x_{p,t}
$$

Depending on config:

* **At least one captain per team**: $C_t \ge 1$ (hard) or penalize $\max(0, 1 - C_t)$ (soft).
* **Separate captains**: $C_t \le 1$ (hard) or penalize $\max(0, C_t - 1)$ (soft).

---

### 6. Objective function

We combine all goals into **one number to minimize**:

$$
\text{Objective} =
\alpha \cdot \sum_{t} d_t
\;+\;
\beta \cdot \sum_{a\to b,t} y_{a,b,t}
\;+\;
\gamma \cdot \sum_{t} \text{CaptainViolation}_t
$$

Where:

* $\alpha$ = `balance_weight` from YAML
* $\beta$ = `conflict_weight` from YAML
* $\gamma$ = `captain_weight` from YAML

By tuning these weights, you control how much the solver prioritizes **balance**, **avoiding conflicts**, and **captain rules**.



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






