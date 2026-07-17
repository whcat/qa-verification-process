# -*- coding: utf-8 -*-
"""比對:對方 repo 簽入的 institutional_signal_train_test.csv vs 稽核方暫存區新算版本"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
import numpy as np

THEIRS = r"C:\Users\ray74\OneDrive\桌面\專案系列\Claud AI  Project\Stock analysis\output\institutional_signal_train_test.csv"
MINE = r"C:\Users\ray74\AppData\Local\Temp\claude\C--Users-ray74-OneDrive---------Claud-AI--Project-------\d6839f90-d22a-4526-944a-a8608c362df4\scratchpad\round5\output\institutional_signal_train_test.csv"

a = pd.read_csv(THEIRS)
b = pd.read_csv(MINE)
print("theirs shape:", a.shape, " mine shape:", b.shape)
print("columns equal:", list(a.columns) == list(b.columns))
if list(a.columns) != list(b.columns):
    print("theirs:", list(a.columns))
    print("mine:  ", list(b.columns))

key = ["symbol", "inst", "agg", "horizon_d"]
a = a.sort_values(key).reset_index(drop=True)
b = b.sort_values(key).reset_index(drop=True)
diffs = 0
for c in a.columns:
    if c in key:
        same = (a[c].astype(str) == b[c].astype(str)).all()
    else:
        va, vb = a[c], b[c]
        if va.dtype == object or vb.dtype == object:
            same = (va.astype(str) == vb.astype(str)).all()
        else:
            same = np.allclose(va.astype(float), vb.astype(float), rtol=1e-9, atol=1e-12, equal_nan=True)
    if not same:
        diffs += 1
        mask = ~((a[c].astype(str) == b[c].astype(str)) | (a[c].isna() & b[c].isna()))
        print(f"COLUMN DIFF: {c}  ({int(mask.sum())} rows)")
        print(pd.concat([a.loc[mask, key + [c]].head(5).add_suffix("_theirs"),
                         b.loc[mask, [c]].head(5).add_suffix("_mine")], axis=1).to_string())
print("\n=> 完全一致" if diffs == 0 else f"\n=> {diffs} 欄不一致")
