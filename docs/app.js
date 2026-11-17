/* 메뉴와 화면. 자료는 docs/data/*.json (자동 수집 결과)에서 읽는다. */
(function () {
  'use strict';
  const { h, fmt, signed } = TT;
  const $ = (id) => document.getElementById(id);
  const cache = {};

  async function load(name, force) {
    if (!force && cache[name] !== undefined) return cache[name];
    try {
      const res = await fetch('data/' + name + '.json?_=' + Date.now(), { cache: 'no-store' });
      cache[name] = res.ok ? await res.json() : null;
    } catch (err) {
      cache[name] = null;
    }
    return cache[name];
  }

  /* ---------- 공용 ---------- */
  const last = (obs) => (obs && obs.length ? obs[obs.length - 1] : null);
  const card = (title, sub, ...kids) => h('section', { class: 'card' },
    h('div', { class: 'card-head' }, h('div', null, h('h3', { text: title }), sub ? h('p', { class: 'sub', text: sub }) : null)), ...kids);
  const empty = (text) => h('p', { class: 'empty', text });
  const tile = (label, value, unit, delta) => h('div', { class: 'tile' },
    h('div', { class: 'label', text: label }),
    h('div', { class: 'value' }, value, unit ? h('small', { text: unit }) : null),
    h('div', { class: 'delta', text: delta || ' ' }));
  const cut = (obs, months) => {
    if (!months || !obs.length) return obs;
    const floor = TT.xval(obs[obs.length - 1][0]) - months * 30.44;
    return obs.filter((p) => TT.xval(p[0]) >= floor);
  };
  const kst = (iso) => iso ? new Date(iso).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '–';
  const tone = (v) => (v == null || v === 0 ? '' : v > 0 ? 'up' : 'down');
  const label = (stamp, freq) => freq === 'M' ? stamp.slice(0, 7) : freq === 'Q' ? stamp.slice(0, 4) + 'Q' + (Math.floor((+stamp.slice(5, 7) - 1) / 3) + 1) : stamp;

  /* 기간 선택이 붙은 차트 카드 */
  function rangeCard(title, sub, ranges, draw, extra) {
    const body = h('div');
    let current = ranges[0].id;
    const render = () => draw(body, ranges.find((r) => r.id === current).months);
    const seg = TT.segmented(ranges, current, (id) => { current = id; render(); });
    const section = h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', null, h('h3', { text: title }), sub ? h('p', { class: 'sub', text: sub }) : null), seg),
      body, extra || null);
    requestAnimationFrame(render);
    return section;
  }
  const R_DAILY = [{ id: '1y', label: '1년', months: 12 }, { id: '6m', label: '6개월', months: 6 }, { id: '3m', label: '3개월', months: 3 }, { id: 'all', label: '전체', months: 0 }];
  const R_LONG = [{ id: '10y', label: '10년', months: 120 }, { id: '5y', label: '5년', months: 60 }, { id: '3y', label: '3년', months: 36 }, { id: 'all', label: '전체', months: 0 }];

  /* 최근 값 표: 기간 × (값, 직전 대비, 전년 대비). 일별·주간 자료는 월말 값으로 모은다. */
  function recentTable(list, freq, digits, count) {
    const monthly = freq === 'D' || freq === 'W';
    const maps = list.map((se) => {
      const m = new Map();
      for (const [stamp, v] of se.obs) if (v != null) m.set(monthly ? stamp.slice(0, 7) : label(stamp, freq), v);
      return m;
    });
    const periods = Array.from(new Set(maps.flatMap((m) => Array.from(m.keys())))).sort().reverse();
    const yearBack = (p) => (+p.slice(0, 4) - 1) + p.slice(4);
    const columns = [{ label: monthly ? '월(월말 값)' : freq === 'Q' ? '분기' : '기간' }];
    list.forEach((se) => columns.push({ label: se.label, num: true }, { label: '직전 대비', num: true }, { label: '전년 대비', num: true }));
    const rows = periods.slice(0, count || 36).map((p) => {
      const row = [p];
      maps.forEach((m) => {
        const v = m.get(p);
        const before = periods.slice(periods.indexOf(p) + 1).map((q) => m.get(q)).find((x) => x != null);
        const yago = m.get(yearBack(p));
        const d1 = v != null && before != null ? v - before : null;
        const d2 = v != null && yago != null ? v - yago : null;
        row.push({ text: fmt(v, digits), cls: 'strong' }, { text: signed(d1, digits), cls: tone(d1) }, { text: signed(d2, digits), cls: tone(d2) });
      });
      return row;
    });
    return h('details', { class: 'more' }, h('summary', { text: '수치 표 (최근 ' + rows.length + '개 기간)' }), TT.table(columns, rows));
  }

  /* ---------- 금리 ---------- */
  function buildRates(view, D) {
    const S = D.rates.series;
    const get = (k) => (S[k] ? S[k].obs : []);
    const bp = (obs) => {
      if (obs.length < 2) return '';
      const d = (obs[obs.length - 1][1] - obs[obs.length - 2][1]) * 100;
      return obs[obs.length - 1][0].slice(5) + ' · 직전 대비 ' + signed(d, 1) + 'bp';
    };
    const tiles = h('div', { class: 'tiles' });
    [['effr', 'USD EFFR'], ['sofr', 'USD SOFR'], ['estr', 'EUR €STR'], ['tona', 'JPY TONA'], ['call', 'KRW 콜금리'], ['kofr', 'KRW KOFR']]
      .forEach(([k, name]) => { const o = get(k); if (o.length) tiles.append(tile(name, fmt(last(o)[1], k === 'effr' || k === 'sofr' ? 2 : 3), '%', bp(o))); });
    view.append(tiles);
    const chart = (title, sub, defs, digits) => rangeCard(title, sub, R_DAILY, (box, months) => {
      TT.timeChart(box, { unit: '%', digits, series: defs.map((d) => ({ name: d[1], color: d[2], step: d[3], dash: d[4], width: d[4] ? 1.5 : 2,
        points: d[3] ? stepCut(get(d[0]), get(defs[0][0]), months) : cut(get(d[0]), months) })).filter((se) => se.points.length) });
    }, recentTable(defs.filter((d) => !d[4]).map((d) => ({ label: d[1], obs: d[3] ? fillStep(get(d[0]), get(defs[0][0])) : get(d[0]) })), 'D', digits, 24));
    view.append(chart('미국 달러', 'EFFR·SOFR와 연방기금 목표범위', [['effr', 'EFFR', '--s1'], ['sofr', 'SOFR', '--s2'], ['effr_hi', '목표범위 상단', '--bar', false, true], ['effr_lo', '목표범위 하단', '--bar', false, true]], 2));
    view.append(chart('유로', '€STR과 ECB 수신금리', [['estr', '€STR', '--s1'], ['dfr', 'ECB 수신금리', '--s2', true]], 3));
    view.append(chart('일본 엔', '무담보 콜 익일물(TONA)', [['tona', 'TONA', '--s1']], 3));
    if (get('call').length || get('kofr').length) {
      view.append(chart('한국 원', '콜금리(1일, 전체거래)와 KOFR', [['call', '콜금리', '--s1'], ['kofr', 'KOFR', '--s2']], 3));
    }
    view.append(h('p', { class: 'note', text: '출처: 뉴욕 연은 Markets API, ECB Data API, 일본은행 시계열 통계, 한국은행 ECOS. 한국 금리는 ECOS 키가 등록돼야 과거 이력까지 받습니다.' }));
  }
  /* 변경일만 있는 금리(계단)를 기준 시리즈의 날짜 축에 맞춰 편다 */
  function fillStep(steps, base) {
    const out = [];
    let i = 0, value = null;
    for (const [day] of base) {
      while (i < steps.length && steps[i][0] <= day) { value = steps[i][1]; i += 1; }
      if (value != null) out.push([day, value]);
    }
    return out;
  }
  const stepCut = (steps, base, months) => cut(fillStep(steps, base), months);

  function spread(a, b) {
    const m = new Map(b);
    const out = [];
    for (const [day, v] of a) if (m.has(day)) out.push([day, +((v - m.get(day)) * 100).toFixed(2)]);
    return out;
  }
  function movingAvg(obs, n) {
    const out = [];
    let sum = 0;
    for (let i = 0; i < obs.length; i++) {
      sum += obs[i][1];
      if (i >= n) sum -= obs[i - n][1];
      if (i >= n - 1) out.push([obs[i][0], +(sum / n).toFixed(2)]);
    }
    return out;
  }
  function monthlyNote(obs) {
    if (!obs.length) return '';
    const by = {};
    for (const [day, v] of obs) (by[day.slice(0, 7)] = by[day.slice(0, 7)] || []).push(v);
    const months = Object.keys(by).sort();
    const avg = (k) => by[k].reduce((a, b) => a + b, 0) / by[k].length;
    const cur = months[months.length - 1], prev = months[months.length - 2];
    if (!prev) return cur + ' 평균 ' + signed(avg(cur), 1) + 'bp';
    const d = avg(cur) - avg(prev);
    return prev + ' 평균 ' + signed(avg(prev), 1) + 'bp → ' + cur + ' 평균 ' + signed(avg(cur), 1) + 'bp (' + (Math.abs(d) < 0.5 ? '보합' : d > 0 ? '확대' : '축소') + ')';
  }
  function buildFunding(view, D) {
    const S = D.rates.series;
    const get = (k) => (S[k] ? S[k].obs : []);
    const section = (title, sub, guide, raw) => {
      if (raw.length < 2) return card(title, sub, empty('아직 받은 자료가 적어 그릴 수 없습니다. 수집이 쌓이면 표시됩니다.'));
      const g = h('p', { class: 'guide' }, guide, ' ', h('b', { text: monthlyNote(raw) }));
      return rangeCard(title, sub, R_DAILY, (box, months) => {
        TT.timeChart(box, { unit: 'bp', digits: 1, zero: true, series: [
          { name: '일별', color: '--s2', width: 1.5, points: cut(raw, months) },
          { name: '20거래일 평균', color: '--s1', points: cut(movingAvg(raw, 20), months) }] });
      }, h('div', null, g, recentTable([{ label: '금리 차이(bp)', obs: raw }], 'D', 1, 24)));
    };
    view.append(section('미국: SOFR 75백분위 − 준비금 이자율(IORB)', '국채 담보 조달금리가 준비금 이자율보다 얼마나 높은가',
      '값이 커지면 담보를 맡기고도 자금을 구하기가 빡빡해졌다는 뜻입니다. 분기말·세금 납부일 전후에 튀는 일이 잦습니다.',
      spread(get('sofr75'), fillStep(get('iorb'), get('sofr75')))));
    view.append(section('한국: KOFR − 콜금리', '익일물 RP금리(담보)와 콜금리(무담보)의 차이',
      '값이 커지면 담보부(RP) 조달이 무담보 콜보다 비싸졌다는 뜻으로, 국채 수급이나 분기말 조달 부담을 가리킵니다.',
      spread(get('kofr'), get('call'))));
    view.append(h('p', { class: 'note', text: '출처: 뉴욕 연은(SOFR 백분위), FRED(IORB), 한국은행 ECOS(콜금리·KOFR).' }));
  }

  /* ---------- 통화정책 ---------- */
  const BANK_INFO = {
    bok: { short: '한국은행', full: '금융통화위원회 통화정책방향 결정회의', color: '--bank-bok',
      note: '결정 발표는 회의 당일 오전 (총재 기자간담회 오전 11시대)' },
    fed: { short: 'FOMC', full: '미 연방공개시장위원회 (연준)', color: '--bank-fed',
      note: '성명 미 동부 14:00 → 한국 시간 다음 날 새벽 4시(서머타임 3시)' },
    boj: { short: 'BOJ', full: '일본은행 금융정책결정회합', color: '--bank-boj',
      note: '결정 발표는 2일차 정오 전후 (한국 시간) · 표시 금리는 콜금리로 추정한 정책금리' },
    ecb: { short: 'ECB', full: '유럽중앙은행 정책이사회 (통화정책회의)', color: '--bank-ecb',
      note: '결정 CET 14:15 → 한국 시간 밤 10:15(서머타임 9:15) · 표시 금리는 수신금리(DFR)' },
  };
  const BANK_ORDER = ['bok', 'fed', 'boj', 'ecb'];
  const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
  const utc = (iso) => new Date(iso + 'T00:00:00Z');
  const monthDay = (iso) => { const d = utc(iso); return (d.getUTCMonth() + 1) + '/' + d.getUTCDate() + '(' + WEEK[d.getUTCDay()] + ')'; };
  const meetingSpan = (m) => {
    if (m.start === m.date) return monthDay(m.date);
    const e = utc(m.date);
    return monthDay(m.start) + '~' + (m.start.slice(0, 7) === m.date.slice(0, 7) ? e.getUTCDate() + '(' + WEEK[e.getUTCDay()] + ')' : monthDay(m.date));
  };
  const todayKst = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  const dday = (iso, today) => { const n = Math.round((utc(iso) - utc(today)) / 864e5); return n === 0 ? 'D-DAY' : 'D-' + n; };
  const pillTabs = (items, current, onPick) => {
    const box = h('div', { class: 'tabs', role: 'group' });
    items.forEach((it) => {
      const b = h('button', { class: 'tab', type: 'button', 'aria-pressed': String(it.id === current), text: it.label });
      b.addEventListener('click', () => {
        box.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', 'false'));
        b.setAttribute('aria-pressed', 'true');
        onPick(it.id);
      });
      box.append(b);
    });
    return box;
  };

  function buildCbank(view, D) {
    const today = todayKst();
    const thisYear = today.slice(0, 4);
    const all = (D.cbank && D.cbank.banks) || [];
    const banks = BANK_ORDER.map((code) => all.find((b) => b.code === code)).filter(Boolean);
    if (!banks.length) { view.append(empty('아직 받은 일정이 없습니다.')); return; }
    const st = D._status && D._status.sources.cbank;
    const asof = st && st.checked_at ? new Date(st.checked_at).toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' }) : today;
    view.append(h('div', { class: 'chipline' },
      h('span', { class: 'infochip', text: '일정 기준: ' + asof + ' · 각 은행 공식 발표 일정 (결정 발표일은 회의 마지막 날)' }),
      h('button', { class: 'btn', type: 'button', text: '일정·점도표 새로고침', on: { click: () => $('refresh').click() } })));

    const nextOf = (b) => b.meetings.find((m) => m.date >= today);
    let years = Array.from(new Set(banks.flatMap((b) => b.meetings.map((m) => m.date.slice(0, 4))))).sort()
      .filter((y) => y >= thisYear && banks.filter((b) => b.meetings.some((m) => m.date.startsWith(y))).length >= 2).slice(0, 2);
    if (!years.length) years = [thisYear];

    const grid = h('div', { class: 'bankgrid' });
    const drawYear = (year) => {
      grid.textContent = '';
      banks.forEach((b) => {
        const info = BANK_INFO[b.code];
        const next = nextOf(b);
        const rows = b.meetings.filter((m) => m.date.startsWith(year)).map((m, i) => {
          const isNext = next && m.date === next.date;
          const kind = m.result === '인상' ? 'hike' : m.result === '인하' ? 'cut' : 'hold';
          return h('li', { class: isNext ? 'next' : null },
            h('span', { class: 'idx', text: String(i + 1) }),
            h('span', { class: 'when', text: meetingSpan(m) }),
            m.result ? h('span', { class: 'pill ' + kind }, h('b', { text: m.result }), m.rate ? ' ' + m.rate : '')
              : (m.date < today ? h('span', { class: 'pill wait', text: '결과 확인 중' }) : null),
            m.sep ? h('span', { class: 'mtag', text: 'SEP' }) : null,
            m.outlook ? h('span', { class: 'mtag', text: '전망보고서' }) : null,
            m.effective ? h('span', { class: 'eff', text: '발효 ' + (+m.effective.slice(5, 7)) + '/' + (+m.effective.slice(8, 10)) }) : null,
            isNext ? h('span', { class: 'dday soft', text: dday(m.date, today) }) : null);
        });
        grid.append(h('section', { class: 'bankcard', style: 'border-top-color:var(' + info.color + ')' },
          h('div', { class: 'bankcard-head' },
            h('div', { class: 'bankcard-title' }, h('h3', { text: info.short }), b.rate ? h('span', { class: 'now', text: '현재 ' + b.rate }) : null),
            h('p', { class: 'full', text: info.full }), h('p', { class: 'memo', text: info.note })),
          rows.length ? h('ol', { class: 'meet' }, rows) : h('p', { class: 'memo pad', text: year + '년 일정은 아직 발표되지 않았습니다.' })));
      });
    };
    view.append(pillTabs(years.map((y) => ({ id: y, label: y + '년' })), years[0], drawYear));

    const chips = h('div', { class: 'nextchips' });
    banks.forEach((b) => {
      const n = nextOf(b);
      if (!n) return;
      chips.append(h('span', { class: 'nextchip' },
        h('i', { class: 'bdot', style: 'background:var(' + BANK_INFO[b.code].color + ')' }),
        h('b', { text: BANK_INFO[b.code].short }), h('span', { text: meetingSpan(n) }),
        h('span', { class: 'dday', text: dday(n.date, today) })));
    });
    view.append(chips, grid);
    drawYear(years[0]);
    view.append(h('p', { class: 'note', text: '결과는 성명서가 아니라 공식 금리 시계열의 변화로 판정합니다. 일본은행 금리는 회의 전후 콜금리 수준으로 추정한 값입니다.' }));

    const seps = (D.dots && D.dots.seps) || [];
    if (!seps.length) return;
    const fed = banks.find((b) => b.code === 'fed');
    const sepLabel = (x) => (x.meeting.slice(0, 4) === thisYear ? '' : "'" + x.meeting.slice(2, 4) + ' ') + x.label;
    const body = h('div');
    const source = h('p', { class: 'sub' });
    const draw = (key) => {
      const i = seps.findIndex((x) => x.meeting === key);
      const sep = seps[i], before = seps[i - 1];
      source.textContent = '출처: 연준 SEP 전망자료 (federalreserve.gov) · ' + sep.meeting + ' FOMC 발표 · 분기(3·6·9·12월)';
      body.textContent = '';
      let current = null;
      if (i === seps.length - 1 && fed && fed.rate) {
        const m = /([\d.]+)~([\d.]+)/.exec(fed.rate);
        if (m) current = (+m[1] + +m[2]) / 2;
      }
      const guide = h('ul');
      guide.append(
        h('li', null, h('b', { text: '점 1개' }), ' = FOMC 참가자 1명이 적정하다고 본 해당 연도 말 ', h('b', { text: '정책금리' }), '(목표범위 중간값). 3·6·9·12월 회의마다 발표'),
        h('li', null, '핵심은 ', h('b', { text: '중앙값(굵은 선)의 이동' }), ' — 위 탭으로 직전 SEP와 견주면 위원들의 금리 경로 전망이 어느 쪽으로 움직였는지 보임'),
        h('li', null, h('b', { text: '장기(Longer run)' }), ' = 경기를 부양하지도 긴축하지도 않는 ', h('b', { text: '중립금리' }), '에 대한 판단'));
      if (before) {
        const moves = [];
        let up = 0, down = 0;
        sep.years.forEach((year, k) => {
          const old = before.medians[before.years.indexOf(year)], now = sep.medians[k];
          if (old == null || now == null) return;
          moves.push(year + ' ' + fmt(old, 1) + '→' + fmt(now, 1));
          if (now > old) up += 1; else if (now < old) down += 1;
        });
        const verdict = !up && !down ? '변화 없음' : !down ? '전반 상향' : !up ? '전반 하향' : '엇갈림';
        guide.append(h('li', null, '직전(' + sepLabel(before) + ') 대비 중앙값: ', h('b', { text: moves.join(' · ') + ' — ' + verdict })));
      }
      const most = Math.max(...sep.participants);
      const short = sep.years.filter((y, k) => sep.participants[k] < most);
      guide.append(h('li', { text: '참가자 ' + most + '명' + (short.length ? ' — ' + (most - Math.min(...sep.participants)) + '명은 ' + short.join('·') + ' 미제출' : '') }));
      const chipsRow = h('div', { class: 'tiles' });
      sep.years.forEach((year, k) => {
        const old = before ? before.medians[before.years.indexOf(year)] : null;
        const d = old != null && sep.medians[k] != null ? sep.medians[k] - old : null;
        chipsRow.append(tile(year + (year === '장기' ? '' : '년 말') + ' 중앙값', fmt(sep.medians[k], 1), '%',
          d == null ? '직전 전망 없음' : '직전 대비 ' + signed(d, 1) + '%p'));
      });
      const box = h('div');
      body.append(h('div', { class: 'guidebox' }, h('h4', { text: '차트 읽는 법 — 연준 위원들이 보는 적정 금리 경로' }), guide), chipsRow, box,
        h('details', { class: 'more' }, h('summary', { text: '수치 표' }),
          TT.table([{ label: '연도' }, { label: '중앙값', num: true }, { label: '중심 경향', num: true }, { label: '전체 범위', num: true }, { label: '참가자 수', num: true }],
            sep.years.map((year, k) => [year, { text: fmt(sep.medians[k], 1), cls: 'strong' }, sep.ct[k] || '–', sep.range[k] || '–', sep.participants[k]]))));
      TT.dotPlot(box, { years: sep.years, bins: sep.bins, medians: sep.medians, current });
    };
    const firstKey = seps[seps.length - 1].meeting;
    view.append(h('section', { class: 'card' },
      h('div', { class: 'card-head' },
        h('div', null, h('h3', { text: '연준 점도표 — 정책금리 전망 분포 (SEP)' }), source),
        pillTabs(seps.map((x) => ({ id: x.meeting, label: sepLabel(x) })), firstKey, draw)),
      body));
    requestAnimationFrame(() => draw(firstKey));
  }

  /* ---------- 물가 ---------- */
  function buildBreadth(view, D) {
    const P = D.pce;
    if (!P) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const col = (name) => P.obs.map((row) => [row[0], row[1 + P.columns.indexOf(name)]]);
    const latest = last(P.obs);
    view.append(h('div', { class: 'tiles' },
      tile('3개월 연율 2% 초과 비중', fmt(latest[1], 1), '%', latest[0] + ' 기준'),
      tile('3개월 연율 3% 초과 비중', fmt(latest[2], 1), '%', ''),
      tile('전년 대비 2% 초과 비중', fmt(latest[4], 1), '%', ''),
      tile('전년 대비 3% 초과 비중', fmt(latest[5], 1), '%', '')));
    view.append(h('p', { class: 'guide' }, '물가 상승이 몇몇 품목에 몰려 있는지, 넓게 퍼져 있는지를 봅니다. ',
      h('b', { text: 'PCE 지출을 16개 품목군으로 나눠, 상승률이 기준을 넘는 품목군의 지출 비중' }), '을 그렸습니다. 선이 높을수록 물가 압력이 넓게 퍼졌다는 뜻입니다.'));
    const chart = (title, sub, keys) => rangeCard(title, sub, R_LONG, (box, months) => {
      TT.timeChart(box, { unit: '%', digits: 1, zero: true, series: keys.map((k, i) => ({ name: k[1], color: '--s' + (i + 1), points: cut(col(k[0]), months) })) });
    });
    view.append(chart('3개월 연율 기준', '최근 석 달 상승 속도가 기준을 넘는 품목군의 비중', [['a3_2', '2% 초과'], ['a3_3', '3% 초과'], ['a3_4', '4% 초과']]));
    view.append(chart('전년 대비 기준', '1년 전보다 기준 넘게 오른 품목군의 비중', [['yy_2', '2% 초과'], ['yy_3', '3% 초과'], ['yy_4', '4% 초과']]));
    view.append(card('품목군별 상승률 (' + P.latest + ')', '가중치는 직전 달 명목 지출 비중',
      TT.table([{ label: '품목군' }, { label: '가중치(%)', num: true }, { label: '3개월 연율(%)', num: true }, { label: '전년 대비(%)', num: true }],
        P.items.map((it) => [it.n, fmt(it.w, 1), { text: fmt(it.a3, 1), cls: it.a3 > 2 ? 'up' : '' }, { text: fmt(it.yoy, 1), cls: it.yoy > 2 ? 'up' : '' }]), { tall: true })));
    view.append(h('p', { class: 'note', text: '기준: ' + P.basis + '. 세부 품목(200여 개) 기준 지표보다 거칠게 움직입니다. 출처: BEA (DBnomics 경유).' }));
  }

  function buildInfl(view, D) {
    const releases = (D.infl && D.infl.releases) || [];
    if (!releases.length) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const body = h('div');
    const pick = h('select', { class: 'pick', 'aria-label': '발표 회차' },
      releases.map((r) => h('option', { value: r.id, text: r.kind + ' ' + r.ref + ' 기준' })));
    const draw = () => {
      const r = releases.find((x) => x.id === pick.value);
      body.textContent = '';
      const head = r.items[0], core = r.items.find((it) => it.n.startsWith('근원'));
      const t = (name, v, prev, unit) => tile(name, fmt(v, 2), '%', prev == null ? '' : '직전 달 ' + fmt(prev, 2) + unit);
      body.append(h('div', { class: 'tiles' },
        t('전체 전월비', head.mom, head.pmom, '%'), t('전체 전년비', head.yoy, null, ''),
        core ? t('근원 전월비', core.mom, core.pmom, '%') : null, core ? t('근원 전년비', core.yoy, null, '') : null));
      const drivers = r.items.filter((it) => it.drv && it.c != null).sort((a, b) => b.c - a.c);
      if (drivers.length) {
        const box = h('div');
        body.append(card('전월비를 끌어올린 항목', '겹치지 않는 16개 항목의 기여도(%p). 합이 전체 전월비와 같습니다.', box));
        TT.hbars(box, drivers.map((it) => ({ label: it.n, note: '가중치 ' + fmt(it.w, 1) + '%', value: it.c })), { digits: 3 });
      }
      const hasW = r.items.some((it) => it.w != null);
      const cols = [{ label: '항목' }].concat(hasW ? [{ label: '가중치(%)', num: true }] : [],
        [{ label: '전월비(%)', num: true }, { label: '직전 달(%)', num: true }, { label: '변화', num: true }, { label: '전년비(%)', num: true }],
        hasW ? [{ label: '기여도(%p)', num: true }] : []);
      const rows = r.items.map((it) => {
        const acc = it.mom != null && it.pmom != null ? it.mom - it.pmom : null;
        return [{ text: it.n, indent: it.lv, cls: it.lv <= 1 ? 'strong' : '' }].concat(hasW ? [fmt(it.w, 1)] : [],
          [{ text: fmt(it.mom, 2), cls: 'strong' }, fmt(it.pmom, 2), { text: acc == null ? '–' : (acc > 0.005 ? '가속 ' : acc < -0.005 ? '둔화 ' : '') + signed(acc, 2), cls: tone(acc) }, fmt(it.yoy, 2)],
          hasW ? [fmt(it.c, 3)] : []);
      });
      body.append(card('세부 항목', r.src, TT.table(cols, rows, { tall: true })));
      if (r.kind === 'CPI' && head.yoy == null) body.append(h('p', { class: 'note', text: '전년비가 비어 있는 것은 1년 전 같은 달 지수가 공표되지 않았기 때문입니다(2025년 10월).' }));
    };
    pick.addEventListener('change', draw);
    view.append(h('div', { class: 'bar-row' }, pick), body);
    view.append(h('p', { class: 'note', text: '공표 지수로 계산한 수치만 싣습니다. 시장 예상치와 해석, 기사는 싣지 않습니다. CPI 전월비는 계절조정, 전체·근원 전년비는 비계절조정 지수 기준이고 품목별 전년비는 계절조정 지수로 계산했습니다.' }));
    draw();
  }

  /* ---------- 미국 경제지표 ---------- */
  function macroSection(D, title, sub, keys, opts) {
    const S = D.macro.series;
    const list = keys.filter((k) => S[k]).map((k) => S[k]);
    if (!list.length) return card(title, sub, empty('아직 받은 자료가 없습니다.'));
    const o = opts || {};
    const freq = list[0].freq, unit = list[0].unit;
    const digits = o.digits == null ? 2 : o.digits;
    return rangeCard(title, sub || list.map((s) => s.src).filter((v, i, a) => a.indexOf(v) === i).join(', '), R_LONG, (box, months) => {
      const mk = (se, i) => ({ name: se.label, color: '--s' + (i + 1), points: cut(se.obs, months).map((p) => [freq === 'M' ? p[0].slice(0, 7) : p[0], p[1]]) });
      const conf = { unit: unit === '%' ? '%' : ' ' + unit, digits, zero: !!o.zero, refs: o.refs };
      if (o.bars) conf.bars = list.map((se, i) => Object.assign(mk(se, i), { color: '--bar' }));
      else conf.series = list.map(mk);
      TT.timeChart(box, conf);
    }, recentTable(list, freq, digits));
  }
  function buildPrice(view, D) {
    if (!D.macro) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const S = D.macro.series;
    const tiles = h('div', { class: 'tiles' });
    [['cpi', 'CPI 전년비'], ['cpi_core', '근원 CPI 전년비'], ['pce', 'PCE 물가 전년비'], ['pce_core', '근원 PCE 전년비']].forEach(([k, name]) => {
      if (S[k]) tiles.append(tile(name, fmt(last(S[k].obs)[1], 2), '%', last(S[k].obs)[0].slice(0, 7) + ' 기준'));
    });
    view.append(tiles);
    view.append(macroSection(D, '소비자물가(CPI)', '전년 같은 달 대비', ['cpi', 'cpi_core'], { refs: [{ y: 2, label: '2%' }] }));
    view.append(macroSection(D, '개인소비지출(PCE) 물가', '전년 같은 달 대비. 연준의 물가 목표 기준', ['pce', 'pce_core'], { refs: [{ y: 2, label: '목표 2%' }] }));
    view.append(macroSection(D, '통화량 M2', '전년 같은 달 대비', ['m2'], { zero: true }));
    view.append(macroSection(D, '연준 총자산', '주간, 조 달러', ['fed_assets'], { digits: 3 }));
  }
  function buildJobs(view, D) {
    if (!D.macro) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const S = D.macro.series;
    const tiles = h('div', { class: 'tiles' });
    [['unrate', '실업률', '%', 1], ['payems', '비농업 고용 증감', '천 명', 0], ['ahe', '시간당 임금 전년비', '%', 2], ['claims', '신규 실업수당 청구', '천 건', 0]].forEach(([k, name, unit, d]) => {
      if (S[k]) tiles.append(tile(name, fmt(last(S[k].obs)[1], d), unit, last(S[k].obs)[0].slice(0, S[k].freq === 'W' ? 10 : 7) + ' 기준'));
    });
    view.append(tiles);
    view.append(macroSection(D, '실업률', null, ['unrate'], { digits: 1 }));
    view.append(macroSection(D, '비농업 고용 증감', '전월 대비, 천 명', ['payems'], { bars: true, digits: 0 }));
    view.append(macroSection(D, '시간당 평균 임금', '전년 같은 달 대비', ['ahe']));
    view.append(macroSection(D, '경제활동참가율', null, ['civpart'], { digits: 1 }));
    view.append(macroSection(D, '구인 건수(JOLTS)', '백만 건', ['jolts'], { digits: 2 }));
    view.append(macroSection(D, '신규 실업수당 청구', '주간, 천 건', ['claims'], { digits: 0 }));
  }
  function buildActivity(view, D) {
    if (!D.macro) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    view.append(macroSection(D, '실질 GDP 성장률', '전기 대비 연율', ['gdp'], { bars: true, digits: 1 }));
    view.append(macroSection(D, '산업생산·소매판매', '전년 같은 달 대비', ['indpro', 'retail'], { zero: true }));
    view.append(macroSection(D, '시카고 연은 전미활동지수', '3개월 평균. 0이면 추세 성장, −0.7 아래면 침체 신호로 봅니다', ['cfnai'], { zero: true, refs: [{ y: -0.7, label: '−0.7' }] }));
    view.append(macroSection(D, '지역 연은 제조업 지수', '뉴욕(엠파이어 스테이트)·필라델피아. 0보다 크면 확장', ['empire', 'philly'], { zero: true, digits: 1 }));
    view.append(h('p', { class: 'note', text: 'ISM PMI와 미시간대 소비자심리지수는 재배포가 제한된 민간 지표라 싣지 않고, 연준·지역 연은이 공개하는 지수로 대신했습니다.' }));
  }

  function buildDelinq(view, D) {
    const X = D.delinq;
    if (!X) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const rate = X.series.auto_d90.obs, bal = X.series.auto_bal.obs;
    const now = last(rate), yago = rate[rate.length - 5];
    const peak = rate.reduce((a, b) => (b[1] > a[1] ? b : a));
    view.append(h('div', { class: 'tiles' },
      tile('90일 이상 연체율', fmt(now[1], 2), '%', TT.shortLabel(now[0])),
      tile('1년 전 같은 분기', fmt(yago[1], 2), '%', '변화 ' + signed(now[1] - yago[1], 2) + '%p'),
      tile('2004년 이후 최고', fmt(peak[1], 2), '%', TT.shortLabel(peak[0])),
      tile('자동차대출 잔액', fmt(last(bal)[1], 2), '조 달러', TT.shortLabel(last(bal)[0]))));
    const R = [{ id: 'all', label: '전체', months: 0 }, { id: '10y', label: '10년', months: 120 }, { id: '5y', label: '5년', months: 60 }];
    view.append(rangeCard('자동차대출 90일 이상 연체율', '잔액 대비 비중, 분기', R, (box, m) =>
      TT.timeChart(box, { unit: '%', digits: 2, series: [{ name: '연체율', color: '--s2', points: cut(rate, m) }] })));
    view.append(rangeCard('자동차대출 잔액', '조 달러, 분기', R, (box, m) =>
      TT.timeChart(box, { unit: '조 달러', digits: 2, series: [{ name: '잔액', color: '--s1', points: cut(bal, m) }] }),
    recentTable([{ label: '연체율(%)', obs: rate }, { label: '잔액(조 달러)', obs: bal }], 'Q', 2, 24)));
    view.append(h('p', { class: 'note', text: '출처: 뉴욕 연은 분기 가계부채·신용 보고서(Consumer Credit Panel/Equifax).' }));
  }

  function buildFiscal(view, D) {
    const F = D.fiscal;
    if (!F) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const prim = F.series.primary.map((p) => [String(p[0]), p[1]]);
    const total = new Map(F.series.total), intr = new Map(F.series.interest);
    const now = last(prim), before = prim[prim.length - 2];
    view.append(h('div', { class: 'tiles' },
      tile('기초적자 (FY' + now[0] + ')', fmt(now[1], 2), '% of GDP', 'FY' + before[0] + ' ' + fmt(before[1], 2) + '%'),
      tile('순이자', fmt(intr.get(+now[0]), 2), '% of GDP', ''),
      tile('총적자', fmt(total.get(+now[0]), 2), '% of GDP', '기초적자 + 순이자'),
      tile('비침체기 평균 기초적자', fmt(F.avg_nonrecession, 2), '%', 'FY' + F.avg_range[0] + '~' + F.avg_range[1])));
    view.append(h('p', { class: 'guide' }, '기초적자는 이자를 빼고 본 재정적자입니다. 침체가 없던 해의 평균은 ', h('b', { text: fmt(F.avg_nonrecession, 2) + '%' }),
      '인데, 최근 회계연도는 ', h('b', { text: fmt(now[1], 2) + '% (평균의 ' + fmt(now[1] / F.avg_nonrecession, 1) + '배)' }), '입니다.'));
    const colors = {};
    F.recession.forEach((fy) => { colors[String(fy)] = '--bar-soft'; });
    const R = [{ id: 'all', label: '전체', months: 0 }, { id: '1990', label: '1990~', months: (+now[0] - 1990) * 12 + 1 }, { id: '2010', label: '2010~', months: (+now[0] - 2010) * 12 + 1 }];
    view.append(rangeCard('기초적자 (GDP 대비 %)', '회계연도. 옅은 막대는 침체가 낀 해, 점선은 비침체기 평균', R, (box, m) =>
      TT.timeChart(box, { unit: '%', digits: 2, bars: [{ name: '기초적자', color: '--s1', colors, points: cut(prim, m) }],
        refs: [{ y: F.avg_nonrecession, label: '비침체기 평균 ' + fmt(F.avg_nonrecession, 2) + '%' }],
        tipExtra: (fy) => [{ name: '순이자', value: fmt(intr.get(+fy), 2) + '%' }, { name: '총적자', value: fmt(total.get(+fy), 2) + '%' }] }),
    h('details', { class: 'more' }, h('summary', { text: '수치 표' }),
      TT.table([{ label: '회계연도' }, { label: '기초적자', num: true }, { label: '전년 대비', num: true }, { label: '순이자', num: true }, { label: '총적자', num: true }, { label: '침체' }],
        prim.slice().reverse().map((p, i, arr) => {
          const d = arr[i + 1] ? p[1] - arr[i + 1][1] : null;
          return ['FY' + p[0], { text: fmt(p[1], 2), cls: 'strong' }, { text: signed(d, 2), cls: tone(d) }, fmt(intr.get(+p[0]), 2), fmt(total.get(+p[0]), 2), F.recession.includes(+p[0]) ? '침체' : ''];
        })))));
    const X = D.refix;
    if (X && X.obs.length > 1) {
      const a = X.obs.map((r) => [r[0], r[1]]), b = X.obs.map((r) => [r[0], r[2]]);
      view.append(rangeCard('국채 리프라이싱 비중', '시장성 국채 가운데 1년 안에 새 금리를 받는 물량(단기채 + 변동금리채 + 1년 내 만기 중장기채)', R_LONG, (box, m) =>
        TT.timeChart(box, { unit: '%', digits: 1, series: [{ name: '1년 내 리프라이싱', color: '--s2', points: cut(a, m) }, { name: '단기채(Bills)', color: '--s1', points: cut(b, m) }] }),
      recentTable([{ label: '1년 내 리프라이싱(%)', obs: a }, { label: '단기채(%)', obs: b }], 'D', 1, 24)));
    }
    view.append(h('p', { class: 'note', text: '출처: FRED(재정수지·GDP), 미 재무부 월간 재정보고서(순이자, FY2015~)와 월간 국가채무 명세. 리프라이싱 과거 이력은 매일 조금씩 이어 받습니다.' }));
  }

  function buildGrowth(view, D) {
    const G = D.growth;
    if (!G) { view.append(empty('아직 받은 자료가 없습니다.')); return; }
    const g = G.series.gdp3y, y = G.series.y10q;
    const gmap = new Map(g), ymap = new Map(y);
    view.append(h('div', { class: 'tiles' },
      tile('명목 GDP 3년 연평균 성장률', fmt(last(g)[1], 2), '%', TT.shortLabel(last(g)[0])),
      tile('10년물 금리 (분기 평균)', fmt(last(y)[1], 2), '%', TT.shortLabel(last(y)[0])),
      G.latest10y ? tile('10년물 금리 (최근)', fmt(G.latest10y[1], 2), '%', G.latest10y[0]) : null,
      tile('금리 − 성장률 장기 평균', signed(G.avg_gap, 2), '%p', '1954년 이후')));
    view.append(h('p', { class: 'guide' }, '미국 10년물 금리는 대체로 경제가 커지는 속도(명목 성장률)를 따라 움직였습니다. 1954년 이후 금리는 성장률보다 평균 ',
      h('b', { text: fmt(Math.abs(G.avg_gap), 2) + '%p ' + (G.avg_gap < 0 ? '낮았습니다' : '높았습니다') }), '.'));
    const R = [{ id: '30y', label: '30년', months: 360 }, { id: '10y', label: '10년', months: 120 }, { id: 'all', label: '전체', months: 0 }];
    view.append(rangeCard('10년물 금리와 명목 GDP 성장률', '막대: 최근 3년 연평균 성장률, 선: 10년물 분기 평균', R, (box, m) =>
      TT.timeChart(box, { unit: '%', digits: 2, bars: [{ name: '명목 GDP 3년 연평균 성장률', color: '--bar', points: cut(g, m) }],
        series: [{ name: '10년물 분기 평균', color: '--s2', points: cut(y, m) }],
        tipExtra: (q) => (gmap.has(q) && ymap.has(q) ? [{ name: '금리 − 성장률', value: signed(ymap.get(q) - gmap.get(q), 2) + '%p' }] : []) }),
    h('details', { class: 'more' }, h('summary', { text: '수치 표 (최근 40분기)' }),
      TT.table([{ label: '분기' }, { label: '성장률(%)', num: true }, { label: '10년물(%)', num: true }, { label: '금리 − 성장률(%p)', num: true }],
        g.slice(-40).reverse().map((p) => {
          const gap = ymap.has(p[0]) ? ymap.get(p[0]) - p[1] : null;
          return [TT.shortLabel(p[0]), fmt(p[1], 2), fmt(ymap.get(p[0]), 2), { text: signed(gap, 2), cls: tone(gap) }];
        })))));
    if (G.curve) {
      const box = h('div');
      view.append(card('만기별 국채 금리 (' + G.curve.date + ')', '점선은 명목 GDP 3년 연평균 성장률', box));
      requestAnimationFrame(() => TT.catChart(box, { unit: '%', digits: 2,
        cats: G.curve.tenors.map((t) => t.replace(' Mo', '개월').replace(' Yr', '년')),
        series: [{ name: '국채 금리', color: '--s1', values: G.curve.values }],
        refs: [{ y: last(g)[1], label: '성장률 ' + fmt(last(g)[1], 2) + '%' }] }));
    }
    view.append(h('p', { class: 'note', text: '출처: FRED(명목 GDP, 10년물), 미 재무부 일별 수익률곡선.' }));
  }

  function buildFedModel(view, D) {
    const F = D.fedmodel;
    if (!F || !F.obs || !F.obs.length) {
      view.append(empty('아직 받은 자료가 없습니다. 주간 수집(월요일)이 돌면 표시됩니다.'));
      return;
    }
    const ey = F.obs.map((r) => [r[0], +(100 / r[1]).toFixed(2)]);
    const y10 = F.obs.map((r) => [r[0], r[2]]);
    const sp = F.obs.map((r) => [r[0], +(100 / r[1] - r[2]).toFixed(2)]);
    const now = last(F.obs);
    const avg = sp.reduce((a, b) => a + b[1], 0) / sp.length;
    view.append(h('div', { class: 'tiles' },
      tile('S&P 500 선행 PER', fmt(now[1], 1), '배', now[0] + ' 기준'),
      tile('선행 이익수익률', fmt(100 / now[1], 2), '%', '100 ÷ 선행 PER'),
      tile('10년물 금리', fmt(now[2], 2), '%', now[0]),
      tile('이익수익률 − 10년물', signed(100 / now[1] - now[2], 2), '%p', '기간 평균 ' + signed(avg, 2) + '%p'),
      F.avg && F.avg.a5 ? tile('선행 PER 5년·10년 평균', fmt(F.avg.a5, 1) + ' · ' + fmt(F.avg.a10, 1), '배', 'FactSet 보고서 기준') : null));
    view.append(h('p', { class: 'guide' }, '주식의 이익수익률이 국채 금리보다 높을수록 주식이 채권보다 싸다고 보는 단순 비교입니다. ',
      h('b', { text: '명목 금리와 단기 이익 전망을 견준다는 한계' }), '가 있어 참고 지표로만 봅니다. 무료 공개 자료로 다시 계산한 값이라 다른 기관 수치와 0.1%p 안팎 차이가 날 수 있습니다.'));
    const R = [{ id: 'all', label: '전체', months: 0 }, { id: '6m', label: '6개월', months: 6 }, { id: '3m', label: '3개월', months: 3 }];
    view.append(rangeCard('이익수익률과 10년물 금리', '주간', R, (box, m) =>
      TT.timeChart(box, { unit: '%', digits: 2, series: [{ name: '선행 이익수익률', color: '--s2', points: cut(ey, m) }, { name: '10년물', color: '--s1', points: cut(y10, m) }] })));
    view.append(rangeCard('이익수익률 − 10년물', '%p. 점선은 기간 평균', R, (box, m) =>
      TT.timeChart(box, { unit: '%p', digits: 2, zero: true, series: [{ name: '스프레드', color: '--s3', points: cut(sp, m) }], refs: [{ y: +avg.toFixed(2), label: '평균 ' + signed(avg, 2) }] }),
    h('details', { class: 'more' }, h('summary', { text: '수치 표' }),
      TT.table([{ label: '기준일' }, { label: '선행 PER', num: true }, { label: '이익수익률(%)', num: true }, { label: '10년물(%)', num: true }, { label: '스프레드(%p)', num: true }],
        F.obs.slice().reverse().map((r) => [r[0], fmt(r[1], 1), fmt(100 / r[1], 2), fmt(r[2], 2), { text: signed(100 / r[1] - r[2], 2), cls: 'strong' }])))));
    view.append(h('p', { class: 'note', text: '출처: FactSet Earnings Insight(공개 주간 보고서의 선행 12개월 PER 수치), FRED(10년물). 보고서 발행 전 영업일 금리와 짝지었습니다.' }));
  }

  /* ---------- 수집 현황 ---------- */
  function buildStatus(view, D) {
    const S = D._status;
    if (!S) { view.append(empty('아직 수집 기록이 없습니다.')); return; }
    const rows = Object.values(S.sources).map((x) => [
      { text: x.name, cls: 'strong' }, { text: x.ok ? '정상' : '실패', cls: x.ok ? 'status-ok' : 'status-bad' },
      x.latest || '–', kst(x.checked_at), kst(x.updated_at),
      { text: x.ok ? ((x.warnings || []).join(' / ') || '') : x.error, cls: 'dim' }]);
    view.append(card('출처별 수집 결과', '마지막 점검 ' + kst(S.checked_at) + ' (한국 시간)',
      TT.table([{ label: '출처' }, { label: '상태' }, { label: '최근 자료' }, { label: '마지막 점검' }, { label: '마지막 변경' }, { label: '경고·오류' }], rows, { tall: true })));
    view.append(card('수집 일정', null, h('ul', null,
      h('li', { text: '월~토 13:37 — 금리, 회의 일정·점도표, 경제지표, 물가 발표, 연체율, 재정·리프라이싱, 성장률' }),
      h('li', { text: '월요일 13:53 — 연준 모델(주간 보고서)' })),
      h('p', { class: 'note', text: '한 출처가 실패해도 나머지는 그대로 진행하고, 실패한 출처는 직전 수집분을 보여 줍니다. 상대 서버가 호출을 막으면 돌아가지 않고 그 출처만 실패로 남깁니다.' })));
  }

  /* ---------- 메뉴 ---------- */
  const MENUS = [
    { group: '금리', items: [
      { id: 'rates', title: '통화별 지표금리', desc: '달러·유로·엔·원 익일물 지표금리', files: ['rates'], src: 'rates', build: buildRates },
      { id: 'funding', title: '자금조달 여건', desc: '담보·무담보 익일물 금리 차이로 보는 단기자금 사정', files: ['rates'], src: 'rates', build: buildFunding }] },
    { group: '통화정책', items: [
      { id: 'cbank', title: '통화정책회의 일정·점도표', desc: '연준·ECB·일본은행·한국은행 회의 일정과 결과, 연준 점도표', files: ['cbank', 'dots'], src: 'cbank', build: buildCbank }] },
    { group: '물가', items: [
      { id: 'breadth', title: '인플레이션 확산 지표', desc: '물가 상승이 얼마나 넓게 퍼졌는가', files: ['pce'], src: 'infl', build: buildBreadth },
      { id: 'infl', title: 'CPI·PCE 발표 수치', desc: '발표 회차별 전월비·전년비와 항목별 기여도', files: ['infl'], src: 'infl', build: buildInfl }] },
    { group: '미국 경제지표', items: [
      { id: 'price', title: '물가·통화', desc: 'CPI, PCE 물가, M2, 연준 총자산', files: ['macro'], src: 'macro', build: buildPrice },
      { id: 'jobs', title: '고용', desc: '실업률, 고용 증감, 임금, 구인, 실업수당 청구', files: ['macro'], src: 'macro', build: buildJobs },
      { id: 'activity', title: '경기', desc: 'GDP, 산업생산, 소매판매, 연은 활동 지수', files: ['macro'], src: 'macro', build: buildActivity },
      { id: 'delinq', title: '자동차대출 연체율', desc: '90일 이상 연체율과 잔액', files: ['delinq'], src: 'delinq', build: buildDelinq },
      { id: 'fiscal', title: '재정적자·리프라이싱', desc: '기초적자와 국채 리프라이싱 비중', files: ['fiscal', 'refix'], src: 'fiscal', build: buildFiscal },
      { id: 'growth', title: '금리 vs 성장률', desc: '10년물 금리와 명목 GDP 성장률, 만기별 금리', files: ['growth'], src: 'growth', build: buildGrowth },
      { id: 'fedmodel', title: '연준 모델', desc: 'S&P 500 이익수익률과 10년물 금리', files: ['fedmodel'], src: 'fedmodel', build: buildFedModel }] },
    { group: '운영', items: [
      { id: 'status', title: '수집 현황', desc: '출처별 자동 수집 결과', files: [], src: null, build: buildStatus }] },
  ];
  const FLAT = MENUS.flatMap((g) => g.items);

  function drawNav() {
    const nav = $('nav');
    for (const g of MENUS) {
      nav.append(h('h2', { text: g.group }));
      for (const it of g.items) nav.append(h('a', { href: '#' + it.id, 'data-id': it.id, text: it.title }));
    }
  }
  async function show(force) {
    const id = location.hash.replace('#', '') || FLAT[0].id;
    const menu = FLAT.find((m) => m.id === id) || FLAT[0];
    document.querySelectorAll('#nav a').forEach((a) => {
      if (a.dataset.id === menu.id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    $('title').textContent = menu.title;
    $('desc').textContent = menu.desc;
    document.title = menu.title + ' — treasurytotal';
    const view = $('view');
    view.textContent = '';
    view.append(empty('자료를 불러오는 중입니다.'));
    const names = menu.files.concat(['_status']);
    const loaded = await Promise.all(names.map((n) => load(n, force)));
    const D = {};
    names.forEach((n, i) => { D[n] = loaded[i]; });
    const st = D._status && menu.src ? D._status.sources[menu.src] : null;
    $('fresh').textContent = st ? '최근 자료 ' + (st.latest || '–') + ' · 점검 ' + kst(st.checked_at) + (st.ok ? '' : ' · 최근 수집 실패')
      : (D._status ? '점검 ' + kst(D._status.checked_at) : '');
    view.textContent = '';
    if (menu.files.length && menu.files.every((n) => !D[n])) {
      view.append(empty('아직 받은 자료가 없습니다. 자동 수집이 한 번 돌면 표시됩니다.'));
      return;
    }
    try {
      menu.build(view, D);
    } catch (err) {
      view.textContent = '';
      view.append(empty('화면을 그리는 중 문제가 생겼습니다: ' + err.message));
      console.error(err);
    }
    $('rail').classList.remove('open');
    $('menu-toggle').setAttribute('aria-expanded', 'false');
  }

  drawNav();
  window.addEventListener('hashchange', () => show(false));
  $('refresh').addEventListener('click', () => show(true));
  $('menu-toggle').addEventListener('click', () => {
    const open = $('rail').classList.toggle('open');
    $('menu-toggle').setAttribute('aria-expanded', String(open));
    $('menu-toggle').textContent = open ? '메뉴 닫기' : '메뉴 열기';
  });
  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => show(false), 250); });
  show(false);
})();
