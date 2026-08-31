#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["HTTPS_PROXY"] = ""
os.environ["HTTP_PROXY"] = ""
os.environ["ALL_PROXY"] = ""

import baostock as bs
import pandas as pd


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "trend_cases.json"


def retry(fn, attempts=4, delay=1.5):
    last_error = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            time.sleep(delay * (i + 1))
    raise last_error


def fetch_baostock(code):
    fields = "date,open,high,low,close,volume"
    rs = bs.query_history_k_data_plus(
        code,
        fields,
        start_date="2024-01-01",
        end_date="2026-08-30",
        frequency="d",
        adjustflag="2",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if rs.error_code != "0":
        raise RuntimeError(f"{code}: {rs.error_msg}")
    df = pd.DataFrame(rows, columns=fields.split(","))
    return normalize(df)


def normalize(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    keep = ["date", "open", "high", "low", "close", "volume"]
    df = df[keep].sort_values("date")
    for col in keep[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().to_dict("records")


def window(rows, start, end):
    return [r for r in rows if start <= r["date"] <= end]


def pick(rows, date, field="close"):
    closest = min(rows, key=lambda r: abs(pd.Timestamp(r["date"]) - pd.Timestamp(date)))
    return {"date": closest["date"], "price": round(float(closest[field]), 3)}


def build_case(source_rows, cfg):
    rows = window(source_rows, cfg["start"], cfg["end"])
    marks = []
    for label, date, field, title, text in cfg["marks"]:
        point = pick(rows, date, field)
        marks.append(
            {
                "label": label,
                "date": point["date"],
                "price": point["price"],
                "title": title,
                "text": text,
            }
        )
    return {
        "id": cfg["id"],
        "title": cfg["title"],
        "symbol": cfg["symbol"],
        "name": cfg["name"],
        "type": cfg["type"],
        "period": f'{cfg["start"]} 至 {cfg["end"]}',
        "question": cfg["question"],
        "lesson": cfg["lesson"],
        "trendBefore": cfg["trendBefore"],
        "boundary": cfg["boundary"],
        "confirmation": cfg["confirmation"],
        "failure": cfg["failure"],
        "bars": rows,
        "marks": marks,
    }


def main():
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(login.error_msg)
    sources = {
        "600036": fetch_baostock("sh.600036"),
        "600519": fetch_baostock("sh.600519"),
        "sh000300": fetch_baostock("sh.000300"),
    }
    configs = [
        {
            "id": "cmb-uptrend-continuation-2024",
            "symbol": "600036",
            "name": "招商银行",
            "title": "上涨趋势如何延续：回调不破前低，再突破前高",
            "type": "上涨延续",
            "start": "2024-01-02",
            "end": "2024-05-31",
            "question": "一段底部反弹什么时候从反弹变成趋势？",
            "lesson": "不要只看第一根大阳线。真正重要的是后续回调没有跌回起点，并且再次突破前高。",
            "trendBefore": "前期低位震荡后开始向上推进。",
            "boundary": "回调低点不能跌回前一段启动低点。",
            "confirmation": "重新突破前高后，高点和低点同时抬高，上涨趋势延续。",
            "failure": "跌破回调低点后不能快速收回，延续判断失效。",
            "marks": [
                ["A", "2024-01-18", "low", "趋势起点", "下跌后形成阶段低点，后续开始向上离开。"],
                ["B", "2024-02-08", "high", "第一段推动", "价格快速上冲，说明空头压力被第一次打穿。"],
                ["C", "2024-03-05", "low", "回调检验", "回调没有跌回 A 点，趋势没有被破坏。"],
                ["D", "2024-03-18", "high", "延续确认", "再次突破 B 附近高点，高低点关系转强。"],
                ["E", "2024-04-18", "low", "趋势边界", "这里成为后续上涨结构的防守边界。"],
                ["F", "2024-05-20", "high", "延续后段", "继续创新高，但之后要开始观察是否滞涨。"],
            ],
        },
        {
            "id": "csi300-false-breakout-2024",
            "symbol": "sh000300",
            "name": "沪深300",
            "title": "假突破：突破区间后又跌回，方向没有真正改变",
            "type": "假突破",
            "start": "2024-09-02",
            "end": "2024-11-29",
            "question": "为什么突破不能马上等于新上涨趋势？",
            "lesson": "突破只是离开区间，回踩不跌回去才是确认。快速跌回原区间，说明方向改变失败。",
            "trendBefore": "指数在低位震荡后突然向上突破。",
            "boundary": "突破后的区间上沿必须守住。",
            "confirmation": "回踩不跌回旧区间，才算趋势延续确认。",
            "failure": "放量跌回旧区间，突破判断失效，重新按震荡处理。",
            "marks": [
                ["A", "2024-09-18", "low", "震荡低点", "原走势仍在低位拉扯。"],
                ["B", "2024-09-30", "high", "向上突破", "强力上冲离开原震荡区。"],
                ["C", "2024-10-08", "high", "情绪高点", "继续冲高，但追涨风险迅速抬升。"],
                ["D", "2024-10-17", "low", "回踩边界", "第一次检验突破是否有效。"],
                ["E", "2024-11-14", "low", "跌回区间", "跌回原突破区附近，说明新趋势不稳。"],
                ["F", "2024-11-29", "close", "重新等待", "方向没有继续确认，后续按震荡观察。"],
            ],
        },
        {
            "id": "moutai-downtrend-continuation-2024",
            "symbol": "600519",
            "name": "贵州茅台",
            "title": "下跌趋势如何延续：反弹不过前高，再跌破前低",
            "type": "下跌延续",
            "start": "2024-05-06",
            "end": "2024-09-30",
            "question": "为什么有些反弹只是反弹，不是反转？",
            "lesson": "反转需要破坏原下跌结构。反弹过不了前高，再跌破前低，说明下跌趋势仍在。",
            "trendBefore": "原方向是震荡下行，高点逐步降低。",
            "boundary": "反弹必须站上前高，才有资格讨论反转。",
            "confirmation": "反弹失败后再次跌破前低，下跌延续确认。",
            "failure": "若价格重新站上前高并回踩不破，下跌延续判断失效。",
            "marks": [
                ["A", "2024-05-06", "high", "下跌前高", "后续反弹需要突破这里，才算破坏下降结构。"],
                ["B", "2024-06-24", "low", "第一段下跌", "形成新低，下跌结构明确。"],
                ["C", "2024-07-12", "high", "反弹不过", "反弹没有越过 A，仍只是下跌中的反抽。"],
                ["D", "2024-08-05", "low", "跌破确认", "再次跌破 B 附近低点，下跌延续。"],
                ["E", "2024-08-28", "high", "第二次反抽", "反抽仍未改变低高点关系。"],
                ["F", "2024-09-18", "low", "延续后段", "继续在低位运行，等待新的止跌结构。"],
            ],
        },
        {
            "id": "csi300-reversal-confirmation-2025",
            "symbol": "sh000300",
            "name": "沪深300",
            "title": "反转确认：先破坏下跌，再形成新的高低点关系",
            "type": "反转确认",
            "start": "2025-04-01",
            "end": "2025-09-30",
            "question": "一段上涨什么时候不再只是反弹？",
            "lesson": "先看是否收复下降段压力，再看回调是否不破前低，最后看能否再次突破。",
            "trendBefore": "前期调整后，指数尝试从低位修复。",
            "boundary": "回调低点不能跌回前一段低点。",
            "confirmation": "突破后回踩不破，再创新高，反转才更可信。",
            "failure": "跌回启动低点下方，反转判断失效。",
            "marks": [
                ["A", "2025-04-07", "low", "调整低点", "原下跌段的阶段低点。"],
                ["B", "2025-05-13", "high", "第一段修复", "开始收复前期下跌空间。"],
                ["C", "2025-06-23", "low", "回踩不破", "回调没有跌破 A，结构开始转稳。"],
                ["D", "2025-07-24", "high", "突破确认", "重新突破 B，高低点关系转为抬高。"],
                ["E", "2025-08-21", "low", "新边界", "这里成为上涨延续的防守线。"],
                ["F", "2025-09-30", "close", "趋势延续", "保持在新结构内运行。"],
            ],
        },
    ]
    cases = [build_case(sources[c["symbol"]], c) for c in configs]
    payload = {
        "builtAt": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
        "source": "Baostock 前复权日线；包含 A 股个股与沪深300指数",
        "caseUnit": "连续行情窗口，不以单日 K 线作为案例",
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} cases={len(cases)}")
    bs.logout()


if __name__ == "__main__":
    main()
