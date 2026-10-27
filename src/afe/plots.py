"""Grafiken für den Bericht (PNG in output/figures/)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

COLORS = {"ML": "#502479", "OP": "#D50006"}  # FFHS-Farben
plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})


def boxplots(visits: pd.DataFrame, metrics: dict[str, str], out: Path) -> Path:
    cols = [c for c in metrics if c in visits]
    n = len(cols)
    ncol = 4
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 2.6, nrow * 2.6))
    axes = axes.ravel()
    for ax, col in zip(axes, cols):
        data = [visits.loc[visits["variant"] == v, col].dropna() for v in ("ML", "OP")]
        bp = ax.boxplot(data, tick_labels=[f"ML\nn={len(data[0])}", f"OP\nn={len(data[1])}"], patch_artist=True, widths=0.5)
        for patch, v in zip(bp["boxes"], ("ML", "OP")):
            patch.set_facecolor(COLORS[v])
            patch.set_alpha(0.35)
        for i, d in enumerate(data, 1):
            ax.scatter([i] * len(d), d, s=8, color="black", alpha=0.6, zorder=3)
        ax.set_title(metrics[col], fontsize=9)
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle("Maus-Kennzahlen nach Variante (eingeschlossene Besuche)")
    fig.tight_layout()
    path = out / "kennzahlen_varianten.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def aoi_hover_map(ev: pd.DataFrame, aoi_col: str, out: Path, title: str) -> Path | None:
    """Mauspositionen innerhalb des AOI-Elements (Element-Koordinaten 0..2000)."""
    m = ev[(ev[aoi_col]) & ev["event_type"].isin((1, 2))]
    if m.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(6, 4), sharey=True)
    for ax, v in zip(axes, ("ML", "OP")):
        d = m[m["variant"] == v]
        ax.hexbin(d["x"], d["y"], gridsize=15, extent=(0, 2000, 0, 2000), cmap="magma_r", mincnt=1)
        ax.set_xlim(0, 2000)
        ax.set_ylim(2000, 0)
        ax.set_title(f"{v} (n Ereignisse={len(d)})")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(title)
    fig.tight_layout()
    path = out / f"{aoi_col}_hovermap.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def page_paths(pv: pd.DataFrame, visits: pd.DataFrame, out: Path) -> Path:
    """Seitenfolge pro Besuch (Menüversion): wie navigieren die Teilnehmenden?"""
    inc = visits.loc[visits["included"] & visits["variant"].eq("ML"), "idvisit"]
    d = pv[pv["idvisit"].isin(inc)]
    pages = sorted(d["page"].unique(), key=lambda p: (p != "startseite", p == "kontakt", p))
    ypos = {p: i for i, p in enumerate(pages)}
    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.4 * len(pages) + 1)))
    for i, (v, g) in enumerate(d.groupby("idvisit")):
        ax.plot(g["pv_index"], g["page"].map(ypos) + (i % 7 - 3) * 0.04, marker="o", ms=3, lw=0.8, alpha=0.6)
    ax.set_yticks(range(len(pages)), pages)
    ax.set_xlabel("Seitenaufruf Nr.")
    ax.set_title(f"Navigationspfade Menüversion (n={d['idvisit'].nunique()} Besuche)")
    fig.tight_layout()
    path = out / "navigationspfade_ml.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def image_usage(summary: pd.DataFrame, out: Path) -> Path | None:
    """Anteil Besuche, die ein Bild überfahren bzw. angeklickt haben, je Variante."""
    if summary.empty:
        return None
    order = (summary.groupby("image")["anteil_ueberfahren"].mean().sort_values().index.tolist())
    fig, axes = plt.subplots(1, 2, figsize=(9, 0.45 * len(order) + 1.5), sharey=True)
    for ax, col, title in zip(axes, ["anteil_ueberfahren", "anteil_angeklickt"], ["überfahren", "angeklickt (Vergrösserung)"]):
        for i, v in enumerate(("ML", "OP")):
            d = summary[summary["variant"] == v].set_index("image").reindex(order)
            y = [k + (i - 0.5) * 0.38 for k in range(len(order))]
            ax.barh(y, d[col].fillna(0), height=0.36, color=COLORS[v], alpha=0.75, label=v)
        ax.set_yticks(range(len(order)), [o.replace("-Mira-Caduff", "") for o in order])
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.set_title(f"Anteil Besuche: {title}")
    axes[0].legend(loc="lower right")
    fig.tight_layout()
    path = out / "bilder_nutzung.png"
    fig.savefig(path)
    plt.close(fig)
    return path
