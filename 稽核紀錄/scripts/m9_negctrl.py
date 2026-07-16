# -*- coding: utf-8 -*-
"""M9 負對照 — 真實價格 + 訊號跨日期重排（打斷時序、保留分布），測管線假陽性。

與 M10 的 rho=0 條件互補：M10 用合成價格（常態報酬），本測試用**真實價格**
（厚尾報酬）＋真實訊號分布，只打斷「訊號→未來報酬」的時序對應。
管線若在此輸入下仍宣告 replicated → 洩漏或機制性偏誤。

被稽核專案唯讀；import 真實 analyze_symbol()。
"""
import os
import sys
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJ = r"C:\Users\ray74\OneDrive\桌面\專案系列\Claud AI  Project\Stock analysis"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJ, "py"))

os.chdir(PROJ)
import analyze_institutional_signal as M   # noqa: E402
# 快取真實價格，避免每次 rep 重讀檔；同時保證 2330 走既有快取檔而非網路
_PRICE_CACHE = {s: M.load_price(s) for s in M.PRICE_SOURCES}
os.chdir(SCRATCH)
M.load_price = lambda s: _PRICE_CACHE[s]

NREP = int(os.environ.get("NREP", "100"))
INST_COLS = ["foreign_net_K", "trust_net_K", "dealer_net_K"]


def main():
    flows = pd.read_csv(os.path.join(PROJ, "output/institutional_flows_3y.csv"),
                        dtype={"Date": str, "symbol": str})
    rng = np.random.default_rng(20260716)
    symbols = list(M.PRICE_SOURCES)
    print(f"M9 負對照：真實價格 × 重排訊號，{NREP} 次重複 × {len(symbols)} 檔 × 36 格\n")
    print(f"{'symbol':<8}{'FDR顯著/36 均值':>16}{'replicated 均值':>17}"
          f"{'replicated_nw 均值':>19}{'任一格rep的比例':>17}")
    print("-" * 78)
    grand_rep = grand_cells = 0
    for sym in symbols:
        f_sym = flows[flows["symbol"] == sym].reset_index(drop=True)
        n_fdr, n_rep, n_nw, any_rep = [], [], [], 0
        for _ in range(NREP):
            f_perm = f_sym.copy()
            for c in INST_COLS:   # 各法人獨立重排：打斷時序，保留分布
                f_perm[c] = rng.permutation(f_perm[c].to_numpy())
            out, _ = M.analyze_symbol(sym, f_perm)
            r = int(out["replicated"].sum())
            n_fdr.append(int(out["train_sig_fdr"].sum()))
            n_rep.append(r)
            n_nw.append(int(out["replicated_nw"].sum()))
            any_rep += r > 0
        grand_rep += sum(n_rep)
        grand_cells += NREP * 36
        print(f"{sym:<8}{np.mean(n_fdr):>16.2f}{np.mean(n_rep):>17.3f}"
              f"{np.mean(n_nw):>19.3f}{any_rep / NREP:>16.1%}")
    print("-" * 78)
    print(f"全體：replicated 假陽性率 = {grand_rep}/{grand_cells} "
          f"= {grand_rep / grand_cells:.4%}（每格）")
    print("判讀：管線名目每格假陽性應遠低於 5%；若接近或超過 → 洩漏/機制性偏誤")


if __name__ == "__main__":
    main()
