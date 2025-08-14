# main.py
from __future__ import annotations

import os


from data_prep import load_config, prepare_data, infer_num_teams, save_effective_config
from solver import build_and_solve
from plotting import (
    write_markdown,
    plot_mmr_bars_per_team,
    plot_avg_role_mmr_by_team,
    plot_team_reports,
)

# ---------------------------------------------------------------------
# Define your paths here (no CLI args)
# ---------------------------------------------------------------------
CONFIG_PATH = "./config.yaml"     # <— set this to your YAML config path
SIGNUPS_PATH = "./signups.csv"    # <— set this to your signups.csv path
# ---------------------------------------------------------------------


def run():
    print("🚀 Starting Team Balancer (module layout)…")

    # Load configuration
    print("📂 Loading configuration file…")
    cfg = load_config(CONFIG_PATH)
    print("✅ Configuration loaded.")

    # Prepare signup data
    print("📄 Reading and validating signup data…")
    roles = list(cfg["roles"])
    df = prepare_data(SIGNUPS_PATH, roles)
    print(f"✅ Signup data loaded: {len(df)} players found.")

    # Determine number of teams
    print("🤔 Determining number of teams…")
    num_teams = infer_num_teams(df, roles, cfg.get("num_teams"))
    print(f"✅ Number of teams set to: {num_teams}")

    # Solve team assignment
    print("🧮 Building and solving team assignment…")
    out_df, diag = build_and_solve(
        df=df,
        roles=roles,
        role_weights=cfg["role_weights"],
        num_teams=num_teams,
        captain_policy=cfg["captain_policy"],
        captain_hard=bool(cfg["captain_hard"]),
        conflict_weight=float(cfg["conflict_weight"]),
        balance_weight=float(cfg["balance_weight"]),
        captain_weight=float(cfg["captain_weight"]),
        presets={str(k): int(v) for k, v in (cfg.get("presets") or {}).items()},
        random_seed=int(cfg["random_seed"]),
    )
    print("✅ Solver finished.")

    # Output directory
    print("📁 Creating output directory…")
    run_dir = os.path.join(cfg["output_root"], cfg["run_name"])
    os.makedirs(run_dir, exist_ok=True)
    print(f"✅ Output directory ready: {run_dir}")

    # Save effective config (records absolute signups path)
    print("💾 Saving configuration used…")
    used_yaml = save_effective_config(cfg, run_dir, SIGNUPS_PATH)
    print(f"   → Saved YAML: {used_yaml}")

    # Markdown roster
    print("📝 Writing Markdown roster…")
    md_path = os.path.join(run_dir, "teams.md")
    write_markdown(out_df, roles, md_path)
    print(f"   → Saved Markdown: {md_path}")

    # CSV
    print("📊 Saving CSV assignments…")
    csv_path = os.path.join(run_dir, "assignments.csv")
    out_df.to_csv(csv_path, index=False)
    print(f"   → Saved CSV: {csv_path}")

    # Plots
    print("📈 Creating plots…")
    dpi = int(cfg["plot_dpi"])
    bars_path = os.path.join(run_dir, "mmr_bars_per_team.png")
    plot_mmr_bars_per_team(out_df, roles, bars_path, dpi=dpi)
    print(f"   → Saved: {bars_path}")

    heatmap_path = os.path.join(run_dir, "avg_role_mmr_by_team.png")
    plot_avg_role_mmr_by_team(out_df, roles, heatmap_path, dpi=dpi)
    print(f"   → Saved: {heatmap_path}")

    report_path = os.path.join(run_dir, "team_reports.png")
    plot_team_reports(out_df, roles, report_path, dpi=dpi)
    print(f"   → Saved: {report_path}")

    # Console summary
    print("\n=== ✅ Team Balancer Complete ===")
    print(f"Solver Status: {diag['status']}")
    if diag["feasibility_warnings"]:
        for w in diag["feasibility_warnings"]:
            print(f"⚠️  {w}")
    print(f"Target weighted score: {diag['target_score']:.2f}")
    for t in sorted(diag["team_scores"]):
        s = diag["team_scores"][t]
        dev = diag["deviations"][t]
        caps = diag["captain_counts"][t]
        print(f"  Team {t}: score={s:.2f} (dev={dev:.2f}), captains={caps}")
    print("\n📂 All outputs saved in:", run_dir)


if __name__ == "__main__":
    run()
