(function (global) {
  'use strict';
// 缠论自动标记工具 SPEC v0.4 双级别中枢引擎
// 已按 SPEC 落地: R0 包含、R1 分型、R2 笔、R3 线段(特征序列分型)、
// R4 笔中枢(操作级)+线段中枢(背景级)双级别并存、R5 走势、R6 背驰(MACD面积比)、R7-R9 买卖点。
// v0.4 变更: 删除临时兜底状态机制；线段划分改为完整不重叠的窗口扫描算法；
// 中枢延伸与"假突破再进入 vs 真离开"互斥判定；力度 A/C 口径统一为 enterObj/leaveObj 的 MACD 面积比。
// v0.5 变更(E-Z11/E-Z12): 修复离开段判定——!overlaps 不再单独作为离开信号(区分"冲出中枢"
// 与"本就在区间外晃"两种情形)，改为回溯找真正与中枢有接触且端点越界的对象，下界为种子三笔
// 第三笔(允许其兼任离开段)；同时把 center.leaveDir(终点落在中枢哪一侧) 与 leaveObj.dir(对象
// 自身斜率) 显式拆开为两个概念，下游 R5/R6/R7-R9 中所有"离开方向"判断改用 leaveDir。

const RULE_VERSION = 'chan_spec_v0.5_leave_side';

const STRENGTH_WEAK = 0.8;
const STRENGTH_STRONG = 1.2;
const STRENGTH_MIN_AREA_RATIO = 0.5;
const ZS_MEMBER_MIN_OVERLAP = 0.3; // 成员与中枢区间的重叠占自身幅度的最小比例
const ZS_FALSEBREAK_MAX_SPAN = 1.5; // 可被判为"假突破"而降级为成员的最大幅度（相对中枢宽度 zg-zd）
const ZS_SEED_MIN_OVERLAP = 0.15; // 种子三笔各自与区间重叠占自身幅度的最小比例（比成员门槛宽松）

function contains(a, b) {
  return (a.low <= b.low && a.high >= b.high) || (b.low <= a.low && b.high >= a.high);
}

function rawToMergedBar(c) {
  return {
    high: c.high,
    low: c.low,
    idxs: [c.i],
    source_ids: [c.i],
    date: c.date,
    dateEnd: c.date,
    stable: true,
    rule_ids: ['R0', 'O-K01', 'E-K02'],
  };
}

function mergedDirection(prev, last) {
  if (!prev) return null;
  if (last.high > prev.high && last.low > prev.low) return 'up';
  if (last.high < prev.high && last.low < prev.low) return 'down';
  if (last.high > prev.high) return 'up';
  if (last.low < prev.low) return 'down';
  return null;
}

function uniq(arr) {
  return [...new Set(arr.filter(Boolean))];
}

function penLow(b) {
  return Math.min(b.start.price, b.end.price);
}

function penHigh(b) {
  return Math.max(b.start.price, b.end.price);
}

function intervalOverlap(intervals) {
  const low = Math.max(...intervals.map((x) => x.low));
  const high = Math.min(...intervals.map((x) => x.high));
  return high > low ? { low, high } : null;
}

function objectLow(o) {
  return o.range_low ?? o.low ?? Math.min(o.startPrice ?? o.start?.price ?? 0, o.endPrice ?? o.end?.price ?? 0);
}

function objectHigh(o) {
  return o.range_high ?? o.high ?? Math.max(o.startPrice ?? o.start?.price ?? 0, o.endPrice ?? o.end?.price ?? 0);
}

function objectStartIdx(o) {
  return o.startIdx ?? o.start?.idx ?? 0;
}

function objectEndIdx(o) {
  return o.endIdx ?? o.end?.idx ?? 0;
}

function objectStartDate(o) {
  return o.startDate ?? o.start?.date ?? '';
}

function objectEndDate(o) {
  return o.endDate ?? o.end?.date ?? '';
}

// 统一取对象“终点价”：笔用 end.price，线段用 endPrice。
function objectEndPrice(o) {
  return o.endPrice ?? o.end?.price ?? 0;
}

// H2: 对象自身幅度，以及它与 [zd, zg] 中枢区间的重叠占自身幅度的比例。
// 用于把"幅度数倍于区宽、直接穿越中枢"的笔/段排除在"中枢内震荡成员"之外，
// 防止大口袋——一根远超区宽的穿越段不该被算作中枢内成员。
function objSpan(o) {
  return Math.abs(objectHigh(o) - objectLow(o));
}

function overlapRatio(o, zd, zg) {
  const ov = Math.min(objectHigh(o), zg) - Math.max(objectLow(o), zd);
  const sp = objSpan(o);
  return sp > 0 ? Math.max(0, ov) / sp : 0;
}

function hasFeatureGap(a, b) {
  return Math.min(a.high, b.high) < Math.max(a.low, b.low);
}

function normalizeFeatureSequence(features, segDir) {
  const out = [];
  for (const f of features) {
    const next = { ...f };
    if (!out.length) {
      out.push(next);
      continue;
    }
    const last = out[out.length - 1];
    const inclusive = (last.low <= next.low && last.high >= next.high) || (next.low <= last.low && next.high >= last.high);
    if (!inclusive) {
      out.push(next);
      continue;
    }
    // 特征序列内部的包含处理采用当前线段方向的保守工程约定。
    if (segDir === 'up') {
      last.high = Math.max(last.high, next.high);
      last.low = Math.max(last.low, next.low);
    } else {
      last.high = Math.min(last.high, next.high);
      last.low = Math.min(last.low, next.low);
    }
    last.sourcePenIds = uniq([...(last.sourcePenIds || []), next.penId]);
    last.sourcePenIndexes = uniq([...(last.sourcePenIndexes || []), next.penIndex]);
    last.endIdx = next.endIdx;
    last.endDate = next.endDate;
  }
  return out;
}

function featureFractal(features, segDir) {
  // 上线段看向下笔特征序列的顶分型；下线段看向上笔特征序列的底分型。
  const target = segDir === 'up' ? 'top' : 'bottom';
  for (let i = 1; i < features.length - 1; i++) {
    const a = features[i - 1], b = features[i], c = features[i + 1];
    const top = b.high > a.high && b.high > c.high && b.low > a.low && b.low > c.low;
    const bottom = b.high < a.high && b.high < c.high && b.low < a.low && b.low < c.low;
    if ((target === 'top' && top) || (target === 'bottom' && bottom)) {
      const firstSecondGap = hasFeatureGap(a, b);
      return {
        type: target,
        featureIndex: i,
        centerFeature: b,
        firstFeature: a,
        secondFeature: b,
        thirdFeature: c,
        firstSecondGap,
      };
    }
  }
  return null;
}

function mergeInclusion(candles) {
  const merged = [];
  for (const c of candles) {
    if (!(c.low <= Math.min(c.open, c.close) && Math.max(c.open, c.close) <= c.high)) {
      throw new Error(`Invalid OHLC at ${c.date || c.i}`);
    }
    const next = rawToMergedBar(c);
    if (!merged.length) {
      merged.push(next);
      continue;
    }
    const last = merged[merged.length - 1];
    if (contains(last, next)) {
      const dir = mergedDirection(merged[merged.length - 2], last);
      if (!dir) {
        last.status = 'candidate';
        last.rejection_reasons = ['startup_direction_insufficient'];
        last.high = Math.max(last.high, next.high);
        last.low = Math.min(last.low, next.low);
      } else if (dir === 'up') {
        last.high = Math.max(last.high, next.high);
        last.low = Math.max(last.low, next.low);
      } else {
        last.high = Math.min(last.high, next.high);
        last.low = Math.min(last.low, next.low);
      }
      last.direction = dir || 'unknown';
      last.idxs.push(c.i);
      last.source_ids.push(c.i);
      last.dateEnd = c.date;
      last.rule_ids = [...new Set([...(last.rule_ids || []), 'O-K03', 'O-K04'])];
    } else {
      merged.push(next);
    }
  }
  merged.forEach((m, i) => {
    m.mi = i;
    if (!m.id) m.id = `mk${i}`;
    if (!m.status) m.status = 'confirmed';
  });
  return merged;
}

function findFenxing(merged) {
  const raw = [];
  for (let i = 1; i < merged.length - 1; i++) {
    const a = merged[i - 1], b = merged[i], c = merged[i + 1];
    const normalized = !contains(a, b) && !contains(b, c);
    const top = b.high > a.high && b.high > c.high && b.low > a.low && b.low > c.low;
    const bottom = b.high < a.high && b.high < c.high && b.low < a.low && b.low < c.low;
    if ((top || bottom) && normalized) {
      const isTop = top;
      raw.push({
        id: `fx_raw_${raw.length}`,
        mi: i,
        type: isTop ? 'top' : 'bottom',
        price: isTop ? b.high : b.low,
        centerHigh: b.high,
        centerLow: b.low,
        idx: b.idxs[b.idxs.length - 1],
        sourceIdx: b.idxs[b.idxs.length - 1],
        source_ids: [a.id, b.id, c.id],
        idxs: [...b.idxs],
        date: b.dateEnd,
        status: 'confirmed',
        rule_ids: ['R1', 'O-F01', 'E-F02', 'E-F03'],
      });
    }
  }
  const cleaned = [];
  for (const f of raw) {
    if (!cleaned.length) { cleaned.push(f); continue; }
    const last = cleaned[cleaned.length - 1];
    if (last.type === f.type) {
      const better = (f.type === 'top' && f.price >= last.price) || (f.type === 'bottom' && f.price <= last.price);
      if (better) cleaned[cleaned.length - 1] = { ...f, supersedes: last.id, rule_ids: [...f.rule_ids, 'O-B03'] };
      continue;
    }
    if (f.mi - last.mi < 4) {
      f.status = 'withdrawn';
      f.rejection_reasons = ['pen_distance_insufficient'];
      continue;
    }
    cleaned.push(f);
  }
  cleaned.forEach((f, i) => {
    f.id = 'fx' + i;
    // I3: 最后一个分型右侧还没有足够的后续K线验证，随时可能被后面的走势延伸/取代。
    f.provisional = i === cleaned.length - 1;
  });
  return cleaned;
}

function buildBi(fenxingList) {
  const bi = [];
  let i = 0;
  while (i < fenxingList.length - 1) {
    const start = fenxingList[i];
    let end = fenxingList[i + 1];
    if (start.type === end.type) { i++; continue; }
    const centerDistance = end.mi - start.mi;
    const independentCount = centerDistance - 3;
    const top = start.type === 'top' ? start : end;
    const bottom = start.type === 'bottom' ? start : end;
    const priceEligible = top.centerHigh > bottom.centerHigh;
    if (centerDistance < 4 || independentCount < 1 || !priceEligible) {
      i++;
      continue;
    }
    bi.push({
      id: 'bi' + i,
      start, end,
      dir: start.type === 'bottom' ? 'up' : 'down',
      bars: Math.abs(end.idx - start.idx),
      independent_count: independentCount,
      range: Math.abs(end.price - start.price),
      momentum: Math.abs(end.price - start.price) / Math.max(1, end.idx - start.idx),
      status: 'confirmed',
      provisional: false, // 末尾统一按位置覆盖最后一根笔
      rule_ids: ['R2', 'O-B01', 'O-B02', 'O-B03', 'E-B04'],
      evidence: {
        centerDistance,
        independentCount,
        topCenterHigh: top.centerHigh,
        bottomCenterHigh: bottom.centerHigh,
      },
    });
    i++;
  }
  // I3: 最后一根笔的右侧端点(分型)还没有被后续走势充分验证，随时可能被延伸/取代，
  // 不能在它身上冒充"结构已完成"，所以标 provisional=true；其余笔显式 false，避免 undefined。
  if (bi.length) bi[bi.length - 1].provisional = true;
  return bi;
}

// 在 biList[i..] 中寻找线段结束位置。见 SPEC v0.4 §2 + 第二轮修复 F3。
function findSegmentEnd(biList, i, dir) {
  const startPrice = biList[i].start.price;
  for (let k = i + 2; k <= biList.length - 1; k++) {
    const rawFeatures = [];
    for (let idx = i; idx <= k; idx++) {
      const b = biList[idx];
      if (b.dir === dir) continue;
      rawFeatures.push({
        id: `ft_${i}_${idx}`,
        penId: b.id,
        penIndex: idx,
        low: penLow(b),
        high: penHigh(b),
        startIdx: b.start.idx,
        endIdx: b.end.idx,
        startDate: b.start.date,
        endDate: b.end.date,
        sourcePenIds: [b.id],
        sourcePenIndexes: [idx],
      });
    }
    const features = normalizeFeatureSequence(rawFeatures, dir);
    if (features.length >= 3) {
      const ff = featureFractal(features, dir);
      if (ff) {
        const centerPenIndex = Math.min(...ff.centerFeature.sourcePenIndexes);
        const end = centerPenIndex - 1;
        if (end >= i + 2 && (end - i) % 2 === 0) {
          const endPrice = biList[end].end.price;
          const directionOk = dir === 'up' ? endPrice > startPrice : endPrice < startPrice;
          if (directionOk) {
            const featurePenIds = uniq([
              ...(ff.firstFeature.sourcePenIds || []),
              ...(ff.secondFeature.sourcePenIds || []),
              ...(ff.thirdFeature.sourcePenIds || []),
            ]);
            return {
              end,
              featureCase: ff.firstSecondGap ? 'case2_gap' : 'case1_no_gap',
              featurePenIds,
            };
          }
          // 方向自洽门禁未通过：不接受这个分型，继续增大 k 往后找。
        }
        // 分型位置不合法，忽略本次，继续找。
      }
    }
  }
  // 整轮扫描都找不到方向自洽的 end。
  if (i === 0) {
    // 数据起点残段：只含 bi[0] 的 1 笔段，交由后处理标记为 leading_fragment。
    return { end: i, featureCase: 'leading_fragment', featurePenIds: [] };
  }
  // 末段兜底：在所有满足 (idx-i) 为偶数 且 idx<=biList.length-1 的下标中，
  // 选使 biList[idx].end.price 达到极值的那个（天然方向自洽）。
  const candidates = [];
  for (let idx = i + 2; idx <= biList.length - 1; idx++) {
    if ((idx - i) % 2 === 0) candidates.push(idx);
  }
  let end;
  if (candidates.length) {
    end = candidates.reduce((best, idx) => {
      const better = dir === 'up'
        ? biList[idx].end.price > biList[best].end.price
        : biList[idx].end.price < biList[best].end.price;
      return better ? idx : best;
    }, candidates[0]);
  } else {
    end = i;
  }
  return { end, featureCase: 'trailing_extreme', featurePenIds: [] };
}

// R3 线段: buildXianduan —— 完整不重叠划分 + 特征序列分型判定，见 SPEC v0.4 §2。
function buildXianduan(biList) {
  if (!biList || !biList.length) return [];
  const segs = [];
  let i = 0;
  while (i < biList.length) {
    const dir = biList[i].dir;
    const { end, featureCase, featurePenIds } = findSegmentEnd(biList, i, dir);
    const member = biList.slice(i, end + 1);
    const start = biList[i].start;
    const last = biList[end].end;
    const highs = member.flatMap((b) => [b.start.price, b.end.price]);
    const lows = member.flatMap((b) => [b.start.price, b.end.price]);
    segs.push({
      id: 'xd' + segs.length,
      dir,
      biRange: [i, end],
      startIdx: start.idx,
      endIdx: last.idx,
      startPrice: start.price,
      endPrice: last.price,
      startDate: start.date,
      endDate: last.date,
      range_low: Math.min(...lows),
      range_high: Math.max(...highs),
      status: 'candidate',
      provisional: true,
      structural_level: 'xianduan',
      rejection_reasons: [],
      evidence: {
        featureCase,
        featurePenIds,
        penCount: end - i + 1,
        ruleVersion: RULE_VERSION,
      },
    });
    i = end + 1;
  }

  // 后处理：status 判定。
  segs.forEach((seg, n) => {
    const isLast = n === segs.length - 1;
    const { featureCase } = seg.evidence;
    if (featureCase === 'leading_fragment') {
      // F3: 数据起点残段——无法判定方向自洽的完整第一段，单笔占位，不冒充 confirmed。
      seg.status = 'candidate';
      seg.provisional = false;
      seg.rejection_reasons = ['leading_fragment'];
      return;
    }
    if (isLast) {
      seg.status = 'candidate';
      seg.provisional = true;
      seg.rejection_reasons = ['segment_still_forming'];
      return;
    }
    const reasons = [];
    let status;
    if (featureCase === 'case1_no_gap') {
      status = 'confirmed';
    } else if (featureCase === 'case2_gap') {
      const nextSeg = segs[n + 1];
      const nextPenCount = nextSeg.biRange[1] - nextSeg.biRange[0] + 1;
      if (nextPenCount >= 3) {
        status = 'confirmed';
      } else {
        status = 'candidate';
        reasons.push('gap_case_next_segment_too_short');
      }
    } else {
      // trailing_extreme
      status = 'candidate';
      reasons.push('no_feature_fractal_found');
    }
    const directionOk = seg.dir === 'up' ? seg.endPrice > seg.startPrice : seg.endPrice < seg.startPrice;
    if (!directionOk) {
      status = 'candidate';
      reasons.push('direction_inconsistent');
    }
    seg.status = status;
    seg.provisional = false;
    seg.rejection_reasons = reasons;
  });

  return segs;
}

// R4 中枢: buildZhongshuFromObjects —— 笔中枢(操作级)与线段中枢(背景级)公用的双级别构建器。
// 见 SPEC v0.4 §3：完整走完扫描窗口，区分"中枢内波动"与"真离开"，假突破可继续延伸中枢。
function buildZhongshuFromObjects(objects, level) {
  const centers = [];
  let i = 0;
  while (i + 2 < objects.length) {
    const three = [objects[i], objects[i + 1], objects[i + 2]];
    const zg = Math.min(...three.map(objectHigh));
    const zd = Math.max(...three.map(objectLow));
    if (zg <= zd) { i++; continue; }
    // I2: 种子三笔都必须与区间有起码的重叠，否则即使字面满足"三段重叠"，
    // 也可能混进一根幅度数倍于区宽、直接穿越的笔，让中枢的教学含义失真。
    // 门槛比成员的 ZS_MEMBER_MIN_OVERLAP(0.3) 宽松，因为种子本来就负责定义区间，
    // 天然会有一根笔跨度较大（贴着 zg 或 zd 的那根本身重叠比例就低）。
    if (three.some((o) => overlapRatio(o, zd, zg) < ZS_SEED_MIN_OVERLAP)) { i++; continue; }

    let endMember = i + 2;
    let leaveIndex = null;
    let j = i + 3;
    while (j < objects.length) {
      const o = objects[j];
      const oHigh = objectHigh(o);
      const oLow = objectLow(o);
      const endP = objectEndPrice(o);
      const overlaps = oHigh >= zd && oLow <= zg;
      // F1: 离开与否只看终点是否落在区外，不要求整根笔/段的起点也在中枢内
      // （否则"穿越型"笔——从中枢下方直接冲到中枢上方——会被误当成中枢内成员吞掉）。
      const isLeaving = (o.dir === 'up' && endP > zg) || (o.dir === 'down' && endP < zd);
      // H2: 中枢是震荡区间，成员应大体在区间内运行——重叠占自身幅度不足
      // ZS_MEMBER_MIN_OVERLAP 的笔/段（哪怕终点或区间跟中枢有交集）也不配算作"中枢内成员"，
      // 必须被当成候选离开，防止"幅度数倍于区宽、直接穿越"的段被吸收成大口袋。
      const memberEligible = overlapRatio(o, zd, zg) >= ZS_MEMBER_MIN_OVERLAP;
      // 候选离开：要么成员资格不够格，要么按终点口径判定为离开，要么区间干脆整体不再与中枢重叠。
      // 三种触发路径共用同一套"是否被否定"的判定，否则任一分支会绕开修复，
      // 重新产生"小幅越界段被当真离开、真正的大幅反向段被当失败回抽"的同类问题。
      const candidateLeave = !memberEligible || isLeaving || !overlaps;
      if (candidateLeave) {
        const nxt = objects[j + 1];
        const nxtEnd = nxt ? objectEndPrice(nxt) : null;
        // G1: 候选离开段被"否定"不止"回到中枢区间内"一种情形，
        // 还包括"假突破后被下一段反向击穿另一侧"——此时这根小幅假突破段不是真正的离开段，
        // 应降级为中枢成员，让循环在下一段重新判定真正的离开段，而不是把这根假突破当成离开、
        // 把真正的大幅反向段错误地当成"回抽"。
        const negated = nxt && (
          (nxtEnd >= zd && nxtEnd <= zg) ||        // ① 回到中枢区间内
          (o.dir === 'up' && nxtEnd < zd) ||       // ② 向上假突破后反向击穿下沿
          (o.dir === 'down' && nxtEnd > zg)        // ③ 向下假突破后反向击穿上沿
        );
        // H1+H2: 只有"小幅假突破"（自身幅度不超过 ZS_FALSEBREAK_MAX_SPAN 倍区宽）才允许被否定
        // 并降级为成员；幅度数倍于区宽的穿越段，即使后面被反向打回，也不该被吸收进中枢，
        // 而应确认为真离开——否则"能被否定的离开段"和"能被吸收的大口袋段"重合，
        // 幸存的离开段必然方向确认，三买/三卖会退化成永真命题。
        const smallEnough = objSpan(o) <= ZS_FALSEBREAK_MAX_SPAN * (zg - zd);
        // I1: 真正的假突破必然是"从区内探出去再回来"，必须与区间本身有起码的接触；
        // 单看幅度足够小不够——一根整体都在区间之外、幅度又恰好不大的笔（overlapRatio=0）
        // 不该被凭空吸收成成员，那只会平白拉长中枢的时间跨度。
        if (smallEnough && negated && overlapRatio(o, zd, zg) >= 0.1) {
          endMember = j;
          j++;
          continue;
        }
        // E-Z11: !overlaps 有两种截然不同的含义——(a) 这一段真的把价格带出了中枢
        // （自身与区间仍有接触，只是端点冲出去了），(b) 这一段开始之前价格早就已经在
        // 区间外了，它只是在区间外面晃（自身与区间毫无接触）。只有 (a) 才配当"离开段"。
        // 若当前对象是 (b)，往回找真正"扣着中枢边沿冲出去"的那一段——下界是 i+2，
        // 即允许种子三笔的第三笔同时兼任离开段（"框由三笔定义，离开段可以是第三笔"）。
        if (overlaps) {
          leaveIndex = j;
        } else {
          let k = j - 1;
          let found = null;
          while (k >= i + 2) {
            const ok = objects[k];
            const okOverlaps = objectHigh(ok) >= zd && objectLow(ok) <= zg;
            const okEnd = objectEndPrice(ok);
            if (okOverlaps && (okEnd > zg || okEnd < zd)) {
              found = k;
              break;
            }
            k--;
          }
          leaveIndex = found;
        }
        break;
      }
      endMember = j;
      j++;
    }

    const member = objects.slice(i, endMember + 1);
    const leaveObj = leaveIndex != null ? objects[leaveIndex] : null;
    const enterObj = objects[i - 1] || null;
    const pullbackObj = leaveIndex != null ? (objects[leaveIndex + 1] || null) : null;
    const postPullbackObj = leaveIndex != null ? (objects[leaveIndex + 2] || null) : null;

    const allConfirmed = member.every((o) => o.status === 'confirmed');
    const status = allConfirmed ? 'confirmed' : 'candidate';
    const rejection_reasons = allConfirmed ? [] : [`member_${level}_not_confirmed`];
    const provisional = member.some((o) => o.provisional === true) || (leaveObj ? leaveObj.provisional === true : false);

    // E-Z12: leaveDir 描述的是"价格离开到了中枢哪一侧"（终点相对 [zd,zg] 的位置），
    // 不是 leaveObj 自身的涨跌斜率(leaveObj.dir)——两者是不同的概念，可能不相等
    // （例如一根整体在中枢上方、自身向下走的笔，leaveDir 仍是 'up'）。
    // 若终点落在区间内（说明其实没有真正离开），不凭空造方向，leaveDir 记为 null。
    let leaveDir = null;
    if (leaveObj) {
      const leaveEndP = objectEndPrice(leaveObj);
      if (leaveEndP > zg) leaveDir = 'up';
      else if (leaveEndP < zd) leaveDir = 'down';
      else rejection_reasons.push('leave_end_inside_range');
    }

    centers.push({
      id: (level === 'bi' ? 'zsb' : 'zsx') + centers.length,
      level,
      zd,
      zg,
      gg: Math.max(...member.map(objectHigh)),
      dd: Math.min(...member.map(objectLow)),
      memberIds: member.map((o) => o.id),
      memberCount: member.length,
      startIdx: objectStartIdx(objects[i]),
      endIdx: objectEndIdx(objects[endMember]),
      startDate: objectStartDate(objects[i]),
      endDate: objectEndDate(objects[endMember]),
      enterObj,
      leaveObj,
      leaveDir,
      pullbackObj,
      postPullbackObj,
      status,
      provisional,
      structural_level: level === 'bi' ? 'bi_zhongshu' : 'xianduan_zhongshu',
      source_kind: level,
      rejection_reasons,
      evidence: {
        zdFormula: 'max(member lows)',
        zgFormula: 'min(member highs)',
        ruleVersion: RULE_VERSION,
      },
    });

    i = leaveIndex != null ? leaveIndex : endMember + 1;
  }
  return centers;
}

function buildAllZhongshu(xianduanList, biList) {
  return {
    bi: buildZhongshuFromObjects(biList || [], 'bi'),
    xianduan: buildZhongshuFromObjects((xianduanList || []).filter((x) => x.status === 'confirmed'), 'xianduan'),
  };
}

// 薄兼容层：旧调用方只取笔中枢。
function buildZhongshu(xianduanList, biList) {
  return buildAllZhongshu(xianduanList, biList).bi;
}

// R5 走势: computeTrendSegments —— 首个中枢 trend='pending'，不得继承第二个的方向。
function computeTrendSegments(centers) {
  if (!centers || !centers.length) return [];
  const out = [];
  for (let i = 0; i < centers.length; i++) {
    const cur = centers[i];
    const leaveObj = cur.leaveObj;
    const base = {
      centerId: cur.id,
      status: cur.status,
      zoneStartIdx: cur.startIdx,
      zoneEndIdx: cur.endIdx,
      leaveStartIdx: leaveObj ? objectStartIdx(leaveObj) : null,
      leaveEndIdx: leaveObj ? objectEndIdx(leaveObj) : null,
      startDate: cur.startDate,
      endDate: cur.endDate,
    };
    if (i === 0) {
      out.push({ ...cur, ...base, trend: 'pending' });
      continue;
    }
    const prev = centers[i - 1];
    let trend;
    if (cur.zd > prev.zg) trend = 'up';
    else if (cur.zg < prev.zd) trend = 'down';
    else trend = 'range';
    const status = prev.status === 'confirmed' && cur.status === 'confirmed' && trend !== 'range' ? 'confirmed' : cur.status;
    out.push({ ...cur, ...base, trend, status });
  }
  return out;
}

function computeMacd(candles, shortN = 12, longN = 26, signalN = 9) {
  const out = [];
  let emaShort = null, emaLong = null, dea = null;
  const aS = 2 / (shortN + 1), aL = 2 / (longN + 1), aD = 2 / (signalN + 1);
  for (const c of candles || []) {
    const close = c.close;
    emaShort = emaShort == null ? close : emaShort * (1 - aS) + close * aS;
    emaLong = emaLong == null ? close : emaLong * (1 - aL) + close * aL;
    const dif = emaShort - emaLong;
    dea = dea == null ? dif : dea * (1 - aD) + dif * aD;
    const hist = 2 * (dif - dea);
    out.push({ idx: c.i, date: c.date, close, dif, dea, hist });
  }
  return out;
}

function macdArea(macd, startIdx, endIdx, dir) {
  const from = Math.min(startIdx, endIdx);
  const to = Math.max(startIdx, endIdx);
  const items = (macd || []).filter((m) => m.idx > from && m.idx <= to);
  if (!items.length) return { area: null, bars: 0, reason: 'no_macd_points' };
  const area = items.reduce((sum, m) => sum + (dir === 'up' ? Math.max(m.hist, 0) : Math.max(-m.hist, 0)), 0);
  return { area, bars: items.length };
}

function computeStrength(biList, candles) {
  const macd = computeMacd(candles || []);
  const byPen = {};
  for (const b of biList) {
    const priceMove = Math.abs(b.end.price - b.start.price);
    const bars = Math.max(1, Math.abs(b.end.idx - b.start.idx));
    const macdInfo = macdArea(macd, b.start.idx, b.end.idx, b.dir);
    byPen[b.id] = {
      biId: b.id,
      dir: b.dir,
      priceMove,
      bars,
      speed: priceMove / bars,
      macdArea: macdInfo.area,
      macdBars: macdInfo.bars,
      status: macdInfo.area == null ? 'insufficient' : 'computed',
      rule_ids: ['R10', 'R12', 'E-DV02'],
    };
  }
  return { macd, byPen };
}

// R12 力度: computeTrendStrength —— 取代逐笔力度，用同向的"进入段/前一中枢离开段" vs 本中枢
// leaveObj(C) 做 MACD 面积比。
// F2: 新增 objects（该级别的全量对象数组，笔中枢传 biList，线段中枢传 xianduanList）用于计算
// MACD 面积中位数基准，防止用一个几乎无动能的段做分母，产出虚假的"力度增强/减弱"结论。
// H3: 参照段三级选取——A/C 方向相反时(中枢往往起于反向的一笔)，enterObj 恒不可比，
// 改为回溯前一个中枢的 leaveObj（连续两个同向推动段才是"趋势力度"的本意）。
function computeTrendStrength(centers, candles, objects) {
  const macd = computeMacd(candles || []);
  const areasAll = (objects || [])
    .map((o) => macdArea(macd, objectStartIdx(o), objectEndIdx(o), o.dir).area)
    .filter((a) => a != null && a > 0)
    .sort((a, b) => a - b);
  const medianArea = areasAll.length ? areasAll[Math.floor(areasAll.length / 2)] : 0;
  const byCenter = {};
  const list = centers || [];
  for (let ci = 0; ci < list.length; ci++) {
    const center = list[ci];
    const C = center.leaveObj;
    if (!C) {
      byCenter[center.id] = {
        status: 'insufficient',
        reason: '缺少离开段',
        label: '力度不可比（结构未完成）',
      };
      continue;
    }
    const A = center.enterObj;
    let ref = null, basis = null;
    if (A && A.dir === C.dir) {
      ref = A;
      basis = 'enter_vs_leave';
    } else {
      // 次选：按 centers 数组顺序回溯，跳过没有 leaveObj 的中枢，取第一个有 leaveObj 的中枢；
      // 只有当它的方向与 C 一致时才采用，否则视为无同向参照段。
      for (let pi = ci - 1; pi >= 0; pi--) {
        const prevLeave = list[pi].leaveObj;
        if (!prevLeave) continue;
        if (prevLeave.dir === C.dir) {
          ref = prevLeave;
          basis = 'prev_leave_vs_leave';
        }
        break;
      }
    }
    if (!ref) {
      byCenter[center.id] = {
        status: 'incomparable',
        reason: '无同向参照段',
        label: '趋势力度不可比（无同向参照段，只能作盘整背驰观察）',
      };
      continue;
    }
    const infoRef = macdArea(macd, objectStartIdx(ref), objectEndIdx(ref), ref.dir);
    const infoC = macdArea(macd, objectStartIdx(C), objectEndIdx(C), C.dir);
    const areaA = infoRef.area, areaC = infoC.area;
    const barsA = infoRef.bars, barsC = infoC.bars;
    if (areaA == null || areaA <= 0 || barsA < 3 || areaC == null || areaC <= 0 || barsC < 3) {
      byCenter[center.id] = {
        status: 'insufficient',
        reason: 'MACD样本不足',
        label: '力度不可比（样本不足）',
        basis,
      };
      continue;
    }
    // F2: 分母/分子面积不能小到失去参考意义——用同级别全量对象的 MACD 面积中位数做基准门槛。
    if (areaA < STRENGTH_MIN_AREA_RATIO * medianArea || areaC < STRENGTH_MIN_AREA_RATIO * medianArea) {
      byCenter[center.id] = {
        status: 'insufficient',
        reason: '进入段或离开段MACD动能过小，比值不具参考意义',
        label: '力度不可比（动能样本过弱）',
        basis,
      };
      continue;
    }
    const ratio = areaC / areaA;
    let verdict;
    if (ratio < STRENGTH_WEAK) verdict = 'weak';
    else if (ratio > STRENGTH_STRONG) verdict = 'strong';
    else verdict = 'flat';
    // E-Z12: 这里生成的是"离开中枢方向"的中文标签，要按 center.leaveDir（终点落在
    // 中枢哪一侧），不是 leaveObj 自身斜率(C.dir)——两者语义不同，可能不一致。
    // leaveDir 为 null（终点其实还在区间内）时不编造方向措辞。
    if (!center.leaveDir) {
      byCenter[center.id] = {
        status: 'incomparable',
        reason: '离开段终点仍在中枢区间内，无离开方向',
        label: '力度不可比（无离开方向）',
        basis,
      };
      continue;
    }
    const labels = center.leaveDir === 'up'
      ? { weak: '上涨力度减弱', strong: '上涨力度增强', flat: '上涨力度持平' }
      : { weak: '下跌力度减弱', strong: '下跌力度增强', flat: '下跌力度持平' };
    const detail = basis === 'prev_leave_vs_leave'
      ? `对比上一个中枢的同向离开段（${objectStartDate(ref)}~${objectEndDate(ref)}）`
      : `对比本中枢的进入段（${objectStartDate(ref)}~${objectEndDate(ref)}）`;
    byCenter[center.id] = {
      status: 'comparable',
      dir: C.dir,
      basis,
      ratio,
      verdict,
      label: labels[verdict],
      detail,
      areaA,
      areaC,
      barsA,
      barsC,
      A: { id: ref.id, startDate: objectStartDate(ref), endDate: objectEndDate(ref) },
      C: { id: C.id, startDate: objectStartDate(C), endDate: objectEndDate(C) },
      refObj: ref, // 内部使用：computeBeichi 判定 priceExtends 需要完整对象（basis 可能不是 enterObj）
      leaveStartIdx: objectStartIdx(C),
      leaveEndIdx: objectEndIdx(C),
    };
  }
  return { byCenter, macd };
}

// R6 背驰: computeBeichi —— 仅在 comparable 且 ratio < STRENGTH_WEAK 且价格确实创出新极值时产出。
// F2: objects 透传给 computeTrendStrength 用于动能中位数基准门槛。
function computeBeichi(centers, candles, objects) {
  const { byCenter } = computeTrendStrength(centers, candles, objects);
  const flags = [];
  for (const center of centers || []) {
    const info = byCenter[center.id];
    if (!info || info.status !== 'comparable' || info.ratio >= STRENGTH_WEAK) continue;
    // E-Z12: priceExtends 问的是"价格是否真的探出了中枢所在的那一侧"，这要看
    // center.leaveDir（终点相对区间的一侧），不是 leaveObj 自身的涨跌斜率(C.dir)。
    // leaveDir 为 null 说明离开段的终点其实还在区间内，谈不上背驰。
    if (!center.leaveDir) continue;
    // H3: 参照段可能是 enterObj，也可能是前一中枢的 leaveObj（basis='prev_leave_vs_leave'），
    // priceExtends 必须用实际参照对象的极值，不能再假设一定是 center.enterObj。
    const A = info.refObj;
    const C = center.leaveObj;
    const priceExtends = center.leaveDir === 'up'
      ? objectHigh(C) > Math.max(center.zg, objectHigh(A))
      : objectLow(C) < Math.min(center.zd, objectLow(A));
    if (!priceExtends) continue;
    const status = (center.status === 'confirmed' && !center.provisional) ? 'confirmed' : 'candidate';
    flags.push({
      id: 'bc' + flags.length,
      zsId: center.id,
      level: center.level,
      dir: center.leaveDir,
      basis: info.basis,
      idx: objectEndIdx(C),
      date: objectEndDate(C),
      price: objectEndPrice(C),
      ratio: info.ratio.toFixed(2),
      areaA: info.areaA,
      areaC: info.areaC,
      status,
      rejection_reasons: status === 'confirmed' ? [] : ['leave_segment_or_center_still_forming'],
      evidence: {
        proxy: 'macd_area_ratio',
        basis: info.basis,
        enterObjId: A.id,
        exitObjId: C.id,
        areaA: info.areaA,
        areaC: info.areaC,
        ratio: info.ratio,
        priceExtends: true,
      },
      rule_ids: ['R6', 'O-DV01', 'E-DV02'],
    });
  }
  return flags;
}

// R7-R9 买卖点: deriveSignals —— 完全基于中枢自带的 enterObj/leaveObj/pullbackObj/postPullbackObj，不用数组下标。
function deriveSignals(centers, beichiFlags) {
  const signals = [];
  const beichiByZs = {};
  for (const f of beichiFlags || []) {
    if (!beichiByZs[f.zsId]) beichiByZs[f.zsId] = f;
  }

  for (const center of centers || []) {
    const C = center.leaveObj;
    const flag = beichiByZs[center.id];
    let sig1 = null;

    // 1B/1S
    // E-Z12: isBuy 问的是"价格离开到了中枢下方还是上方"，要用 center.leaveDir，
    // 不是 leaveObj 自身斜率(C.dir)——leaveDir 为 null 时不生成信号，不回退到斜率。
    if (flag && C && center.leaveDir) {
      const isBuy = center.leaveDir === 'down';
      sig1 = {
        id: 'sig-1' + (isBuy ? 'B' : 'S') + center.id,
        type: isBuy ? '1B' : '1S',
        dir: isBuy ? 'buy' : 'sell',
        zsId: center.id,
        level: center.level,
        idx: objectEndIdx(C),
        date: objectEndDate(C),
        price: objectEndPrice(C),
        status: flag.status,
        stage: 'leave',
        // 一买/一卖的失效位是背驰离开段自身的极值：跌破该低点则底背驰被证伪，涨破该高点则顶背驰被证伪。
        // 不能用中枢边界——背驰点往往离中枢很远，用边界会让信号一产生就"已失效"。
        boundary: isBuy ? objectLow(C) : objectHigh(C),
        rejection_reasons: flag.status === 'confirmed' ? [] : ['divergence_still_forming'],
        evidence: { beichiId: flag.id, exitObjId: C.id },
      };
      signals.push(sig1);
    }

    // 2B/2S
    if (sig1 && center.pullbackObj) {
      const postPullbackObj = center.postPullbackObj;
      // E-Z12: 这里要问"回踩后这一段是不是延续了离开中枢的那一侧方向"，用 center.leaveDir 比对。
      if (postPullbackObj && center.leaveDir && postPullbackObj.dir === center.leaveDir) {
        const isBuy = sig1.dir === 'buy';
        const holds = isBuy
          ? objectEndPrice(postPullbackObj) > objectEndPrice(C)
          : objectEndPrice(postPullbackObj) < objectEndPrice(C);
        if (holds) {
          const status = center.status === 'confirmed' && !postPullbackObj.provisional ? 'confirmed' : 'candidate';
          signals.push({
            id: 'sig-2' + (isBuy ? 'B' : 'S') + center.id,
            type: isBuy ? '2B' : '2S',
            dir: isBuy ? 'buy' : 'sell',
            zsId: center.id,
            level: center.level,
            idx: objectEndIdx(postPullbackObj),
            date: objectEndDate(postPullbackObj),
            price: objectEndPrice(postPullbackObj),
            status,
            stage: 'pullback',
            boundary: isBuy ? center.zd : center.zg,
            rejection_reasons: status === 'confirmed' ? [] : ['first_point_or_pullback_not_confirmed'],
            evidence: { firstSignalId: sig1.id, postPullbackObjId: postPullbackObj.id, refPrice: objectEndPrice(C) },
          });
        }
      }
    }

    // 3B/3S
    // E-Z12: 三买/三卖的方向是"离开到了中枢哪一侧"(center.leaveDir)，不是 leaveObj 自身
    // 斜率(C.dir)——leaveDir 为 null（终点其实还在区间内，谈不上真离开）时不生成 3B/3S。
    if (center.leaveObj && center.leaveDir) {
      const dirC = center.leaveDir;
      if (!center.pullbackObj) {
        // 突破观察点：已离开但尚未出现回踩段。
        const isUp = dirC === 'up';
        signals.push({
          id: 'sig-3' + (isUp ? 'B' : 'S') + center.id + '-leave',
          type: isUp ? '3B' : '3S',
          dir: isUp ? 'buy' : 'sell',
          zsId: center.id,
          level: center.level,
          idx: objectEndIdx(C),
          date: objectEndDate(C),
          price: objectEndPrice(C),
          status: 'candidate',
          stage: 'leave',
          displayType: isUp ? '突破' : '破位',
          boundary: isUp ? center.zg : center.zd,
          needsCondition: '已向' + (isUp ? '上' : '下') + '离开中枢；需下一段回踩不' + (isUp ? '跌回' : '站回') + '中枢' + (isUp ? '上沿' : '下沿') + ' ' + (isUp ? center.zg : center.zd).toFixed(2) + ' 内，' + (isUp ? '三买' : '三卖') + '才确认',
          rejection_reasons: ['pullback_segment_not_yet_formed'],
          evidence: { leaveObjId: C.id },
        });
      } else {
        const pullbackObj = center.pullbackObj;
        const isUp = dirC === 'up';
        const boundary = isUp ? center.zg : center.zd;
        const success = isUp
          ? objectLow(pullbackObj) > center.zg
          : objectHigh(pullbackObj) < center.zd;
        if (success) {
          const status = center.status === 'confirmed' && !pullbackObj.provisional ? 'confirmed' : 'candidate';
          signals.push({
            id: 'sig-3' + (isUp ? 'B' : 'S') + center.id,
            type: isUp ? '3B' : '3S',
            dir: isUp ? 'buy' : 'sell',
            zsId: center.id,
            level: center.level,
            idx: objectEndIdx(pullbackObj),
            date: objectEndDate(pullbackObj),
            price: objectEndPrice(pullbackObj),
            status,
            stage: 'pullback',
            boundary,
            rejection_reasons: status === 'confirmed' ? [] : ['center_or_pullback_not_confirmed'],
            evidence: { leaveObjId: C.id, pullbackObjId: pullbackObj.id, condition: isUp ? 'pullback_low_strictly_above_ZG' : 'pullback_high_strictly_below_ZD' },
          });
        } else {
          signals.push({
            id: 'sig-3' + (isUp ? 'B' : 'S') + center.id + '-failed',
            type: isUp ? '3B' : '3S',
            dir: isUp ? 'buy' : 'sell',
            zsId: center.id,
            level: center.level,
            idx: objectEndIdx(pullbackObj),
            date: objectEndDate(pullbackObj),
            price: objectEndPrice(pullbackObj),
            status: 'failed',
            stage: 'pullback',
            boundary,
            failReason: '回踩重回中枢区间',
            rejection_reasons: ['pullback_reentered_center_range'],
            evidence: { leaveObjId: C.id, pullbackObjId: pullbackObj.id },
          });
        }
      }
    }
  }

  // F4: 同一中枢上背驰(1B/1S)与三买/三卖(3B/3S)是互斥解读，不能并列以 confirmed 姿态摆给用户。
  // 出现背驰信号时，把该中枢非 failed 的 3B/3S 降级为 candidate，保留可见性但不与背驰并列采信。
  const byZs = {};
  for (const s of signals) {
    if (!byZs[s.zsId]) byZs[s.zsId] = [];
    byZs[s.zsId].push(s);
  }
  for (const zsId in byZs) {
    const group = byZs[zsId];
    const hasDivergence = group.some((s) => s.type === '1B' || s.type === '1S');
    if (!hasDivergence) continue;
    for (const s of group) {
      if ((s.type === '3B' || s.type === '3S') && s.status !== 'failed') {
        s.status = 'candidate';
        s.conflictNote = '同一中枢的离开段已出现背驰信号，三买/三卖仅作观察，不与背驰并列采信';
        s.rejection_reasons = uniq([...(s.rejection_reasons || []), 'conflicts_with_divergence_on_same_center']);
      }
    }
  }

  signals.sort((a, b) => a.idx - b.idx);
  return signals;
}

function supportResistance(centers) {
  const lines = [];
  const lastCenters = (centers || []).slice(-2);
  for (const zs of lastCenters) {
    lines.push({ id: 'sr-zg-' + zs.id, price: zs.zg, type: 'resistance', label: '中枢上沿 ZG' });
    lines.push({ id: 'sr-zd-' + zs.id, price: zs.zd, type: 'support', label: '中枢下沿 ZD' });
  }
  return lines;
}

function failureLine(signals, objects) {
  if (!signals || !signals.length) return null;
  const last = signals[signals.length - 1];
  if (last.boundary != null) {
    return {
      signalId: last.id,
      price: last.boundary,
      dir: last.dir,
      label: (last.dir === 'buy' ? '防守位(跌破失效)' : '防守位(涨破失效)'),
    };
  }
  const list = objects || [];
  const obj = list.find((o) => o.id === last.biId || o.id === last.zsId);
  if (!obj) return null;
  const price = last.dir === 'buy' ? objectLow(obj) : objectHigh(obj);
  return {
    signalId: last.id,
    price,
    dir: last.dir,
    label: (last.dir === 'buy' ? '防守位(跌破失效)' : '防守位(涨破失效)'),
  };
}

  const API = {
    RULE_VERSION,
    STRENGTH_WEAK, STRENGTH_STRONG, STRENGTH_MIN_AREA_RATIO,
    ZS_MEMBER_MIN_OVERLAP, ZS_FALSEBREAK_MAX_SPAN, ZS_SEED_MIN_OVERLAP,
    mergeInclusion, findFenxing, buildBi, buildXianduan,
    buildZhongshuFromObjects, buildAllZhongshu, buildZhongshu,
    computeTrendSegments, computeMacd, computeStrength, computeTrendStrength,
    computeBeichi, deriveSignals, supportResistance, failureLine,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  global.ChanAlgo = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
