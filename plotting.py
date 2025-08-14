# plotting.py
from __future__ import annotations

import math
from typing import List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def write_markdown(out_df: pd.DataFrame, roles: List[int], path_md: str) -> None:
    tmp = out_df.sort_values(["Team", "Position", "Name"]).reset_index(drop=True)
    lines = []
    for team_id, g in tmp.groupby("Team"):
        lines.append(f"## Team {team_id}")
        lines.append("")
        lines.append("| Role | Name | MMR | Captain |")
        lines.append("|-----:|------|----:|:-------:|")
        for r in sorted(roles):
            row = g[g["Position"] == r].iloc[0]
            cap = "✅" if int(row["Captain"]) == 1 else ""
            lines.append(f"| {r} | {row['Name']} | {int(row['Skill'])} | {cap} |")
        mmrs = g["Skill"].to_numpy(dtype=float)
        avg_all = mmrs.mean()
        avg_core = g[g["Position"].isin([1, 2, 3])]["Skill"].mean()
        avg_support = g[g["Position"].isin([4, 5])]["Skill"].mean()
        lines.append("")
        lines.append(
            f"**Averages** — All: {avg_all:.1f} | Core(1–3): {avg_core:.1f} | Support(4–5): {avg_support:.1f}"
        )
        lines.append("")
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def plot_mmr_bars_per_team(out_df: pd.DataFrame, roles: List[int], out_path: str, dpi: int) -> None:
    teams = sorted(out_df["Team"].unique())
    T = len(teams)
    cols = min(4, T)
    rows = int(math.ceil(T / cols))

    fig_w = 4 * cols
    fig_h = 3 * rows
    fig = plt.figure(figsize=(fig_w, fig_h))

    for i, team_id in enumerate(teams, start=1):
        ax = fig.add_subplot(rows, cols, i)
        g = out_df[out_df["Team"] == team_id].sort_values("Position")
        xs = [str(int(r)) for r in g["Position"]]
        ys = g["Skill"].to_numpy(dtype=float)
        ax.bar(xs, ys)
        ax.set_title(f"Team {team_id}")
        ax.set_xlabel("Role")
        ax.set_ylabel("MMR")
        ax.set_ylim(0.95 * float(out_df["Skill"].min()), 1.05 * float(out_df["Skill"].max()))
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_avg_role_mmr_by_team(out_df: pd.DataFrame, roles: List[int], out_path: str, dpi: int) -> None:
    teams = sorted(out_df["Team"].unique())
    data = np.zeros((len(teams), len(roles)))
    for i, t in enumerate(teams):
        g = out_df[out_df["Team"] == t]
        for j, r in enumerate(sorted(roles)):
            val = float(g[g["Position"] == r]["Skill"])
            data[i, j] = val

    fig, ax = plt.subplots(figsize=(1.2 * len(roles) + 3, 0.6 * len(teams) + 3))
    im = ax.imshow(data, aspect="auto")
    ax.set_xticks(range(len(roles)))
    ax.set_xticklabels([str(r) for r in sorted(roles)])
    ax.set_yticks(range(len(teams)))
    ax.set_yticklabels([f"Team {t}" for t in teams])
    ax.set_xlabel("Role")
    ax.set_title("Average MMR per Role per Team")

    for i in range(len(teams)):
        for j in range(len(roles)):
            ax.text(j, i, f"{data[i,j]:.0f}", ha="center", va="center")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_team_reports(out_df: pd.DataFrame, roles: List[int], out_path: str, dpi: int) -> None:
    teams = sorted(out_df["Team"].unique())
    T = len(teams)
    cols = min(3, T)
    rows = int(math.ceil(T / cols))

    fig_w = 5 * cols
    fig_h = 3.6 * rows
    fig = plt.figure(figsize=(fig_w, fig_h))

    for i, team_id in enumerate(teams, start=1):
        ax = fig.add_subplot(rows, cols, i)
        g = out_df[out_df["Team"] == team_id].sort_values("Position")
        lines = [f"Team {team_id}", "-" * 18]
        for _, r in g.iterrows():
            cap = " (C)" if int(r["Captain"]) == 1 else ""
            lines.append(f"R{int(r['Position'])}: {r['Name']}{cap} — {int(r['Skill'])}")
        mmrs = g["Skill"].astype(float)
        avg_all = mmrs.mean()
        avg_core = g[g["Position"].isin([1, 2, 3])]["Skill"].mean()
        avg_support = g[g["Position"].isin([4, 5])]["Skill"].mean()
        lines.append("")
        lines.append(f"Avg: {avg_all:.1f}")
        if {1, 2, 3}.issubset(set(roles)):
            lines.append(f"Core (1–3): {avg_core:.1f}")
        if {4, 5}.issubset(set(roles)):
            lines.append(f"Support (4–5): {avg_support:.1f}")

        ax.axis("off")
        ax.text(0.02, 0.98, "\n".join(lines), va="top", ha="left", family="monospace")

    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
