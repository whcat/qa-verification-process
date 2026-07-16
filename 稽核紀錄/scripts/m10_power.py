# -*- coding: utf-8 -*-
"""M10 合成資料檢定力 — 在真實管線中注入已知強度訊號，看管線能否找回。

稽核方腳本，跑在暫存區。載入被稽核專案的「真實」analyze_symbol()，只抽換輸入：
  - 日期序列：沿用 4739 真實交易日
  - 訊號：兩種條件（真實厚尾 trust_net_K ／ 同均數同標準差的常態）
  - 價格：由合成報酬建構，使 ret[t+1] = b*z[t] + eps，population corr(z[t], fwd1[t]) = rho

判定用管線「自己的」放行標準：train_sig_fdr / replicated / replicated_nw
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

os.chdir(PROJ)                      # 讓模組的相對路徑常數可解析（唯讀）
import analyze_institutional_signal as M   # noqa: E402  ← 被測管線本體
os.chdir(SCRATCH)                   # 立刻切回，確保任何寫檔都落在暫存區

SYNTH_PX = os.path.join(SCRATCH, "synth_price.csv")
DAILY_VOL = 0.02                    # 合成日報酬總波動（小型股量級）
INJECT = ("trust", "1d", 1)         # 注入格：投信 單日淨買超 → 未來1日報酬


def build_flows(dates, sig_series, rng, cond):
    """三個法人欄位；只有 trust 帶訊號，其餘為同分布的獨立雜訊（對照組）"""
    def shuffled():
        return rng.permutation(sig_series.to_numpy())
    if cond == "real_heavy":
        trust = sig_series.to_numpy()
    else:  # gaussian
        trust = rng.normal(sig_series.mean(), sig_series.std(), len(sig_series))
    return pd.DataFrame({
        "Date": dates, "symbol": "SYNTH",
        "foreign_net_K": shuffled(),
        "trust_net_K": trust,
        "dealer_net_K": shuffled(),
    })


def make_price(dates, z, rho, rng):
    """ret[t+1] = b*z[t] + eps[t+1]，總波動固定 → corr(z[t], fwd1[t]) = rho"""
    n = len(dates)
    b = DAILY_VOL * rho
    sd_eps = DAILY_VOL * np.sqrt(1 - rho ** 2)
    ret = np.zeros(n)
    ret[1:] = b * z[:-1] + rng.normal(0, sd_eps, n - 1)
    close = 100 * np.cumprod(1 + ret)
    pd.DataFrame({"Date": dates, "Close": close}).to_csv(
        SYNTH_PX, index=False, encoding="utf-8-sig")


def run_once(dates, sig_series, rho, rng, cond):
    flows = build_flows(dates, sig_series, rng, cond)
    x = flows["trust_net_K"].to_numpy(float)
    z = (x - x.mean()) / x.std()
    make_price(dates, z, rho, rng)
    out, _ = M.analyze_symbol("SYNTH", flows)
    inst, agg, h = INJECT
    cell = out[(out["inst"] == inst) & (out["agg"] == agg) & (out["horizon_d"] == h)]
    if not len(cell):
        return None
    c = cell.iloc[0]
    return {
        "train_r": c["train_r"], "train_p": c["train_p"],
        "fdr": bool(c["train_sig_fdr"]),
        "replicated": bool(c["replicated"]),
        "replicated_nw": bool(c["replicated_nw"]),
        # 偽陽性對照：未注入訊號的 foreign 欄位有幾格被判 replicated
        "false_pos": int(out[(out["inst"] == "foreign")]["replicated"].sum()),
    }


def main():
    M.PRICE_SOURCES = {"SYNTH": SYNTH_PX}
    flows_real = pd.read_csv(os.path.join(PROJ, "output/institutional_flows_3y.csv"),
                             dtype={"Date": str, "symbol": str})
    f4739 = flows_real[flows_real["symbol"] == "4739"].reset_index(drop=True)
    dates = f4739["Date"].tolist()
    sig = f4739["trust_net_K"].astype(float)
    from scipy import stats as st
    print(f"真實 4739 trust_net_K：n={len(sig)}  峰態={st.kurtosis(sig, fisher=False):.1f}  "
          f"偏態={st.skew(sig):.1f}")
    print(f"注入格：{INJECT}   每條件 {NREP} 次重複\n")

    print(f"{'條件':<14}{'rho':>6}{'FDR顯著':>10}{'replicated':>12}"
          f"{'replicated_nw':>15}{'平均train_r':>13}{'偽陽(foreign)':>14}")
    print("-" * 84)
    results = []
    for cond in ("real_heavy", "gaussian"):
        for rho in RHOS:
            rng = np.random.default_rng(20260716)
            recs = [r for r in (run_once(dates, sig, rho, rng, cond)
                                for _ in range(NREP)) if r]
            n = len(recs)
            row = {
                "cond": cond, "rho": rho, "n": n,
                "fdr": sum(r["fdr"] for r in recs) / n,
                "rep": sum(r["replicated"] for r in recs) / n,
                "rep_nw": sum(r["replicated_nw"] for r in recs) / n,
                "mean_r": np.mean([r["train_r"] for r in recs]),
                "fp": np.mean([r["false_pos"] for r in recs]),
            }
            results.append(row)
            print(f"{cond:<14}{rho:>6.2f}{row['fdr']:>9.1%}{row['rep']:>12.1%}"
                  f"{row['rep_nw']:>15.1%}{row['mean_r']:>13.4f}{row['fp']:>14.2f}")
    pd.DataFrame(results).to_csv(os.path.join(SCRATCH, "m10_power_results.csv"),
                                 index=False, encoding="utf-8-sig")


NREP = int(os.environ.get("NREP", "200"))
# 主表（稽核紀錄引用）：NREP=200 跑這組
RHOS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
# 80% 檢定力門檻細掃（NREP=300 跑過）：
# RHOS = (0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18)

if __name__ == "__main__":
    main()
