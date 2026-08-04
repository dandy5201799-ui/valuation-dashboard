-- 投资研究本地数据仓库 结构定义
-- 版本：2026-08-03（第二轮审查后重构）
-- 重建方式：python3 05_数据仓库/rebuild_db.py

pragma foreign_keys = on;

create table if not exists securities (
  id integer primary key,
  ticker text not null unique,
  name text not null,
  market text not null,
  currency text not null,
  business_type text not null,
  active integer not null default 1,
  created_at text not null default current_timestamp
);

create table if not exists data_sources (
  id integer primary key,
  source_name text not null,
  source_type text not null,
  source_url text,
  reliability_level text not null default 'unknown',
  frequency text,
  is_official integer not null default 0,
  coverage_start text,
  coverage_end text,
  cross_validated_note text,
  notes text,
  created_at text not null default current_timestamp,
  unique(source_name)
);

-- value 允许为 NULL：接口返回异常已剔除的观测保留占位行，并在 source_note 说明原因。
create table if not exists raw_observations (
  id integer primary key,
  security_id integer,
  metric_code text not null,
  metric_name text not null,
  period_end text,
  report_date text,
  frequency text not null,
  value real,
  unit text not null,
  source_id integer,
  source_payload_hash text,
  source_note text,
  fetched_at text,
  is_restated integer not null default 0,
  created_at text not null default current_timestamp,
  unique(security_id, metric_code, period_end, frequency),
  foreign key (security_id) references securities(id),
  foreign key (source_id) references data_sources(id)
);

create index if not exists idx_raw_observations_lookup
on raw_observations(security_id, metric_code, period_end, report_date);

create table if not exists price_snapshots (
  id integer primary key,
  security_id integer not null,
  trade_date text not null,
  close_price real not null,
  currency text not null,
  market_cap real,
  pe_ttm real,
  pb real,
  dividend_yield real,
  source_id integer,
  created_at text not null default current_timestamp,
  unique(security_id, trade_date),
  foreign key (security_id) references securities(id),
  foreign key (source_id) references data_sources(id)
);

create table if not exists model_versions (
  id integer primary key,
  model_code text not null,
  model_name text not null,
  version_label text not null,
  description text not null,
  spec_section text,
  status text not null default 'active' check (status in ('active', 'deprecated')),
  deprecated_reason text,
  superseded_by_id integer,
  created_at text not null default current_timestamp,
  unique(model_code, version_label),
  foreign key (superseded_by_id) references model_versions(id)
);

-- confidence 拆为盈利口径置信度与倍数口径置信度；confidence 仅保留为可空的综合值。
create table if not exists valuation_runs (
  id integer primary key,
  security_id integer not null,
  valuation_date text not null,
  model_version_id integer not null,
  run_type text not null,
  price_at_run real,
  currency text not null,
  practical_low real,
  practical_high real,
  strict_low real,
  strict_high real,
  conclusion text,
  confidence_earnings text not null check (confidence_earnings in ('高', '中高', '中', '低')),
  confidence_multiple text not null check (confidence_multiple in ('高', '中高', '中', '低')),
  confidence text,
  summary text,
  workbook_path text,
  created_by text not null default 'codex',
  valuation_status text,
  created_at text not null default current_timestamp,
  foreign key (security_id) references securities(id),
  foreign key (model_version_id) references model_versions(id)
);

create index if not exists idx_valuation_runs_security_date
on valuation_runs(security_id, valuation_date);

create table if not exists valuation_inputs (
  id integer primary key,
  run_id integer not null,
  input_name text not null,
  input_value real not null,
  unit text not null,
  input_type text not null check (input_type in ('fact', 'assumption', 'derived')),
  source_observation_id integer,
  source_note text,
  formula_note text,
  created_at text not null default current_timestamp,
  foreign key (run_id) references valuation_runs(id) on delete cascade,
  foreign key (source_observation_id) references raw_observations(id)
);

-- 多口径利润分层：周期股/口径升级中的公司无法用单一"正常化利润"表达时使用。
create table if not exists profit_basis_tiers (
  id integer primary key,
  run_id integer not null,
  tier_name text not null,
  tier_amount real,
  unit text,
  evidence_grade text check (evidence_grade in ('A', 'B', 'C')),
  derivation text,
  implied_multiple real,
  note text,
  created_at text not null default current_timestamp,
  unique(run_id, tier_name),
  foreign key (run_id) references valuation_runs(id) on delete cascade
);

create table if not exists scenario_results (
  id integer primary key,
  run_id integer not null,
  scenario_name text not null,
  target_return real,
  growth_path text,
  terminal_metric_name text,
  terminal_metric_value real,
  fair_value real,
  expected_irr real,
  dividend_value real,
  notes text,
  foreign key (run_id) references valuation_runs(id) on delete cascade
);

-- security_id 可空：市场级（沪深300/恒生/标普500）口径变更没有对应证券。
create table if not exists assumption_change_log (
  id integer primary key,
  security_id integer,
  market_code text,
  change_date text not null,
  changed_field text not null,
  old_value text,
  new_value text,
  reason text not null,
  evidence_summary text,
  related_run_id integer,
  created_at text not null default current_timestamp,
  foreign key (security_id) references securities(id),
  foreign key (related_run_id) references valuation_runs(id)
);

create table if not exists market_position_runs (
  id integer primary key,
  market_code text not null,
  valuation_date text not null,
  index_name text not null,
  index_level real,
  normalized_eps real,
  fair_index_level real,
  current_to_fair_ratio real,
  suggested_position real,
  eps_basis text check (eps_basis in ('current_ttm', 'normalized_pb_roe', 'third_party_normalized')),
  pb_current real,
  pb_median real,
  pe_median real,
  long_run_roe real,
  calibrated integer not null default 0,
  terminal_pe real,
  crisis_state text,
  conclusion text,
  confidence text,
  workbook_path text,
  created_at text not null default current_timestamp,
  unique(market_code, valuation_date)
);

create table if not exists crisis_metric_observations (
  id integer primary key,
  market_code text not null,
  metric_code text not null,
  observation_date text not null,
  value real not null,
  unit text not null,
  state text,
  source_id integer,
  notes text,
  created_at text not null default current_timestamp,
  unique(market_code, metric_code, observation_date),
  foreign key (source_id) references data_sources(id)
);

-- 市场估值温度（外部表面口径）。由 update_market_temperature.py 每次抓取后 upsert。
-- 与 market_position_runs 的区别：本表只记录「市场表面贵不贵」（PE/PB/CAPE 分位），
-- 不含正常化解释、股债性价比与仓位映射；两者可能给出不同档位，internal_model_agrees
-- 字段即用于记录这种分歧。
create table if not exists market_temperature_runs (
  id integer primary key,
  market_code text not null,
  index_name text not null,
  valuation_date text not null,
  pe real, pb real, dividend_yield real, roe real,
  pe_percentile real, pb_percentile real,
  cape real, cape_percentile real, forward_pe real,
  temperature_level integer not null check (temperature_level between 0 and 4),
  temperature_label text not null,
  divergent integer not null default 0,
  weak_earnings integer not null default 0,
  conclusion text not null,
  internal_model_agrees integer,
  internal_model_note text,
  source text not null,
  source_detail text,
  fetched_at text,
  created_at text not null default current_timestamp,
  unique(market_code, valuation_date)
);

create view if not exists latest_valuation_runs as
select
  vr.*,
  s.ticker,
  s.name,
  s.market
from valuation_runs vr
join securities s on s.id = vr.security_id
where vr.valuation_date = (
  select max(vr2.valuation_date)
  from valuation_runs vr2
  where vr2.security_id = vr.security_id
);

-- 每只证券最新一次估值运行的当前持仓视图。
create view if not exists v_current_positions as
select
  s.ticker,
  s.name,
  s.market,
  vr.valuation_date,
  vr.currency,
  vr.price_at_run                                        as price,
  vr.practical_low,
  vr.practical_high,
  printf('%.6g–%.6g', vr.practical_low, vr.practical_high) as practical_range,
  vr.strict_low,
  vr.strict_high,
  printf('%.6g–%.6g', vr.strict_low, vr.strict_high)       as strict_range,
  vr.confidence_earnings,
  vr.confidence_multiple,
  vr.valuation_status,
  vr.conclusion,
  mv.model_code,
  mv.version_label
from valuation_runs vr
join securities s on s.id = vr.security_id
join model_versions mv on mv.id = vr.model_version_id
where vr.id = (
  select vr2.id
  from valuation_runs vr2
  where vr2.security_id = vr.security_id
  order by vr2.valuation_date desc, vr2.id desc
  limit 1
);
