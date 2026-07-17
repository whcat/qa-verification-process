# -*- coding: utf-8 -*-
"""第五輪覆稽:在暫存區重跑對方 v2 管線(真實資料),不觸碰被稽核專案。
cwd = scratchpad/round5(輸入已複製至此),py 模組從對方專案載入(唯讀)。"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PROJ_PY = r"C:\Users\ray74\OneDrive\桌面\專案系列\Claud AI  Project\Stock analysis\py"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRATCH)
sys.path.insert(0, PROJ_PY)
import analyze_institutional_signal as ais
ais.main()
