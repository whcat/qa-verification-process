# -*- coding: utf-8 -*-
"""closeout_check.py — 稽核方收尾檢查(卡點B:由使用者親自執行)

用途:每輪稽核/工作收尾時,由**使用者**在本資料夾執行:

    python closeout_check.py

檢查四項(任何一項 FAIL → exit 1,fail-closed):
  C1  PROGRESS.md 本日已更新(「最後更新」日期 = 今天)
  C2  稽核總表統計數字 = 問題點追蹤帳逐列加總(未結案/待覆核/已結案)
  C3  總表輪次總覽中:今日輪次必須連結交付報告,且所有被連結的報告檔案存在
  C4  交付報告雙副本完整性:稽核紀錄/ 基準原本 vs 對方 repo 交付件,
      換行符正規化後必須逐字元相同(不同 = 疑似遭改動,FAIL)

設計依據(CLAUDE.md 稽核紀律第6條):可靠的控制只有外部/結構性驗證,
且觸發者須為工作流程而非 agent 自覺。故本腳本的「通過」**只在使用者
親自執行時構成控制**;agent 代跑僅屬測試,不得以此宣稱「收尾檢查通過」。

2026/07/17 依使用者核准之改進第一項建立。
"""
import os
import re
import sys
import datetime
from pathlib import Path

# UTF-8 輸出(2026/07/17 使用者實際終端為 UTF-8,預設 cp950 bytes 顯示為亂碼);
# errors="replace" 保底不崩潰(SA-05 教訓:編碼問題只准影響顯示,不准影響 exit code)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "稽核紀錄" / "稽核總表.md"
PROGRESS = ROOT / "PROGRESS.md"
RECORDS_DIR = ROOT / "稽核紀錄"

# 交付件雙副本:被稽核專案名 → 對方 repo 中存放交付件的資料夾
DELIVERED_DIRS = {
    "Stock analysis": Path(r"C:\Users\ray74\OneDrive\桌面\專案系列\Claud AI  Project\Stock analysis\docs"),
}

TODAY = datetime.date.today().strftime("%Y/%m/%d")
failures = []
infos = []


def fail(code, msg):
    failures.append(f"[FAIL {code}] {msg}")


def ok(code, msg):
    print(f"[PASS {code}] {msg}")


def info(msg):
    infos.append(f"[INFO] {msg}")


# ── C1 PROGRESS.md 本日已更新 ──────────────────────────────────────────
def check_progress():
    if not PROGRESS.exists():
        return fail("C1", "PROGRESS.md 不存在")
    text = PROGRESS.read_text(encoding="utf-8")
    m = re.search(r"最後更新[::]\s*(\d{4}/\d{2}/\d{2})", text)
    if not m:
        return fail("C1", "PROGRESS.md 找不到「最後更新:YYYY/MM/DD」行")
    if m.group(1) != TODAY:
        return fail("C1", f"PROGRESS.md 最後更新={m.group(1)},今天={TODAY} — 收尾前必須更新(規則 2026/07/17)")
    ok("C1", f"PROGRESS.md 最後更新 = 今天({TODAY})")


# ── C2 稽核總表統計 = 逐列加總 ────────────────────────────────────────
def check_ledger_consistency():
    if not LEDGER.exists():
        return fail("C2", "稽核總表.md 不存在")
    text = LEDGER.read_text(encoding="utf-8")

    counts = {"open": 0, "pending": 0, "closed": 0}
    ids = {"open": [], "pending": [], "closed": []}
    for line in text.splitlines():
        m = re.match(r"^\|\s*([A-Z]{2}-\d+)\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 7:
            return fail("C2", f"{m.group(1)} 列欄位數異常:{line[:60]}…")
        status = cells[5]
        hit = [k for k, kw in (("open", "未結案"), ("pending", "待覆核"), ("closed", "已結案")) if kw in status]
        if len(hit) != 1:
            return fail("C2", f"{m.group(1)} 狀態欄無法唯一判讀:「{status}」")
        counts[hit[0]] += 1
        ids[hit[0]].append(m.group(1))

    if sum(counts.values()) == 0:
        return fail("C2", "問題點追蹤帳解析不到任何 SA-xx 列")

    stated = {}
    for key, kw in (("open", "未結案"), ("pending", "待覆核"), ("closed", "已結案")):
        sm = re.search(r"^\|[^|]*" + kw + r"[^|]*\|\s*(\d+)", text, re.M)
        if not sm:
            return fail("C2", f"統計表找不到「{kw}」列")
        stated[key] = int(sm.group(1))

    bad = False
    for key, label in (("open", "未結案"), ("pending", "待覆核"), ("closed", "已結案")):
        if counts[key] != stated[key]:
            fail("C2", f"統計表寫{label}={stated[key]},逐列加總={counts[key]}(實際:{','.join(ids[key]) or '無'})")
            bad = True
    if not bad:
        ok("C2", f"總表統計與逐列加總一致:未結案{counts['open']}/待覆核{counts['pending']}/已結案{counts['closed']}")


# ── C3 輪次總覽的交付報告連結 ─────────────────────────────────────────
def check_round_reports():
    text = LEDGER.read_text(encoding="utf-8")
    sec = re.search(r"### 稽核輪次總覽(.*?)(?=\n#|\Z)", text, re.S)
    if not sec:
        return fail("C3", "稽核總表找不到「稽核輪次總覽」節")
    rows = [l for l in sec.group(1).splitlines()
            if l.startswith("|") and not re.match(r"^\|\s*(輪次|---)", l)]
    if not rows:
        return fail("C3", "輪次總覽解析不到任何資料列")

    today_rows = 0
    today_linked = 0
    all_ok = True
    for row in rows:
        cells = [c.strip() for c in row.split("|")]
        if len(cells) < 7:
            continue
        date, report_cell = cells[2], cells[6]
        names = re.findall(r"交付報告_[^|`]+?\.md", report_cell)
        for name in names:
            if not (RECORDS_DIR / name).exists():
                fail("C3", f"輪次總覽連結的報告不存在:稽核紀錄/{name}")
                all_ok = False
        if date == TODAY:
            today_rows += 1
            if names:
                today_linked += 1
    if today_rows and today_linked == 0:
        fail("C3", f"今日({TODAY})有稽核輪次但未連結任何交付報告——依規則每輪必產出")
        all_ok = False
    if all_ok:
        note = f";今日輪次 {today_rows} 列均已連結報告" if today_rows else ";今日無新輪次(僅制度/覆查作業時屬正常)"
        ok("C3", f"輪次總覽引用的交付報告檔案齊全{note}")


# ── C4 雙副本完整性 ──────────────────────────────────────────────────
def _normalized(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def check_dual_copies():
    reports = sorted(RECORDS_DIR.glob("交付報告_*.md"))
    if not reports:
        return fail("C4", "稽核紀錄/ 內沒有任何交付報告(基準原本遺失?)")
    all_ok = True
    for rp in reports:
        m = re.match(r"交付報告_(.+)_\d{4}-\d{2}-\d{2}\.md$", rp.name)
        proj = m.group(1) if m else None
        ddir = DELIVERED_DIRS.get(proj)
        if ddir is None:
            info(f"{rp.name}:專案「{proj}」未設定交付目錄,跳過雙副本比對")
            continue
        other = ddir / rp.name
        if not other.exists():
            info(f"{rp.name}:對方 {ddir} 尚無交付件(未交付狀態,允許)")
            continue
        if _normalized(rp) == _normalized(other):
            ok("C4", f"{rp.name}:兩副本正規化後逐字元相同")
        else:
            fail("C4", f"{rp.name}:兩副本內容不同——疑似交付件遭改動,依規則列新🔴優先處理")
            all_ok = False
    return all_ok


def main():
    print(f"=== 稽核方收尾檢查 closeout_check.py === 今天:{TODAY}")
    print("(本檢查僅在使用者親自執行時構成控制;agent 代跑只算測試)\n")
    check_progress()
    check_ledger_consistency()
    check_round_reports()
    check_dual_copies()
    print()
    for line in infos:
        print(line)
    if failures:
        print()
        for line in failures:
            print(line)
        print(f"\n=== 結果:FAIL({len(failures)} 項)— 收尾不得放行 ===")
        sys.exit(1)
    print("\n=== 結果:PASS — 四項檢查全部通過 ===")
    sys.exit(0)


if __name__ == "__main__":
    main()
