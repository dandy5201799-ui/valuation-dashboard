#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建 investment_research.sqlite 并全量装载已核验数据。

用法：
    python3 05_数据仓库/rebuild_db.py            # 删旧库、按 schema.sql 重建、全量装载、跑验证
    python3 05_数据仓库/rebuild_db.py --no-verify

设计原则：
- 数据全部来自本文件中的常量（已人工核验），脚本可重复执行且结果一致。
- 不联网、不读写工作簿、不同步 WPS。
- 旧库无需保留：所有内容都由本脚本可复现地重建。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date

import sys as _sys
# --- 破坏性操作护栏（2026-08-03 加）---
# 本脚本会删库重建，会清空所有历史试算与市场温度记录。
# 只有在 schema 变更时才应运行；日常更新请用 update_market_temperature.py / build_mobile_dashboard.py。
if "--force" not in _sys.argv:
    print("DESTRUCTIVE: rebuild_db.py 会删除并重建数据库，清空全部历史记录。")
    print("确认要重建请加 --force；日常数据更新不需要跑本脚本。")
    _sys.exit(2)
# --- 护栏结束 ---



HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "investment_research.sqlite")
SCHEMA_PATH = os.path.join(HERE, "schema.sql")

FETCHED_AT = "2026-08-03"
VALUATION_DATE = "2026-07-31"

# ---------------------------------------------------------------- 数据源

DATA_SOURCES = [
    # (source_name, source_type, url, reliability, frequency, is_official,
    #  coverage_start, coverage_end, cross_validated_note)
    ("东方财富F10/datacenter", "vendor_api", "https://datacenter.eastmoney.com", "high",
     "annual/quarterly", 0, "2011-12-31", "2026-03-31", "与工作簿已有年报数一致"),
    ("蛋卷(雪球基金)指数估值", "vendor_api", "https://danjuanfunds.com/djapi/index_eva", "medium",
     "weekly", 0, "2016-07-31", "2026-07-31",
     "沪深300 PE 14.3751 vs 中证官方 14.36，偏差 0.10%，通过；"
     "端点 /djapi/index_eva/dj 另提供 A股(SH000300)/港股(HKHSI)/美股(SP500) 三市场的 "
     "pe/pb/pe_percentile/pb_percentile/roe/yeild，由 update_market_temperature.py 使用"),
    ("multpl.com", "vendor_api", "https://www.multpl.com", "medium",
     "daily", 0, "1881-01-31", "2026-07-31",
     "非官方汇编（Shiller 数据二次整理）。标普500 CAPE 40.91、GAAP PE 28.84、PB 5.94、"
     "股息率 1.07%，与蛋卷 PE 25.4861 存在 13% 口径差（GAAP vs 调整后盈利），"
     "仅作美股 CAPE 来源与交叉验证，不作主字段"),
    ("中证指数官方", "official_api", "https://www.csindex.com.cn", "high",
     "daily", 1, "2016-01-01", "2026-07-31", "仅提供PE，PB接口404"),
    ("FRED", "official_api", "https://fred.stlouisfed.org", "high",
     "daily", 1, "1996-01-02", "2026-07-30",
     "VIX 覆盖 1996-01-02–2026-07-30；HY OAS 本环境仅取到 2023-08 起"),
    ("香港金管局HKMA", "official_api", "https://api.hkma.gov.hk", "high",
     "daily", 1, "2002-01-02", "2026-07-31", "官方一手"),
    ("腾讯证券行情", "vendor_api", "https://qt.gtimg.cn", "medium",
     "daily", None, None, None, "实时公开行情，可能延迟"),
]
SRC_EM = "东方财富F10/datacenter"
SRC_DANJUAN = "蛋卷(雪球基金)指数估值"
SRC_CSI = "中证指数官方"
SRC_FRED = "FRED"
SRC_HKMA = "香港金管局HKMA"
SRC_TX = "腾讯证券行情"
SRC_MULTPL = "multpl.com"

# ---------------------------------------------------------------- 证券

SECURITIES = [
    ("600519.SH", "贵州茅台", "A股", "CNY", "consumer", 1),
    ("600036.SH", "招商银行A", "A股", "CNY", "bank", 1),
    ("02476.HK", "胜宏科技H", "港股", "HKD", "manufacturer", 1),
    ("300476.SZ", "胜宏科技", "A股", "CNY", "manufacturer", 1),
    ("002463.SZ", "沪电股份", "A股", "CNY", "manufacturer", 1),
]

# ---------------------------------------------------------------- 指标字典

METRIC_META = {
    "net_profit_parent": ("归母净利润", "亿元"),
    "revenue": ("营业收入", "亿元"),
    "roe_weighted": ("加权ROE", "%"),
    "roic": ("ROIC", "%"),
    "gross_margin": ("毛利率", "%"),
    "net_margin": ("净利率", "%"),
    "total_assets": ("总资产", "亿元"),
    "equity_parent": ("归属母公司股东权益", "亿元"),
    "cash": ("货币资金", "亿元"),
    "short_loan": ("短期借款", "亿元"),
    "long_loan": ("长期借款", "亿元"),
    "cfo": ("经营活动现金流量净额", "亿元"),
    "capex": ("购建固定资产等长期资产支出", "亿元"),
    "revenue_export": ("直接出口收入", "亿元"),
    "revenue_domestic": ("内销收入", "亿元"),
    "gm_pcb": ("PCB制造分部毛利率", "%"),
    "eps": ("每股收益", "元"),
    "bvps": ("每股净资产", "元"),
    "dps": ("每股现金分红", "元"),
    "net_profit_growth": ("净利润同比增速", "小数"),
    "nim": ("净息差", "小数"),
    "npl_ratio": ("不良贷款率", "小数"),
    "provision_coverage": ("拨备覆盖率", "倍"),
}

SIX = ["net_profit_parent", "revenue", "roe_weighted", "roic", "gross_margin", "net_margin"]

# 胜宏科技 300476.SZ 年度核心六项 2011–2025
SHENGHONG_ANNUAL = [
    (2011, 0.59, 7.05, 19.61, 27.84, 23.71, 8.42),
    (2012, 0.77, 9.54, 19.14, 14.80, 21.11, 8.12),
    (2013, 0.89, 9.80, 18.15, 15.46, 23.89, 9.03),
    (2014, 1.03, 10.87, 18.46, 15.82, 23.55, 9.49),
    (2015, 1.27, 12.85, 13.81, 12.81, 24.37, 9.85),
    (2016, 2.32, 18.18, 17.40, 16.51, 27.32, 12.77),
    (2017, 2.82, 24.42, 14.67, 13.36, 25.97, 11.54),
    (2018, 3.80, 33.04, 13.59, 12.68, 27.56, 11.52),
    (2019, 4.63, 38.85, 14.03, 12.99, 25.75, 11.91),
    (2020, 5.19, 56.00, None, 11.41, 23.66, 9.27),
    (2021, 6.70, 74.32, 16.16, 10.32, 20.37, 9.02),
    (2022, 7.91, 78.85, 12.14, 9.07, 18.15, 10.03),
    (2023, 6.71, 79.31, 9.35, 6.31, 20.72, 8.46),
    (2024, 11.54, 107.31, 13.95, 9.62, 22.72, 10.76),
    (2025, 43.12, 192.92, 35.56, 24.39, 35.22, 22.35),
]
SHENGHONG_Q1_2026 = (12.88, 55.19, 7.62, 5.36, 34.46, 23.34)

# 胜宏 资产负债（亿元）：total_assets, equity_parent, cash, short_loan, long_loan
SHENGHONG_BS = [
    ("2025-12-31", 352.44, 166.18, 32.80, 15.00, 38.67),
    ("2024-12-31", 191.75, 89.28, 16.62, 12.54, 23.10),
    ("2023-12-31", 173.84, 76.26, 21.41, 30.14, 17.77),
    ("2022-12-31", 143.04, 69.37, 10.95, 24.52, 8.98),
    ("2021-12-31", 134.61, 62.70, 5.79, 12.95, 9.09),
    ("2020-12-31", 96.89, 37.31, 4.52, 13.99, 7.85),
    ("2019-12-31", 69.92, 33.26, 3.56, 8.08, 0.00),
    ("2018-12-31", 53.98, 29.76, 6.75, 3.00, 0.00),
]
SHENGHONG_BS_Q1 = [("equity_parent", 174.04), ("cash", 37.94),
                   ("short_loan", 30.47), ("long_loan", 48.23)]

# 胜宏 现金流（亿元）：cfo, capex
SHENGHONG_CF = [
    (2025, 46.03, 66.17),
    (2024, 13.58, 8.34),
    (2023, 12.80, 6.45),
    (2022, 12.40, 10.61),
    (2021, 7.93, 15.37),
    (2020, 9.64, 21.02),
]

# 胜宏 主营构成：revenue_export, revenue_domestic, gm_pcb
SHENGHONG_SEG = [
    (2025, 148.21, 44.71, 30.89),
    (2024, 65.33, 41.99, 17.86),
]

# 沪电股份 002463.SZ 年度核心六项 2020–2025
HUDIAN_ANNUAL = [
    (2020, 13.43, 74.60, 24.02, 20.04, 30.37, 18.00),
    (2021, 10.64, 74.19, 15.85, 12.22, 27.18, 14.34),
    (2022, 13.62, 83.36, 17.70, 13.60, 30.28, 16.33),
    (2023, 15.13, 89.38, 16.84, 12.65, 31.01, 16.66),
    (2024, 25.87, 133.42, 24.25, 17.73, 34.54, 19.24),
    (2025, 38.22, 189.45, 28.57, 21.24, 35.48, 20.16),
]

# 贵州茅台 600519.SH（来自 03茅台估值 / 02公司比较，2025年报口径）
MOUTAI_OBS = [
    ("2025-12-31", "annual", "eps", 65.66, "元", "工作簿03茅台估值B7：2025正常化EPS，估值基准"),
    ("2025-12-31", "annual", "revenue", 1688.38, "亿元", "工作簿02公司比较B14；同比-1.21%"),
    ("2025-12-31", "annual", "net_profit_parent", 823.20, "亿元", "工作簿02公司比较C14；同比-4.53%"),
    ("2025-12-31", "annual", "gross_margin", 91.23, "%", "工作簿02公司比较E14：酒类毛利率"),
    ("2025-12-31", "annual", "cfo", 615.22, "亿元", "工作簿02公司比较F14"),
    ("2025-12-31", "annual", "equity_parent", 2446.0, "亿元", "2025年报归母权益（本轮补录）"),
    ("2025-12-31", "annual", "cash", 517.0, "亿元", "2025年末货币资金，无有息负债（本轮补录）"),
]

# 招商银行 600036.SH 年度表（工作簿03招商银行估值 A16:G22）
# (period_end, frequency, net_profit_growth, roe_weighted, nim, npl_ratio, provision_coverage, bvps)
CMB_ROWS = [
    ("2021-12-31", "annual", 0.2320, 0.1696, 0.0248, 0.0091, 4.8387, 29.01),
    ("2022-12-31", "annual", 0.1508, 0.1706, 0.0240, 0.0096, 4.5079, 32.71),
    ("2023-12-31", "annual", 0.0622, 0.1622, 0.0215, 0.0095, 4.3770, 36.71),
    ("2024-12-31", "annual", 0.0122, 0.1449, 0.0198, 0.0095, 4.1198, 41.46),
    ("2025-12-31", "annual", 0.0121, 0.1344, 0.0187, 0.0094, 3.9179, 43.43),
    ("2026-03-31", "quarterly", 0.0152, 0.1348, 0.0183, 0.0094, 3.8776, 44.90),
]
CMB_EXTRA = [
    ("2025-12-31", "annual", "eps", 5.70, "元", "归属于普通股股东利润口径"),
    ("2025-12-31", "annual", "dps", 2.016, "元", "中期＋年度，税前；派息率35.34%"),
]

# ---------------------------------------------------------------- 行情

PRICE_SNAPSHOTS = [
    # ticker, trade_date, close, currency, market_cap, pe_ttm, pb, div_yield, source
    ("600519.SH", VALUATION_DATE, 1350.60, "CNY", None, 20.57, None, None, SRC_TX),
    ("600036.SH", VALUATION_DATE, 39.62, "CNY", None, None, 0.9026, 0.0509, SRC_TX),
    ("02476.HK", VALUATION_DATE, 184.40, "HKD", None, 37.96, None, None, SRC_TX),
]

# ---------------------------------------------------------------- 模型版本

MODEL_VERSIONS = [
    ("moutai_fcfe_strict", "贵州茅台两阶段FCFE严格价格模型", "v1",
     "用五年FCFE路径、终局PE和目标回报率计算严格价格区间。", "SPEC 4A", "active", None),
    ("cmb_residual_income_strict", "招商银行两阶段剩余收益严格价格模型", "v1",
     "用BVPS、ROE路径、要求回报率和终局PB计算严格价格区间。", "SPEC 4A", "active", None),
    ("shenghong_profit_path_strict", "胜宏科技H五年利润路径严格价格模型", "v1",
     "用多口径利润、五年利润路径、退出倍数和反向指标评估价格。", "SPEC 4A", "active", None),
    ("practical_range", "实用合理价格区间模型", "v1",
     "用稳定可读的盈利或净资产基数乘以实用倍数区间，服务日常看盘。", "SPEC 4A", "active", None),
    ("shenghong_manual_terminal_pe", "胜宏科技手填终局PE口径（已废弃）", "v0",
     "终局PE直接手填22倍，并用成长期派息率做检验。", "SPEC 4 废弃口径", "deprecated",
     "终局PE手填22倍无推导、无来源，且用成长期派息率误检验；已由H模型推导与多锚参照替代"),
    ("market_current_ttm_as_normalized", "市场当期TTM EPS当作正常化EPS口径（已废弃）", "v0",
     "把指数当期TTM EPS直接称为正常化EPS并据此推算合理点位。", "SPEC 4 废弃口径", "deprecated",
     "把当期TTM EPS称为正常化EPS；已由PB—ROE正常化机制替代"),
]
# 废弃口径的替代模型（model_code, version_label）
SUPERSEDED_BY = {
    "shenghong_manual_terminal_pe": ("shenghong_profit_path_strict", "v1"),
    "market_current_ttm_as_normalized": ("practical_range", "v1"),
}

# ---------------------------------------------------------------- 估值运行

VALUATION_RUNS = [
    dict(
        ticker="600519.SH", model=("moutai_fcfe_strict", "v1"), currency="CNY",
        price=1350.60, practical=(1182.0, 1445.0), strict=(1107.9564566612241, 1203.1649532070585),
        conf_e="高", conf_m="中",
        conclusion="现价高于严格买入价带上限；五年年化低于10%目标",
        workbook="03_白酒与贵州茅台/白酒产业与贵州茅台投资研究工作簿.xlsx",
        inputs=[
            ("2025正常化EPS", 65.66, "元", "fact", "工作簿03茅台估值B7；2025年报口径", None),
            ("当前静态PE", 20.57, "倍", "derived", "当前价格÷EPS", "1350.60 / 65.66"),
            ("前5年利润CAGR", 0.05, "小数", "assumption", "中性情景成熟期增速", None),
            ("公式终局PE", 18.54, "倍", "derived", "稳定期推导，非手填",
             "payout×(1+g)/(k−g)，g=3%、ROE=30%、k=8% → payout=1−g/ROE=0.9"),
            ("目标年化回报", 0.10, "小数", "assumption", "合理价值对应的目标回报率", None),
        ],
        scenarios=[
            ("悲观", None, "利润CAGR 2%，稳定g 1%、稳定ROE 20%、k 9.5%",
             "终局PE", 11.288235294117646, 750.306629135556, -0.0374, None,
             "同时下调基本面并上调要求回报，功能上接近压力测试，不作行动阈值"),
            ("中性", 0.10, "利润CAGR 5%，稳定g 3%、稳定ROE 30%、k 8%",
             "终局PE", 18.54, 1203.2, 0.0727, None, "10%目标回报买入价"),
            ("乐观", 0.08, "利润CAGR 8%，稳定g 3.5%、稳定ROE 30%、k 7.5%",
             "终局PE", 22.85625, 1608.96, 0.1419, None, "周期修复与估值上沿测试"),
        ],
        tiers=[],
    ),
    dict(
        ticker="600036.SH", model=("cmb_residual_income_strict", "v1"), currency="CNY",
        price=39.62, practical=(42.0, 50.0), strict=(33.39, 44.77),
        conf_e="中高", conf_m="中高",
        conclusion="两个口径同时折价，是三只中唯一",
        workbook="04_银行与招商银行/银行板块与招商银行投资研究工作簿.xlsx",
        inputs=[
            ("调整后起始BVPS", 43.897, "元", "fact",
             "2026Q1 BVPS 44.90 − 报告后已除权年度股息 1.003", None),
            ("当前PB", 0.9026, "倍", "derived", "当前价格÷调整后BVPS", "39.62 / 43.897"),
            ("要求回报率kₑ", 0.115, "小数", "assumption",
             "本表hurdle，不是CAPM股权成本；引用隐含ROE必须同时报kₑ与g", None),
            ("稳定增长g", 0.03, "小数", "assumption", "稳定期永续增长", None),
            ("稳定ROE", 0.113, "小数", "assumption", "中性情景稳定期ROE", None),
            ("市场隐含稳定ROE", 0.1067, "小数", "derived",
             "由当前PB反推；完全依赖kₑ=11.5%与g=3%", "ROE = g + PB×(k−g)"),
        ],
        scenarios=[
            ("悲观", None, "Y1–Y5 ROE 12.0%→9.5%，k=13%、稳定g 2.5%、稳定ROE 9.5%",
             "第5年PB", 0.6666666666666666, 29.25, 0.0505, 12.0558,
             "压力测试；自2026-08-02起不得用作明显低估行动阈值"),
            ("中性", 0.115, "Y1–Y5 ROE 13.2%→11.6%，k=11.5%、稳定g 3%、稳定ROE 11.3%",
             "第5年PB", 0.9764705882352941, 44.77, 0.1329, 13.9312, "今日内在价值"),
            ("乐观", 0.10, "Y1–Y5 ROE 13.5%→12.3%，k=10%、稳定g 3.5%、稳定ROE 12%",
             "第5年PB", 1.3076923076923075, 61.50, 0.1947, 13.3352, "区间上沿"),
        ],
        tiers=[],
    ),
    dict(
        ticker="02476.HK", model=("shenghong_profit_path_strict", "v1"), currency="HKD",
        price=184.40, practical=(158.0, 193.0), strict=(98.0, 107.0),
        conf_e="低", conf_m="低",
        conclusion="两套区间无重叠；不宣称精确合理价值",
        workbook=None,
        inputs=[
            ("2026E利润", 62.0, "亿元", "assumption",
             "景气预测口径，非正常化利润", "2026Q1归母12.88亿按2025季节性(21.4%)外推≈60.3亿"),
            ("EV/IC", 7.47, "倍", "derived",
             "备考口径，含2026-04完成的H股IPO资本结构", "企业价值÷投入资本（2026Q1备考）"),
            ("投入资本IC", 214.80, "亿元", "fact", "2026Q1备考投入资本", None),
            ("WACC", 0.112, "小数", "assumption", "加权平均资本成本", None),
            ("中性五年IRR", -0.0138, "小数", "derived",
             "按中性利润路径与退出倍数反推", None),
            ("同倍数退出IRR", 0.1329, "小数", "derived",
             "反向指标：仍依赖利润路径假设，只消除了退出倍数假设", None),
            ("10%所需退出PE", 21.71, "倍", "derived",
             "反向指标：仍依赖2026E利润与五年路径假设", None),
        ],
        scenarios=[
            ("悲观", None, "利润回落至历史中周期参照利润附近", "退出PE", None,
             40.41, -0.1832, None, "下行参考线，不作行动阈值"),
            ("中性", None, "2026E后增速淡出至稳定期", "退出PE", None,
             99.46, -0.0138, None, "严格区间中枢"),
            ("乐观", None, "AI服务器需求延续，利润与倍数同时抬升", "退出PE", None,
             169.15, 0.1053, None, "上沿"),
        ],
        tiers=[
            ("2025已实现归母净利", 43.12, "亿元", "A", "年报审计", 36.3),
            ("历史中周期参照利润（升级前产品结构）", 24.13, "亿元", "B",
             "三口径一致性检查：净利率9.67%×营收247 / ROE14.67%×权益166.18 / ROIC12.90%×IC187.05", 64.8),
            ("升级后中周期参照利润（同业锚）", 40.8, "亿元", "C",
             "沪电2020–2023净利率中位16.5%×胜宏2026E营收247亿", 38.3),
            ("2026E景气预测利润", 62.0, "亿元", "B",
             "2026Q1归母12.88亿按2025季节性(21.4%)外推≈60.3亿", 25.2),
        ],
    ),
]

# ---------------------------------------------------------------- 市场仓位

MARKET_RUNS = [
    ("A股", "沪深300", 4588.2, 359.8, 4639.2, 0.9890, 0.522,
     "normalized_pb_roe", 1.4655, 1.4626, 12.7283, 0.1149, 1, 12.7283, "正常", "合理", "中"),
    ("港股", "恒生指数", 25858.9, 2199.2, 20542.8, 1.2588, 0.0,
     "normalized_pb_roe", 1.2319, 1.0938, 10.4401, 0.1048, 1, 10.4401, "正常", "明显高估", "中"),
    ("美股", "标普500", 7413.2, 310.0, 7628.8, 0.9717, 0.40,
     "third_party_normalized", None, None, None, None, 1, 22.98, "正常", "合理", "中"),
]

CRISIS_OBS = [
    ("美股", "vix", 17.09, "点", "正常", SRC_FRED,
     "四次危机峰值 2008:80.86 / 2015:40.74 / 2020:82.69 / 2022:36.45；"
     "阈值 中位18.49 / 90%29.40 / 99%49.33"),
    ("港股", "hibor_on_minus_1m", -0.36, "pct", "正常", SRC_HKMA,
     "四次危机读数 2008:+0.58 / 2015:−0.16 / 2020:−0.27 / 2022:+0.35；"
     "阈值 中位−0.22 / 90%−0.06 / 99%0.54"),
    ("A股", "credit_spread_aaa", 0.36, "pct", "未校准", None,
     "中债接口404，阈值未校准，仅人工判断"),
]

# ---------------------------------------------------------------- 假设变更

CHANGE_LOG = [
    ("02476.HK", None, "终局PE", "22（手填）", "12.4（H模型推导）",
     "手填无推导无来源", "成熟期锚集中10–13倍"),
    ("02476.HK", None, "盈利口径", "单一“正常化利润”", "四层口径（profit_basis_tiers）",
     "2011–2024中位数代表升级前结构，不能称正常化",
     "已实现43.12亿 / 历史中周期24.13亿 / 升级后中周期40.8亿 / 2026E 62亿"),
    ("600036.SH", None, "明显低估阈值", "29.25（悲观压力值）", "33.39（中性k=14%）",
     "压力测试值不得用作行动阈值", "SPEC 跨模型统一规则第2条"),
    (None, "A股", "指数EPS口径", "当期TTM 319.2", "PB—ROE正常化 359.8",
     "当前PB在历史中位而PE在86分位，盈利被压低",
     "蛋卷序列＋中证官方PE交叉验证偏差0.10%"),
    ("02476.HK", None, "EV/IC", "8.48（2025年末且未含IPO）", "7.47（2026Q1备考含IPO资本结构）",
     "IPO 2026-04完成，晚于两张资产负债表", "2026Q1备考投入资本214.80亿元"),
]


# ================================================================ 装载

def build(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # -- data_sources
    cur.executemany(
        """insert into data_sources
           (source_name, source_type, source_url, reliability_level, frequency,
            is_official, coverage_start, coverage_end, cross_validated_note)
           values (?,?,?,?,?,coalesce(?,0),?,?,?)""",
        DATA_SOURCES,
    )
    src = {n: i for n, i in cur.execute("select source_name, id from data_sources")}

    # -- securities
    cur.executemany(
        """insert into securities (ticker, name, market, currency, business_type, active)
           values (?,?,?,?,?,?)""",
        SECURITIES,
    )
    sec = {t: i for t, i in cur.execute("select ticker, id from securities")}

    # -- model_versions
    cur.executemany(
        """insert into model_versions
           (model_code, model_name, version_label, description, spec_section,
            status, deprecated_reason)
           values (?,?,?,?,?,?,?)""",
        MODEL_VERSIONS,
    )
    mv = {(c, v): i for c, v, i in
          cur.execute("select model_code, version_label, id from model_versions")}
    for dep, target in SUPERSEDED_BY.items():
        cur.execute("update model_versions set superseded_by_id=? where model_code=?",
                    (mv[target], dep))

    # -- raw_observations -------------------------------------------------
    obs: list[tuple] = []

    def add(ticker, code, period_end, freq, value, source, note=None, unit=None):
        name, default_unit = METRIC_META[code]
        obs.append((
            sec[ticker] if ticker else None, code, name, period_end, freq,
            value, unit or default_unit, src[source] if source else None,
            note, FETCHED_AT,
        ))

    # 胜宏 年度核心六项
    for row in SHENGHONG_ANNUAL:
        year, vals = row[0], row[1:]
        pe = f"{year}-12-31"
        for code, v in zip(SIX, vals):
            note = None
            if v is None:
                note = "东方财富接口该年ROE返回值异常，已剔除；保留占位行"
            add("300476.SZ", code, pe, "annual", v, SRC_EM, note)
    for code, v in zip(SIX, SHENGHONG_Q1_2026):
        add("300476.SZ", code, "2026-03-31", "quarterly", v, SRC_EM)

    # 胜宏 资产负债
    bs_codes = ["total_assets", "equity_parent", "cash", "short_loan", "long_loan"]
    for row in SHENGHONG_BS:
        pe, vals = row[0], row[1:]
        for code, v in zip(bs_codes, vals):
            add("300476.SZ", code, pe, "annual", v, SRC_EM)
    for code, v in SHENGHONG_BS_Q1:
        add("300476.SZ", code, "2026-03-31", "quarterly", v, SRC_EM)

    # 胜宏 现金流
    for year, cfo, capex in SHENGHONG_CF:
        add("300476.SZ", "cfo", f"{year}-12-31", "annual", cfo, SRC_EM)
        add("300476.SZ", "capex", f"{year}-12-31", "annual", capex, SRC_EM)

    # 胜宏 主营构成
    for year, exp, dom, gm in SHENGHONG_SEG:
        add("300476.SZ", "revenue_export", f"{year}-12-31", "annual", exp, SRC_EM)
        add("300476.SZ", "revenue_domestic", f"{year}-12-31", "annual", dom, SRC_EM)
        add("300476.SZ", "gm_pcb", f"{year}-12-31", "annual", gm, SRC_EM)

    # 沪电股份
    for row in HUDIAN_ANNUAL:
        year, vals = row[0], row[1:]
        pe = f"{year}-12-31"
        for code, v in zip(SIX, vals):
            add("002463.SZ", code, pe, "annual", v, SRC_EM, "同业peer，用于胜宏净利率同业锚")

    # 茅台
    for pe, freq, code, v, unit, note in MOUTAI_OBS:
        add("600519.SH", code, pe, freq, v, SRC_EM, note, unit)

    # 招行
    cmb_codes = ["net_profit_growth", "roe_weighted", "nim", "npl_ratio",
                 "provision_coverage", "bvps"]
    cmb_units = {"roe_weighted": "小数"}
    for row in CMB_ROWS:
        pe, freq, vals = row[0], row[1], row[2:]
        for code, v in zip(cmb_codes, vals):
            add("600036.SH", code, pe, freq, v, SRC_EM,
                "工作簿03招商银行估值A16:G22年度趋势表", cmb_units.get(code))
    for pe, freq, code, v, unit, note in CMB_EXTRA:
        add("600036.SH", code, pe, freq, v, SRC_EM, note, unit)

    cur.executemany(
        """insert into raw_observations
           (security_id, metric_code, metric_name, period_end, frequency,
            value, unit, source_id, source_note, fetched_at)
           values (?,?,?,?,?,?,?,?,?,?)""",
        obs,
    )

    # -- price_snapshots
    cur.executemany(
        """insert into price_snapshots
           (security_id, trade_date, close_price, currency, market_cap,
            pe_ttm, pb, dividend_yield, source_id)
           values (?,?,?,?,?,?,?,?,?)""",
        [(sec[t], d, c, cy, mc, pe, pb, dy, src[s])
         for t, d, c, cy, mc, pe, pb, dy, s in PRICE_SNAPSHOTS],
    )

    # -- valuation_runs / inputs / scenarios / tiers
    for run in VALUATION_RUNS:
        cur.execute(
            """insert into valuation_runs
               (security_id, valuation_date, model_version_id, run_type, price_at_run,
                currency, practical_low, practical_high, strict_low, strict_high,
                conclusion, confidence_earnings, confidence_multiple, workbook_path)
               values (?,?,?,'full',?,?,?,?,?,?,?,?,?,?)""",
            (sec[run["ticker"]], VALUATION_DATE, mv[run["model"]], run["price"],
             run["currency"], run["practical"][0], run["practical"][1],
             run["strict"][0], run["strict"][1], run["conclusion"],
             run["conf_e"], run["conf_m"], run["workbook"]),
        )
        run_id = cur.lastrowid
        run["_id"] = run_id
        cur.executemany(
            """insert into valuation_inputs
               (run_id, input_name, input_value, unit, input_type, source_note, formula_note)
               values (?,?,?,?,?,?,?)""",
            [(run_id, *i) for i in run["inputs"]],
        )
        cur.executemany(
            """insert into scenario_results
               (run_id, scenario_name, target_return, growth_path, terminal_metric_name,
                terminal_metric_value, fair_value, expected_irr, dividend_value, notes)
               values (?,?,?,?,?,?,?,?,?,?)""",
            [(run_id, *s) for s in run["scenarios"]],
        )
        if run["tiers"]:
            cur.executemany(
                """insert into profit_basis_tiers
                   (run_id, tier_name, tier_amount, unit, evidence_grade,
                    derivation, implied_multiple)
                   values (?,?,?,?,?,?,?)""",
                [(run_id, *t) for t in run["tiers"]],
            )

    run_by_ticker = {r["ticker"]: r["_id"] for r in VALUATION_RUNS}

    # -- market_position_runs
    cur.executemany(
        """insert into market_position_runs
           (market_code, valuation_date, index_name, index_level, normalized_eps,
            fair_index_level, current_to_fair_ratio, suggested_position, eps_basis,
            pb_current, pb_median, pe_median, long_run_roe, calibrated, terminal_pe,
            crisis_state, conclusion, confidence, workbook_path)
           values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(m[0], VALUATION_DATE, *m[1:],
          "01_市场与仓位/市场估值与仓位管理工作簿.xlsx") for m in MARKET_RUNS],
    )

    # -- crisis_metric_observations
    cur.executemany(
        """insert into crisis_metric_observations
           (market_code, metric_code, observation_date, value, unit, state, source_id, notes)
           values (?,?,?,?,?,?,?,?)""",
        [(mk, code, VALUATION_DATE, v, u, st, src[s] if s else None, n)
         for mk, code, v, u, st, s, n in CRISIS_OBS],
    )

    # -- assumption_change_log
    cur.executemany(
        """insert into assumption_change_log
           (security_id, market_code, change_date, changed_field, old_value, new_value,
            reason, evidence_summary, related_run_id)
           values (?,?,?,?,?,?,?,?,?)""",
        [(sec[t] if t else None, mkt, date.today().isoformat(), field, old, new,
          reason, ev, run_by_ticker.get(t))
         for t, mkt, field, old, new, reason, ev in CHANGE_LOG],
    )

    conn.commit()


# ================================================================ 验证

TABLES = [
    "securities", "data_sources", "raw_observations", "price_snapshots",
    "model_versions", "valuation_runs", "valuation_inputs", "profit_basis_tiers",
    "scenario_results", "assumption_change_log", "market_position_runs",
    "crisis_metric_observations", "market_temperature_runs",
]

EXPECTED_MIN = {
    "raw_observations": 150,
    "valuation_inputs": 15,
}
EXPECTED_EXACT = {
    "scenario_results": 9,
    "profit_basis_tiers": 4,
}


def verify(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    failures = []

    print("\n== 各表行数 ==")
    for t in TABLES:
        n = cur.execute(f"select count(*) from {t}").fetchone()[0]
        flag = ""
        if t in EXPECTED_MIN:
            ok = n >= EXPECTED_MIN[t]
            flag = f"  (要求 ≥{EXPECTED_MIN[t]}: {'OK' if ok else 'FAIL'})"
            if not ok:
                failures.append(f"{t} 行数 {n} < {EXPECTED_MIN[t]}")
        if t in EXPECTED_EXACT:
            ok = n == EXPECTED_EXACT[t]
            flag = f"  (要求 ={EXPECTED_EXACT[t]}: {'OK' if ok else 'FAIL'})"
            if not ok:
                failures.append(f"{t} 行数 {n} != {EXPECTED_EXACT[t]}")
        print(f"{t:<30} {n:>5}{flag}")

    print("\n== unique 约束验证 ==")
    checks = [
        ("raw_observations(security_id,metric_code,period_end,frequency)",
         """insert into raw_observations
            (security_id, metric_code, metric_name, period_end, frequency, value, unit)
            select security_id, metric_code, metric_name, period_end, frequency, value, unit
            from raw_observations limit 1"""),
        ("crisis_metric_observations(market_code,metric_code,observation_date)",
         """insert into crisis_metric_observations
            (market_code, metric_code, observation_date, value, unit)
            select market_code, metric_code, observation_date, value, unit
            from crisis_metric_observations limit 1"""),
        ("profit_basis_tiers(run_id,tier_name)",
         """insert into profit_basis_tiers (run_id, tier_name)
            select run_id, tier_name from profit_basis_tiers limit 1"""),
        ("market_position_runs(market_code,valuation_date)",
         """insert into market_position_runs (market_code, valuation_date, index_name)
            select market_code, valuation_date, index_name
            from market_position_runs limit 1"""),
    ]
    for label, sql in checks:
        try:
            cur.execute(sql)
            conn.rollback()
            print(f"FAIL  {label}  重复插入未被拒绝")
            failures.append(f"unique 未生效: {label}")
        except sqlite3.IntegrityError as e:
            conn.rollback()
            print(f"OK    {label}  -> {e}")

    print("\n== 置信度值域约束（valuation_runs.confidence_earnings）==")
    try:
        cur.execute("""insert into valuation_runs
                       (security_id, valuation_date, model_version_id, run_type, currency,
                        confidence_earnings, confidence_multiple)
                       values (1,'2026-07-31',1,'full','CNY','很高','中')""")
        conn.rollback()
        print("FAIL  非法置信度被接受")
        failures.append("confidence_earnings 值域未生效")
    except sqlite3.IntegrityError as e:
        conn.rollback()
        print(f"OK    非法置信度被拒绝 -> {e}")

    print("\n== v_current_positions ==")
    rows = cur.execute("""select ticker, name, currency, price, practical_range,
                                 strict_range, confidence_earnings, confidence_multiple,
                                 conclusion
                          from v_current_positions order by ticker""").fetchall()
    for r in rows:
        print(f"{r[0]:<11} {r[1]:<8} {r[2]}  现价 {r[3]:>8}  实用 {r[4]:<12} "
              f"严格 {r[5]:<12} 盈利置信 {r[6]:<3} 倍数置信 {r[7]:<3}")
        print(f"{'':<11} 结论：{r[8]}")
    if len(rows) != 3:
        failures.append(f"v_current_positions 返回 {len(rows)} 行，应为 3")

    print("\n== 胜宏 ROIC 序列与 2011–2024 中位数 ==")
    roic = cur.execute("""select period_end, value
                          from raw_observations
                          where security_id = (select id from securities where ticker='300476.SZ')
                            and metric_code = 'roic' and frequency='annual'
                          order by period_end""").fetchall()
    for pe, v in roic:
        print(f"  {pe}  {v}")
    med = cur.execute("""with s as (
                           select value from raw_observations
                           where security_id = (select id from securities where ticker='300476.SZ')
                             and metric_code='roic' and frequency='annual'
                             and period_end between '2011-01-01' and '2024-12-31'
                             and value is not null
                           order by value
                         ), c as (select count(*) n from s)
                         select round(avg(value), 4) from (
                           select value, row_number() over (order by value) rn, (select n from c) n
                           from s
                         ) where rn in ((n+1)/2, (n+2)/2)""").fetchone()[0]
    ok = abs(med - 12.90) < 1e-6
    print(f"  2011–2024 ROIC 中位数 = {med}  (期望 12.90: {'OK' if ok else 'FAIL'})")
    if not ok:
        failures.append(f"ROIC 中位数 {med} != 12.90")

    print("\n== 废弃模型 ==")
    for r in cur.execute("""select m.model_code, m.status, s.model_code, m.deprecated_reason
                            from model_versions m
                            left join model_versions s on s.id = m.superseded_by_id
                            where m.status='deprecated'"""):
        print(f"  {r[0]}  -> 替代者 {r[2]}\n     原因：{r[3]}")

    print("\n== 结果 ==")
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("全部验证通过。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"已删除旧库 {DB_PATH}")

    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = f.read()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    conn.execute("pragma foreign_keys = on")
    build(conn)
    print(f"重建完成：{DB_PATH}")

    rc = 0 if args.no_verify else verify(conn)
    conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
