/* 차트·표 부품. 외부 라이브러리 없이 SVG로 그린다. */
(function () {
  'use strict';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const TT = (window.TT = {});

  TT.h = function (tag, props, ...kids) {
    const e = document.createElement(tag);
    for (const k in (props || {})) {
      if (k === 'class') e.className = props[k];
      else if (k === 'text') e.textContent = props[k];
      else if (k === 'on') for (const ev in props.on) e.addEventListener(ev, props.on[ev]);
      else if (props[k] != null) e.setAttribute(k, props[k]);
    }
    for (const kid of kids.flat()) if (kid != null) e.append(kid);
    return e;
  };
  const h = TT.h;
  const s = (TT.s = function (tag, attrs, text) {
    const e = document.createElementNS(SVG_NS, tag);
    for (const k in (attrs || {})) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  });

  TT.fmt = function (v, digits) {
    if (v == null || Number.isNaN(v)) return '–';
    return Number(v).toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  };
  TT.signed = function (v, digits) {
    if (v == null || Number.isNaN(v)) return '–';
    const t = TT.fmt(Math.abs(v), digits);
    return (v > 0 ? '+' : v < 0 ? '−' : '') + t;
  };

  /* 날짜·분기 표기 → 가로축 위치(일 단위 숫자) */
  TT.xval = function (label) {
    const q = /^(\d{4})Q([1-4])$/.exec(label);
    if (q) return Date.UTC(+q[1], (+q[2] - 1) * 3 + 1, 15) / 864e5;
    if (/^\d{4}$/.test(label)) return Date.UTC(+label, 6, 1) / 864e5;
    if (/^\d{4}-\d{2}$/.test(label)) return Date.UTC(+label.slice(0, 4), +label.slice(5, 7) - 1, 15) / 864e5;
    return Date.UTC(+label.slice(0, 4), +label.slice(5, 7) - 1, +label.slice(8, 10)) / 864e5;
  };
  TT.shortLabel = function (label) {
    const q = /^(\d{4})Q([1-4])$/.exec(label);
    if (q) return q[1] + ' ' + q[2] + '분기';
    return label;
  };

  function niceTicks(lo, hi, count) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const span = hi - lo;
    const raw = span / Math.max(count, 1);
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((m) => m >= raw) || raw;
    const first = Math.floor(lo / step) * step;
    const ticks = [];
    for (let v = first; v <= hi + step * 0.999; v += step) ticks.push(+v.toFixed(10));
    return { ticks, step };
  }
  function stepDigits(step) {
    if (step >= 1) return 0;
    return Math.min(3, Math.ceil(-Math.log10(step) + 0.0001) + (String(step).includes('25') ? 1 : 0));
  }
  function yearTicks(x0, x1, width) {
    const y0 = new Date(x0 * 864e5).getUTCFullYear(), y1 = new Date(x1 * 864e5).getUTCFullYear();
    const spanDays = x1 - x0;
    const out = [];
    if (spanDays > 500) {
      const every = Math.max(1, Math.ceil((y1 - y0 + 1) / Math.max(3, Math.floor(width / 64))));
      const nice = [1, 2, 5, 10, 20].find((n) => n >= every) || every;
      for (let y = Math.ceil(y0 / nice) * nice; y <= y1; y += nice) {
        const x = Date.UTC(y, 0, 1) / 864e5;
        if (x >= x0 && x <= x1) out.push({ x, label: String(y) });
      }
    } else {
      const stepMonths = spanDays > 240 ? 2 : 1;
      const d = new Date(x0 * 864e5);
      let y = d.getUTCFullYear(), m = d.getUTCMonth();
      for (let i = 0; i < 40; i++) {
        const x = Date.UTC(y, m, 1) / 864e5;
        if (x > x1) break;
        if (x >= x0 && m % stepMonths === 0) out.push({ x, label: m === 0 ? String(y) : (m + 1) + '월' });
        m += 1; if (m > 11) { m = 0; y += 1; }
      }
    }
    return out;
  }

  function frame(container, height, legendItems) {
    container.textContent = '';
    if (legendItems && legendItems.length > 1) {
      container.append(h('div', { class: 'legend' }, legendItems.map((it) =>
        h('span', { class: 'lg' },
          h('span', { class: 'key' + (it.kind === 'bar' ? ' key-bar' : it.dash ? ' key-dash' : ''), style: 'background:var(' + it.color + ')' }),
          it.name))));
    }
    const box = h('div', { class: 'chart' });
    container.append(box);
    const width = Math.max(320, Math.round(box.getBoundingClientRect().width || container.clientWidth || 720));
    const svg = s('svg', { viewBox: '0 0 ' + width + ' ' + height, width, height, role: 'img' });
    box.append(svg);
    const tip = h('div', { class: 'tip', hidden: '' });
    box.append(tip);
    return { box, svg, tip, width };
  }
  function placeTip(tip, box, px, py) {
    tip.hidden = false;
    const bw = box.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = px + 14;
    if (left + tw > bw - 4) left = px - tw - 14;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top = Math.max(4, Math.min(py - th / 2, box.clientHeight - th - 4)) + 'px';
  }
  function tipRows(tip, title, rows) {
    tip.textContent = '';
    tip.append(h('div', { class: 'tip-h', text: title }));
    for (const r of rows) {
      tip.append(h('div', { class: 'tip-r' },
        r.color ? h('span', { class: 'key', style: 'background:var(' + r.color + ')' }) : null,
        h('span', { class: 'tip-n', text: r.name }), h('strong', { text: r.value })));
    }
  }

  /* 시계열 선 차트.
     opts.series: [{name, color:'--s1', points:[[표기, 값]], step, dash, dots}]
     opts.bars:   [{name, color, points, colors?:{표기: '--변수'}}]  (같은 세로축을 쓴다)
     opts.refs:   [{y, label}]  opts.marks: [{x:표기, y, label, color}]
     opts.unit, opts.digits, opts.zero(0 기준선), opts.height */
  TT.timeChart = function (container, opts) {
    const height = opts.height || 280;
    const series = (opts.series || []).filter((se) => se.points.length);
    const bars = (opts.bars || []).filter((b) => b.points.length);
    const legend = bars.map((b) => ({ name: b.name, color: b.color, kind: 'bar' })).concat(series);
    const { box, svg, tip, width } = frame(container, height, legend);
    const all = series.concat(bars);
    if (!all.length) { container.append(h('p', { class: 'empty', text: '표시할 자료가 없습니다.' })); return; }
    const digits = opts.digits == null ? 2 : opts.digits;
    const unit = opts.unit || '';
    const M = { l: 46, r: series.length && series.length <= 4 && opts.endLabels !== false ? 58 : 14, t: 10, b: 24 };
    const xs = all.flatMap((se) => se.points.map((p) => TT.xval(p[0])));
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (bars.length) { const pad = (x1 - x0) / Math.max(bars[0].points.length, 1) * 0.6; x0 -= pad; x1 += pad; }
    if (x0 === x1) { x0 -= 1; x1 += 1; }
    const ys = all.flatMap((se) => se.points.map((p) => p[1])).concat((opts.refs || []).map((r) => r.y))
      .concat((opts.marks || []).map((m) => m.y)).filter((v) => v != null);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (opts.zero || bars.length) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    const padY = (hi - lo) * 0.06 || 0.5;
    const tk = niceTicks(lo - (lo < 0 || !(opts.zero || bars.length) ? padY : 0), hi + padY, Math.max(3, Math.floor(height / 60)));
    const yLo = tk.ticks[0], yHi = tk.ticks[tk.ticks.length - 1];
    const X = (v) => M.l + (v - x0) / (x1 - x0) * (width - M.l - M.r);
    const Y = (v) => M.t + (yHi - v) / (yHi - yLo) * (height - M.t - M.b);
    const tickDigits = Math.max(stepDigits(tk.step), 0);

    for (const v of tk.ticks) {
      svg.append(s('line', { class: v === 0 ? 'axis' : 'grid', x1: M.l, x2: width - M.r, y1: Y(v), y2: Y(v) }));
      svg.append(s('text', { class: 'tick', x: M.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, TT.fmt(v, tickDigits)));
    }
    for (const t of yearTicks(x0, x1, width - M.l - M.r)) {
      svg.append(s('text', { class: 'tick', x: X(t.x), y: height - 6, 'text-anchor': 'middle' }, t.label));
    }
    svg.append(s('line', { class: 'axis', x1: M.l, x2: width - M.r, y1: Y(yLo), y2: Y(yLo) }));

    for (const b of bars) {
      const n = b.points.length;
      const bw = Math.max(1, Math.min(18, (width - M.l - M.r) / n - (n > 120 ? 0.6 : 2)));
      for (const [label, value] of b.points) {
        if (value == null) continue;
        const top = Y(Math.max(value, 0)), bottom = Y(Math.min(value, 0));
        svg.append(s('rect', {
          x: X(TT.xval(label)) - bw / 2, y: top, width: bw, height: Math.max(bottom - top, 0.5),
          rx: Math.min(2, bw / 3), fill: 'var(' + ((b.colors && b.colors[label]) || b.color) + ')' }));
      }
    }
    for (const r of opts.refs || []) {
      svg.append(s('line', { class: 'ref', x1: M.l, x2: width - M.r, y1: Y(r.y), y2: Y(r.y) }));
      if (r.label) svg.append(s('text', { class: 'reflabel', x: M.l + 6, y: Y(r.y) - 5 }, r.label));
    }
    const ends = [];
    for (const se of series) {
      let d = '';
      let prev = null;
      for (const [label, value] of se.points) {
        if (value == null) { prev = null; continue; }
        const px = X(TT.xval(label)), py = Y(value);
        if (prev == null) d += 'M' + px.toFixed(1) + ' ' + py.toFixed(1);
        else if (se.step) d += 'H' + px.toFixed(1) + 'V' + py.toFixed(1);
        else d += 'L' + px.toFixed(1) + ' ' + py.toFixed(1);
        prev = [px, py];
      }
      if (se.step && prev) d += 'H' + X(x1).toFixed(1);
      svg.append(s('path', { class: 'line', d, stroke: 'var(' + se.color + ')',
        'stroke-dasharray': se.dash ? '5 4' : null, 'stroke-width': se.width || 2 }));
      if (se.dots) for (const [label, value] of se.points) if (value != null)
        svg.append(s('circle', { class: 'dot', cx: X(TT.xval(label)), cy: Y(value), r: 3.5, fill: 'var(' + se.color + ')' }));
      const last = se.points.filter((p) => p[1] != null).pop();
      if (last) ends.push({ y: Y(last[1]), text: TT.fmt(last[1], digits), color: se.color });
    }
    if (M.r > 20) {
      ends.sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
      for (const e of ends) {
        svg.append(s('circle', { cx: width - M.r + 7, cy: e.y, r: 3, fill: 'var(' + e.color + ')' }));
        svg.append(s('text', { class: 'endlabel', x: width - M.r + 13, y: e.y + 4 }, e.text));
      }
    }
    for (const m of opts.marks || []) {
      const px = X(TT.xval(m.x)), py = Y(m.y);
      svg.append(s('circle', { class: 'dot', cx: px, cy: py, r: 4.5, fill: 'var(' + (m.color || '--ink') + ')' }));
      if (m.label) svg.append(s('text', { class: 'endlabel halo', x: px - 8, y: py - 9, 'text-anchor': 'end' }, m.label));
    }

    /* 호버: 가장 가까운 시점의 값을 모두 보여 준다 */
    const labels = Array.from(new Set(all.flatMap((se) => se.points.map((p) => p[0])))).sort((a, b) => TT.xval(a) - TT.xval(b));
    const lx = labels.map(TT.xval);
    const lookup = all.map((se) => new Map(se.points));
    const cross = s('line', { class: 'cross', y1: M.t, y2: height - M.b, visibility: 'hidden' });
    svg.append(cross);
    const hit = s('rect', { x: M.l, y: M.t, width: width - M.l - M.r, height: height - M.t - M.b, fill: 'transparent' });
    svg.append(hit);
    const valueAt = (i, label) => {
      const se = all[i];
      if (lookup[i].has(label)) return lookup[i].get(label);
      if (!se.step) return undefined;
      let best;
      for (const p of se.points) { if (TT.xval(p[0]) <= TT.xval(label)) best = p[1]; else break; }
      return best;
    };
    const move = (ev) => {
      const rect = svg.getBoundingClientRect();
      const px = (ev.clientX - rect.left) * (width / rect.width);
      const xv = x0 + (px - M.l) / (width - M.l - M.r) * (x1 - x0);
      let best = 0;
      for (let i = 1; i < lx.length; i++) if (Math.abs(lx[i] - xv) < Math.abs(lx[best] - xv)) best = i;
      const label = labels[best];
      cross.setAttribute('x1', X(lx[best])); cross.setAttribute('x2', X(lx[best]));
      cross.setAttribute('visibility', 'visible');
      const rows = [];
      all.forEach((se, i) => {
        const v = valueAt(i, label);
        if (v != null) rows.push({ name: se.name, color: se.color, value: TT.fmt(v, digits) + unit });
      });
      if (opts.tipExtra) rows.push(...opts.tipExtra(label));
      tipRows(tip, TT.shortLabel(label), rows);
      placeTip(tip, box, X(lx[best]) * (rect.width / width), (ev.clientY - rect.top));
    };
    hit.addEventListener('pointermove', move);
    hit.addEventListener('pointerdown', move);
    hit.addEventListener('pointerleave', () => { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); });
  };

  /* 범주 축 차트(만기별 곡선 등). opts.cats: [표기], opts.series: [{name,color,values}], opts.refs */
  TT.catChart = function (container, opts) {
    const height = opts.height || 260;
    const { box, svg, tip, width } = frame(container, height, opts.series);
    const M = { l: 46, r: 16, t: 10, b: 24 };
    const digits = opts.digits == null ? 2 : opts.digits;
    const ys = opts.series.flatMap((se) => se.values).concat((opts.refs || []).map((r) => r.y)).filter((v) => v != null);
    const pad = (Math.max(...ys) - Math.min(...ys)) * 0.1 || 0.5;
    const tk = niceTicks(Math.min(...ys) - pad, Math.max(...ys) + pad, 4);
    const yLo = tk.ticks[0], yHi = tk.ticks[tk.ticks.length - 1];
    const n = opts.cats.length;
    const X = (i) => M.l + (n === 1 ? 0.5 : i / (n - 1)) * (width - M.l - M.r - 20) + 10;
    const Y = (v) => M.t + (yHi - v) / (yHi - yLo) * (height - M.t - M.b);
    for (const v of tk.ticks) {
      svg.append(s('line', { class: 'grid', x1: M.l, x2: width - M.r, y1: Y(v), y2: Y(v) }));
      svg.append(s('text', { class: 'tick', x: M.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, TT.fmt(v, stepDigits(tk.step))));
    }
    opts.cats.forEach((c, i) => svg.append(s('text', { class: 'tick', x: X(i), y: height - 6, 'text-anchor': 'middle' }, c)));
    for (const r of opts.refs || []) {
      svg.append(s('line', { class: 'ref', x1: M.l, x2: width - M.r, y1: Y(r.y), y2: Y(r.y) }));
      if (r.label) svg.append(s('text', { class: 'reflabel', x: M.l + 6, y: Y(r.y) - 5 }, r.label));
    }
    for (const se of opts.series) {
      let d = '';
      se.values.forEach((v, i) => { if (v != null) d += (d ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); });
      svg.append(s('path', { class: 'line', d, stroke: 'var(' + se.color + ')' }));
      se.values.forEach((v, i) => {
        if (v == null) return;
        const c = s('circle', { class: 'dot', cx: X(i), cy: Y(v), r: 4, fill: 'var(' + se.color + ')' });
        const target = s('circle', { cx: X(i), cy: Y(v), r: 14, fill: 'transparent' });
        target.addEventListener('pointerenter', () => {
          tipRows(tip, opts.cats[i], [{ name: se.name, color: se.color, value: TT.fmt(v, digits) + (opts.unit || '') }]);
          placeTip(tip, box, X(i) * (svg.getBoundingClientRect().width / width), Y(v));
        });
        target.addEventListener('pointerleave', () => { tip.hidden = true; });
        svg.append(c, target);
      });
    }
  };

  /* 점도표. years: [..], bins: [[중간값, [연도별 인원]]], medians: [..], current: 숫자|null */
  TT.dotPlot = function (container, opts) {
    const height = 360;
    const { box, svg, tip, width } = frame(container, height, null);
    const M = { l: 50, r: 16, t: 12, b: 28 };
    const mids = opts.bins.map((b) => b[0]);
    const lo = Math.min(...mids, opts.current == null ? Infinity : opts.current) - 0.25;
    const hi = Math.max(...mids, opts.current == null ? -Infinity : opts.current) + 0.25;
    const n = opts.years.length;
    const colW = (width - M.l - M.r) / n;
    const Y = (v) => M.t + (hi - v) / (hi - lo) * (height - M.t - M.b);
    for (let v = Math.ceil(lo * 4) / 4; v <= hi + 1e-9; v += 0.25) {
      const whole = Math.abs(v * 2 - Math.round(v * 2)) < 1e-9;
      svg.append(s('line', { class: 'grid', x1: M.l, x2: width - M.r, y1: Y(v), y2: Y(v), opacity: whole ? 1 : 0.45 }));
      if (whole) svg.append(s('text', { class: 'tick', x: M.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, TT.fmt(v, 1)));
    }
    opts.years.forEach((year, i) => {
      const cx = M.l + colW * (i + 0.5);
      svg.append(s('text', { class: 'tick', x: cx, y: height - 8, 'text-anchor': 'middle' }, year));
      if (i > 0) svg.append(s('line', { class: 'grid', x1: M.l + colW * i, x2: M.l + colW * i, y1: M.t, y2: height - M.b }));
    });
    if (opts.current != null) {
      svg.append(s('line', { class: 'ref', x1: M.l, x2: width - M.r, y1: Y(opts.current), y2: Y(opts.current) }));
      svg.append(s('text', { class: 'reflabel', x: M.l + 6, y: Y(opts.current) - 5 }, '현재 목표범위 중간값 ' + TT.fmt(opts.current, 3)));
    }
    const gap = Math.min(11, (colW - 16) / 19 * 1.0 + 4);
    for (const [mid, counts] of opts.bins) {
      counts.forEach((count, i) => {
        if (!count) return;
        const cx = M.l + colW * (i + 0.5);
        for (let k = 0; k < count; k++) {
          svg.append(s('circle', { class: 'dot', cx: cx + (k - (count - 1) / 2) * gap, cy: Y(mid), r: 4, fill: 'var(--s1)' }));
        }
        const target = s('rect', { x: cx - colW / 2 + 2, y: Y(mid) - 7, width: colW - 4, height: 14, fill: 'transparent' });
        target.addEventListener('pointerenter', () => {
          tipRows(tip, opts.years[i], [{ name: '금리 ' + TT.fmt(mid, 3) + '%', value: count + '명' }]);
          placeTip(tip, box, cx * (svg.getBoundingClientRect().width / width), Y(mid));
        });
        target.addEventListener('pointerleave', () => { tip.hidden = true; });
        svg.append(target);
      });
    }
    opts.medians.forEach((m, i) => {
      if (m == null) return;
      const cx = M.l + colW * (i + 0.5);
      svg.append(s('line', { class: 'median', x1: cx - colW * 0.34, x2: cx + colW * 0.34, y1: Y(m), y2: Y(m) }));
      svg.append(s('text', { class: 'endlabel halo', x: cx + colW * 0.34 + 4, y: Y(m) + 4 }, TT.fmt(m, 1)));
    });
  };

  /* 가로 막대 순위. rows: [{label, value, note}] */
  TT.hbars = function (container, rows, opts) {
    container.textContent = '';
    const digits = opts.digits == null ? 2 : opts.digits;
    const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9);
    const hasNeg = rows.some((r) => r.value < 0);
    const wrap = h('div', { class: 'hbars' });
    for (const r of rows) {
      const share = Math.abs(r.value) / max * (hasNeg ? 50 : 100);
      const bar = h('span', { class: 'hbar-fill' + (r.value < 0 ? ' neg' : ''),
        style: 'width:' + share.toFixed(1) + '%;' + (hasNeg ? (r.value < 0 ? 'right:50%' : 'left:50%') : 'left:0') });
      wrap.append(h('div', { class: 'hbar-row', title: r.label + ' ' + TT.signed(r.value, digits) + (opts.unit || '') },
        h('span', { class: 'hbar-label' }, r.label, r.note ? h('small', { text: ' ' + r.note }) : null),
        h('span', { class: 'hbar-track' + (hasNeg ? ' mid' : '') }, bar),
        h('span', { class: 'hbar-value', text: TT.signed(r.value, digits) })));
    }
    container.append(wrap);
  };

  /* 표. columns: [{label, num, cls}], rows: [[값 또는 {text, cls, indent}]] */
  TT.table = function (columns, rows, opts) {
    const table = h('table');
    table.append(h('thead', null, h('tr', null, columns.map((c) => h('th', { class: c.num ? 'num' : null, text: c.label })))));
    const body = h('tbody');
    for (const row of rows) {
      body.append(h('tr', null, row.map((cell, i) => {
        const c = cell != null && typeof cell === 'object' ? cell : { text: cell };
        const td = h('td', { class: [columns[i].num ? 'num' : '', c.cls || ''].join(' ').trim() || null,
          text: c.text == null ? '–' : String(c.text) });
        if (c.indent) td.style.paddingLeft = (10 + c.indent * 14) + 'px';
        return td;
      })));
    }
    table.append(body);
    return h('div', { class: 'scroll' + (opts && opts.tall ? ' tall' : '') }, table);
  };

  /* 기간 선택 버튼 */
  TT.segmented = function (items, current, onPick) {
    const seg = h('div', { class: 'seg', role: 'group' });
    items.forEach((it) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(it.id === current), text: it.label });
      b.addEventListener('click', () => {
        seg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', 'false'));
        b.setAttribute('aria-pressed', 'true');
        onPick(it.id);
      });
      seg.append(b);
    });
    return seg;
  };
})();
