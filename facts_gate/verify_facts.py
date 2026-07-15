"""
verify_facts.py — 稽核方事實帳本驗證器（Layer 2 反造假控制）

把 facts.yaml 裡登記的每一筆「既定事實」拿去**重跑被稽核專案的腳本**，比對輸出與
帳本記錄值是否逐一吻合。任一筆對不上 → 以非 0 exit code 結束，使它能被 pre-commit /
CI / 部署前流程當成「閘門」擋下造假或漂移。

設計原則
--------
- 只讀被稽核專案，絕不寫回：被稽核腳本會原地覆寫輸入 CSV，故一律先把輸入複製到
  一個暫存目錄，再對副本執行。原始檔不受影響。
- 執行者住在 agent 之外：本檔在稽核方工作區，由工作流程（hook/CI/人）觸發，不靠
  被稽核 agent 自律。
- 覆蓋「真實性」而非只有「出處」：值是當場重跑算出來的，不是讀文件比字串。

用法
----
    python verify_facts.py                      # 用同目錄 facts.yaml
    python verify_facts.py --ledger other.yaml  # 指定其他帳本
    python verify_facts.py --project-root <路徑> # 覆寫被稽核專案根目錄

exit code: 0=全數通過  1=有 fact 對不上（閘門擋下）  2=設定/執行錯誤
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

# 本檔輸出含中文，Windows 預設 cp950 終端會亂碼/崩潰。閘門必須在「任何人的預設終端」
# 都能正確顯示結果，否則 FAIL 訊息可能被誤讀為工具壞掉。（同一問題見稽核紀錄 🔵 項）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))

# 解析 apply_multiple_testing_correction.py 輸出的資料列，例如：
#   "  1日         69                2          5   p<0.000063（有效測試數=793）"
# group(1)=持有期天數  group(2)=原始p<0.05  group(3)=Bonferroni  group(4)=FDR顯著
_FDR_ROW = re.compile(r"^\s*(\d+)日\s+(\d+)\s+(\d+)\s+(\d+)")


def _run_script(project_root, script_rel, input_csv_rel):
    """把 input_csv 複製到暫存區，對副本執行 script，回傳 (stdout, tmpdir)。呼叫端負責清 tmpdir。"""
    script = os.path.join(project_root, script_rel)
    src_csv = os.path.join(project_root, input_csv_rel)
    if not os.path.isfile(script):
        raise FileNotFoundError(f"找不到腳本: {script}")
    if not os.path.isfile(src_csv):
        raise FileNotFoundError(f"找不到輸入 CSV: {src_csv}")

    tmpdir = tempfile.mkdtemp(prefix="facts_gate_")
    copy_csv = os.path.join(tmpdir, os.path.basename(src_csv))
    shutil.copyfile(src_csv, copy_csv)  # 只複製，被稽核原檔不動

    env = dict(os.environ, PYTHONUTF8="1")  # 避開 cp950 終端 emoji 崩潰
    proc = subprocess.run(
        [sys.executable, script, "--csv", copy_csv],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"腳本以非 0 結束（{proc.returncode}）:\n{proc.stderr or proc.stdout}")
    return proc.stdout, tmpdir


def _check_fdr_counts(project_root, check, expected):
    """重跑校正腳本，從輸出解析各持有期 FDR 顯著數，比對 expected。回傳 (ok, actual, msg)。"""
    stdout, tmpdir = _run_script(project_root, check["script"], check["input_csv"])
    try:
        actual = {}
        for line in stdout.splitlines():
            m = _FDR_ROW.match(line)
            if m:
                actual[m.group(1)] = int(m.group(4))  # 持有期 -> FDR顯著數
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    exp = {str(k): int(v) for k, v in expected.items()}
    diffs = []
    for h, ev in exp.items():
        av = actual.get(h)
        if av != ev:
            diffs.append(f"{h}日 期望={ev} 實測={av}")
    ok = not diffs
    msg = "逐位吻合 " + " ".join(f"{h}日={actual.get(h)}" for h in exp) if ok else "；".join(diffs)
    return ok, actual, msg


CHECKERS = {
    "fdr_counts": _check_fdr_counts,
}


def main():
    ap = argparse.ArgumentParser(description="稽核方事實帳本驗證器")
    ap.add_argument("--ledger", default=os.path.join(HERE, "facts.yaml"))
    ap.add_argument("--project-root", default=None, help="覆寫 facts.yaml 的 audited_project_root")
    args = ap.parse_args()

    try:
        with open(args.ledger, encoding="utf-8") as f:
            ledger = yaml.safe_load(f)
    except Exception as e:
        print(f"[設定錯誤] 讀不到帳本 {args.ledger}: {e}")
        return 2

    project_root = args.project_root or ledger.get("audited_project_root")
    if not project_root or not os.path.isdir(project_root):
        print(f"[設定錯誤] 被稽核專案根目錄無效: {project_root}")
        return 2

    facts = ledger.get("facts", [])
    print(f"事實帳本驗證器 — 帳本 {os.path.basename(args.ledger)}，共 {len(facts)} 筆")
    print(f"被稽核專案: {project_root}")
    print("=" * 70)

    n_pass = n_fail = n_err = 0
    for fact in facts:
        fid = fact.get("id", "<no-id>")
        checker = CHECKERS.get(fact.get("check", {}).get("type"))
        if checker is None:
            print(f"[ERROR] {fid}: 未知 check.type={fact.get('check', {}).get('type')}")
            n_err += 1
            continue
        try:
            ok, _actual, msg = checker(project_root, fact["check"], fact["expected"])
        except Exception as e:
            print(f"[ERROR] {fid}: 重跑失敗 — {e}")
            n_err += 1
            continue
        if ok:
            print(f"[PASS ] {fid}: {msg}")
            n_pass += 1
        else:
            print(f"[FAIL ] {fid}: {msg}")
            print(f"         主張: {fact.get('claim', '')}")
            print(f"         來源: {fact.get('source_doc', '')}")
            n_fail += 1

    print("=" * 70)
    print(f"結果: PASS={n_pass}  FAIL={n_fail}  ERROR={n_err}")
    if n_fail or n_err:
        print(">>> 閘門擋下：有 fact 對不上或無法重跑，不得升級為既定事實/同步公開版。")
        return 1
    print(">>> 全數逐位重現，通過閘門。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
