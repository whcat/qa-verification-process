# -*- coding: utf-8 -*-
"""第五輪覆稽:v2 判準負對照(稽核方獨立實作,seed 與對方不同)
真實價格 × 各檔內重排三法人訊號,100 輪 × 6 檔,統計 v1/v1nw/v2 假陽性格數。
對方宣稱(seed=20260717, 100輪): v1 5.09 / v1nw 1.90 / v2 0.030 格/輪,v2 至少1格輪數 1%。
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

SCRATCH = os.path.dirname(os.path.abspath(__file__))
PROJ_PY = r"C:\Users\ray74\OneDrive\桌面\專案系列\Claud AI  Project\Stock analysis\py"
os.chdir(SCRATCH)
sys.path.insert(0, PROJ_PY)
import analyze_institutional_signal as ais

# 價格快取:load_price 每輪重讀 9~26MB CSV 太慢,先讀一次後 monkeypatch
_CACHE = {s: ais.load_price(s) for s in ais.PRICE_SOURCES}
ais.load_price = lambda s: _CACHE[s]

flows = pd.read_csv(ais.FLOWS_CSV, dtype={"Date": str, "symbol": str})
INST_COLS = ["foreign_net_K", "trust_net_K", "dealer_net_K"]

rng = np.random.default_rng(55555)   # 稽核方自訂 seed,刻意不同於對方
N_ITER = 100

v1c, v1nwc, v2c = [], [], []
for it in range(N_ITER):
    pf = flows.copy()
    for sym in pf["symbol"].unique():
        m = (pf["symbol"] == sym).to_numpy()
        for col in INST_COLS:
            pf.loc[m, col] = rng.permutation(pf.loc[m, col].to_numpy())
    c1 = c1nw = c2 = 0
    for symbol in ais.PRICE_SOURCES:
        res, _ = ais.analyze_symbol(symbol, pf)
        c1 += int(res["replicated"].sum())
        c1nw += int(res["replicated_nw"].sum())
        c2 += int(res["replicated_v2"].sum())
    v1c.append(c1); v1nwc.append(c1nw); v2c.append(c2)
    if (it + 1) % 25 == 0:
        print(f"...{it+1}/{N_ITER}  v1累計={sum(v1c)}  v2累計={sum(v2c)}", flush=True)

v1a, v2a = np.array(v1c), np.array(v2c)
print(f"\n=== 稽核方獨立負對照(seed=55555, {N_ITER}輪 × 6檔 × 36格) ===")
print(f"v1 replicated     平均 {v1a.mean():.2f} 格/輪 (max {v1a.max()})")
print(f"v1 replicated_nw  平均 {np.mean(v1nwc):.2f} 格/輪")
print(f"v2 replicated_v2  平均 {v2a.mean():.3f} 格/輪 (max {v2a.max()}, 至少1格輪數 {np.mean(v2a>0)*100:.0f}%)")
