# 投资研究本地数据仓库

定位：保存每次取数、估值试算、模型输入和结论变更记录，供 Codex、Claude Code 或其他本地工具复用。

前端仪表盘是**人看的决策界面**，数据库是**机器用的可追溯底座**。归档工作簿只作历史底稿；日常数据更新不再依赖 Excel、Word 或 WPS。

## 文件

| 文件 | 用途 |
|---|---|
| `investment_research.sqlite` | 本地 SQLite 数据库 |
| `schema.sql` | 数据库结构定义（唯一权威） |
| `rebuild_db.py` | 删旧库、按 `schema.sql` 重建、全量装载已核验数据、跑验证 |

重建（仅在需要从头恢复数据库时使用，日常不要跑）：

```bash
python3 05_数据仓库/rebuild_db.py          # 重建并验证
python3 05_数据仓库/rebuild_db.py --no-verify
```

`rebuild_db.py` 中的数据常量即为迁移时的基准来源。它是破坏性重建脚本，日常更新应使用父目录下的：

```bash
python3 ../update_stock_valuations.py
python3 ../update_market_temperature.py
python3 ../build_mobile_dashboard.py
```

## 表清单与用途

| 表 | 保存什么 | 季度更新时 |
|---|---|---|
| `securities` | 股票、市场、币种、商业类型；含仅作 peer 的同业（如 `002463.SZ` 沪电股份） | 可选 |
| `data_sources` | 来源、类型、可靠性、更新频率、是否官方、覆盖区间、交叉验证结论 | 可选 |
| `raw_observations` | 财报、经营、分部等原始观测值；`value` 可空（接口异常已剔除时保留占位行并在 `source_note` 说明） | **必须** |
| `price_snapshots` | 每日价格、市值、PE、PB、股息率 | **必须**（日更也写这张） |
| `model_versions` | 模型名称、版本、SPEC 章节、`status`（active/deprecated）、废弃原因、替代模型 | 模型修订时**必须** |
| `valuation_runs` | 每次估值运行的日期、模型、价格、实用/严格区间、结论、两维置信度 | **必须** |
| `valuation_inputs` | 本次用到的关键参数及其 `fact`/`assumption`/`derived` 属性 | **必须** |
| `scenario_results` | 悲观/中性/乐观或不同要求回报率下的结果 | **必须** |
| `profit_basis_tiers` | 多口径利润分层（已实现/历史中周期/升级后中周期/预测），带证据等级 A/B/C 与推导过程 | 周期股或口径升级中的公司**必须** |
| `assumption_change_log` | 参数变化、原因、证据、关联 run；`security_id` 可空以容纳市场级口径变更 | 假设变化时**必须** |
| `market_position_runs` | 市场估值与仓位模型运行结果，含 `eps_basis`、PB/PE 中位、长期 ROE、是否已校准、终局 PE | 市场模型更新时**必须** |
| `crisis_metric_observations` | VIX、HIBOR 隔夜−1M 利差、信用利差等危机指标及阈值 | 可选（阈值未校准须写 `state='未校准'`） |

视图：

| 视图 | 用途 |
|---|---|
| `v_current_positions` | 每只证券**最新一次** run 的 ticker/name/price/实用区间/严格区间/两维置信度/结论 |
| `latest_valuation_runs` | 最新估值日的完整 run 明细（兼容旧查询） |

## 核心约束（写入前必读）

1. `raw_observations` 对 `(security_id, metric_code, period_end, frequency)` 唯一 —— 同一期同一指标只有一行。重报要么 `update` 并置 `is_restated=1`，要么先删后插。
2. `crisis_metric_observations` 对 `(market_code, metric_code, observation_date)` 唯一。
3. `market_position_runs` 对 `(market_code, valuation_date)` 唯一。
4. `profit_basis_tiers` 对 `(run_id, tier_name)` 唯一，`evidence_grade` 限 `A`/`B`/`C`。
5. `valuation_runs.confidence_earnings` 与 `confidence_multiple` **均为必填**，值域 `高`/`中高`/`中`/`低`。旧的单一 `confidence` 字段保留但可空，只作综合印象，不得单独引用。
6. 估值参数分三类：`fact`＝财报或行情事实，`assumption`＝人工假设，`derived`＝公式推导。终局倍数必须是 `derived` 且在 `formula_note` 写出公式。
7. 不覆盖历史估值记录。新季度、新数据源或新假设都新增一条 `valuation_runs`。
8. 废弃口径不删记录，改 `model_versions.status='deprecated'`，写 `deprecated_reason` 并指向 `superseded_by_id`。

## 每季度更新的标准 SQL 流程

顺序不可颠倒：`raw_observations` → `valuation_runs` → `valuation_inputs` → `scenario_results` / `profit_basis_tiers` → `assumption_change_log`。

**第 0 步：确认数据源存在**

```sql
select id, source_name, frequency, is_official, coverage_end
from data_sources where source_name = '东方财富F10/datacenter';
```

**第 1 步：写入原始观测（幂等）**

```sql
insert into raw_observations
  (security_id, metric_code, metric_name, period_end, frequency,
   value, unit, source_id, source_note, fetched_at)
values
  ((select id from securities where ticker = '300476.SZ'),
   'net_profit_parent', '归母净利润', '2026-06-30', 'quarterly',
   :value, '亿元',
   (select id from data_sources where source_name = '东方财富F10/datacenter'),
   :note, date('now'))
on conflict(security_id, metric_code, period_end, frequency) do update set
  value = excluded.value,
  fetched_at = excluded.fetched_at,
  is_restated = 1,
  source_note = excluded.source_note;
```

**第 2 步：新建一次估值运行**

```sql
insert into valuation_runs
  (security_id, valuation_date, model_version_id, run_type, price_at_run, currency,
   practical_low, practical_high, strict_low, strict_high,
   conclusion, confidence_earnings, confidence_multiple, workbook_path)
values
  ((select id from securities where ticker = '02476.HK'),
   :valuation_date,
   (select id from model_versions
     where model_code = 'shenghong_profit_path_strict' and version_label = 'v1'
       and status = 'active'),
   'full', :price, 'HKD', :pl, :ph, :sl, :sh, :conclusion, '低', '低', null);
```

**第 3 步：写入本次输入**（`:run_id` 取上一步 `last_insert_rowid()`）

```sql
insert into valuation_inputs
  (run_id, input_name, input_value, unit, input_type, source_note, formula_note)
values
  (:run_id, '2026E利润', 62.0, '亿元', 'assumption', '景气预测口径，非正常化利润',
   '2026Q1归母12.88亿按2025季节性(21.4%)外推'),
  (:run_id, '公式终局PE', 18.54, '倍', 'derived', '稳定期推导，非手填',
   'payout×(1+g)/(k−g)，g=3%、ROE=30%、k=8%');
```

**第 4 步：写入情景与利润分层**

```sql
insert into scenario_results
  (run_id, scenario_name, target_return, growth_path,
   terminal_metric_name, terminal_metric_value, fair_value, expected_irr, notes)
values (:run_id, '中性', 0.10, :path, '终局PE', 18.54, :fv, :irr, :notes);

insert into profit_basis_tiers
  (run_id, tier_name, tier_amount, unit, evidence_grade, derivation, implied_multiple)
values (:run_id, '2026E景气预测利润', 62.0, '亿元', 'B',
        '2026Q1归母12.88亿按2025季节性(21.4%)外推≈60.3亿', 25.2);
```

**第 5 步：假设有变则记录变更**

```sql
insert into assumption_change_log
  (security_id, market_code, change_date, changed_field,
   old_value, new_value, reason, evidence_summary, related_run_id)
values ((select id from securities where ticker = '02476.HK'), null, date('now'),
        '终局PE', '22（手填）', '12.4（H模型推导）',
        '手填无推导无来源', '成熟期锚集中10–13倍', :run_id);
```

市场级口径变更把 `security_id` 留空、写 `market_code`：

```sql
insert into assumption_change_log
  (security_id, market_code, change_date, changed_field, old_value, new_value, reason, evidence_summary)
values (null, 'A股', date('now'), '指数EPS口径', '当期TTM 319.2', 'PB—ROE正常化 359.8',
        '当前PB在历史中位而PE在86分位，盈利被压低',
        '蛋卷序列＋中证官方PE交叉验证偏差0.10%');
```

## 常用查询

**查某只证券的最新结论**

```sql
select ticker, name, price, practical_range, strict_range,
       confidence_earnings, confidence_multiple, conclusion
from v_current_positions
where ticker = '02476.HK';
```

去掉 `where` 即得三只证券当前全景。

**查某个参数的历史变化**

```sql
select vr.valuation_date, vi.input_value, vi.unit, vi.input_type, vi.formula_note
from valuation_inputs vi
join valuation_runs vr on vr.id = vi.run_id
join securities s on s.id = vr.security_id
where s.ticker = '600519.SH' and vi.input_name = '公式终局PE'
order by vr.valuation_date;

-- 配合变更日志看"为什么改"
select change_date, changed_field, old_value, new_value, reason, evidence_summary
from assumption_change_log
where security_id = (select id from securities where ticker = '600519.SH')
order by change_date desc;
```

**查某次 run 的全部输入**

```sql
select input_type, input_name, input_value, unit, source_note, formula_note
from valuation_inputs
where run_id = :run_id
order by case input_type when 'fact' then 1 when 'derived' then 2 else 3 end, input_name;

select scenario_name, target_return, fair_value, expected_irr, notes
from scenario_results where run_id = :run_id;

select tier_name, tier_amount, unit, evidence_grade, implied_multiple, derivation
from profit_basis_tiers where run_id = :run_id order by tier_amount;
```

**查某只证券某指标的年度序列 / 中位数**

```sql
select period_end, value
from raw_observations
where security_id = (select id from securities where ticker = '300476.SZ')
  and metric_code = 'roic' and frequency = 'annual'
order by period_end;
```

**查哪些模型口径已废弃**

```sql
select m.model_code, m.version_label, m.deprecated_reason, s.model_code as superseded_by
from model_versions m
left join model_versions s on s.id = m.superseded_by_id
where m.status = 'deprecated';
```

**查市场仓位与危机指标**

```sql
select market_code, index_name, index_level, normalized_eps, eps_basis,
       fair_index_level, current_to_fair_ratio, suggested_position, calibrated, conclusion
from market_position_runs
where valuation_date = '2026-07-31';

select market_code, metric_code, value, unit, state, notes
from crisis_metric_observations
where observation_date = '2026-07-31';
```

## 哪些表必须写、哪些可选

| 场景 | 必须写 | 可选 |
|---|---|---|
| 日更行情 | `price_snapshots` | `valuation_runs` 用 `run_type='price_only'` 刷新估值位置 |
| 季度财报 | `raw_observations`、`valuation_runs`、`valuation_inputs`、`scenario_results`；周期股另加 `profit_basis_tiers`；假设变化时 `assumption_change_log` | `data_sources`（新来源时必写） |
| 模型修订 | 新增 `model_versions` 或改版本号；旧版本置 `status='deprecated'` 并填 `deprecated_reason`、`superseded_by_id` | — |
| 市场与仓位复核 | `market_position_runs`；`eps_basis` 必填并说明是否 `calibrated` | `crisis_metric_observations`（阈值未校准须写 `state='未校准'`） |

绝不允许：在旧模型版本下覆盖历史结果；用压力测试值作为行动阈值；把当期 TTM 数字写成"正常化"；手填终局倍数而不写 `formula_note`。
