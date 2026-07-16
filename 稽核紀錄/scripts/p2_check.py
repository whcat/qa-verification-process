# -*- coding: utf-8 -*-
"""P2（R04/R05 均線濾網）方法學檢核 — 稽核方腳本，唯讀讀取被稽核專案資料。

檢核：
  M8 選擇性報告：文件引用「大盤 MA20 訓練期」，但 CSV 有 33 標的 → 大盤是不是被挑出來的？
  M6/M3 顯著性：Sharpe 0.84→1.16 的差異有沒有超出雜訊？（文件全無檢定/CI）
  M11 擾動：MA 窗格 10~40、split ±20 交易日，結論是否存活
"""
import os
import sys
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJ = r"C:\Users\ray74\OneDrive\桌面\專案系列\Claud AI  Project\Stock analysis"
sys.path.insert(0, os.path.join(PROJ, "py"))
os.chdir(PROJ)
import analyze_expert_rule_R04_R05 as R    # 被測管線本體（load_prices/backtest_one/perf_stats）
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SPLIT = 20250703
BENCH = "大盤"


def sharpe(r):
    r = pd.Series(r).dropna()
    if len(r) < 20 or r.std() == 0:
        return np.nan
    return r.mean() * 252 / (r.std() * np.sqrt(252))


def main():
    cwd = os.getcwd()
    os.chdir(PROJ)              # load_prices 用相對路徑；純讀取，不呼叫會寫檔的 main()
    try:
        prices = R.load_prices()
    finally:
        os.chdir(cwd)
    print(f"標的數：{len(prices.columns)}\n")

    # ── M8：訓練期跨標的勝率（文件只引用「大盤」一個標的）──
    print("=== M8 選擇性報告：訓練期 MA20 濾網，33 標的各自 Sharpe 改善？ ===")
    for label, w in (("R05_MA20", 20), ("R04_MA240", 240)):
        wins, diffs, bench_diff = 0, [], None
        for name in prices.columns:
            df = R.backtest_one(prices[name], w)
            sub = df[df.index < SPLIT]
            if len(sub) < 60:
                continue
            d = sharpe(sub["strat_ret"]) - sharpe(sub["ret"])
            if np.isnan(d):
                continue
            diffs.append(d)
            wins += d > 0
            if name == BENCH:
                bench_diff = d
        diffs = np.array(diffs)
        rank = (diffs > bench_diff).sum() + 1 if bench_diff is not None else np.nan
        print(f"{label} 訓練期：Sharpe改善者 {wins}/{len(diffs)} ({wins/len(diffs):.0%})  "
              f"中位數改善 {np.median(diffs):+.3f}")
        print(f"   大盤改善 {bench_diff:+.3f} → 在 {len(diffs)} 標的中排名第 {rank} "
              f"(前 {rank/len(diffs):.0%})")
    print()

    # ── M6/M3：大盤 MA20 訓練期 Sharpe 差的顯著性（循環區塊拔靴，保留自相關）──
    print("=== M6/M3 顯著性：大盤 MA20 訓練期 Sharpe 改善 0.84→1.16 是雜訊嗎？ ===")
    df = R.backtest_one(prices[BENCH], 20)
    sub = df[df.index < SPLIT].dropna(subset=["ret", "strat_ret"])
    bh, fl = sub["ret"].to_numpy(), sub["strat_ret"].to_numpy()
    obs = sharpe(fl) - sharpe(bh)
    print(f"實測：buy&hold Sharpe={sharpe(bh):.3f}  濾網 Sharpe={sharpe(fl):.3f}  差={obs:+.3f}")

    rng = np.random.default_rng(20260716)
    n, L = len(bh), 20                       # 區塊長 20 日 ≈ MA 窗格
    boot = []
    for _ in range(5000):
        idx = np.concatenate([np.arange(s, s + L) % n
                              for s in rng.integers(0, n, n // L + 1)])[:n]
        boot.append(sharpe(fl[idx]) - sharpe(bh[idx]))
    boot = np.array(boot)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"循環區塊拔靴 95% CI：[{lo:+.3f}, {hi:+.3f}]  "
          f"→ {'含 0，無法排除雜訊' if lo <= 0 <= hi else '不含 0'}")

    # 安慰劑：隨機進出場但在場比例相同 → 純粹「少曝險」能不能複製這個改善？
    in_mkt = sub["position"].mean()
    plc = []
    for _ in range(2000):
        pos = (rng.random(n) < in_mkt).astype(float)
        plc.append(sharpe(pos * bh) - sharpe(bh))
    plc = np.array(plc)
    pv = (plc >= obs).mean()
    print(f"安慰劑（隨機在場 {in_mkt:.0%} 時間，非 MA 訊號）：中位改善 {np.median(plc):+.3f}，"
          f"P(隨機 ≥ 實測) = {pv:.3f}")
    print()

    # ── M11 擾動：MA 窗格 ──
    print("=== M11 擾動：大盤訓練期 Sharpe 改善 vs MA 窗格 ===")
    out = []
    for w in (5, 10, 15, 20, 25, 30, 40, 60):
        d2 = R.backtest_one(prices[BENCH], w)
        s = d2[d2.index < SPLIT]
        out.append((w, sharpe(s["strat_ret"]) - sharpe(s["ret"])))
    print("  MA窗格: " + "  ".join(f"{w:>3}" for w, _ in out))
    print("  改善  : " + "  ".join(f"{d:>+.2f}" for _, d in out))


if __name__ == "__main__":
    main()
