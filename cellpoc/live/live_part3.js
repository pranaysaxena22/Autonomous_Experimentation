// ======================================================================== PART 3 (live): the page
// Spliced onto parts 1 and 2 of the replay viewer (the state engine and the drawing), unchanged. This page asks the local live simulation what it has published so far (state) and shows it: the arm is drawn from the
// executed timelines the simulation publishes as each trial starts, and every number on the page is one the simulation published. The page decides nothing and calculates no result: it only moves the clock
// between updates (so the arm moves smoothly) and draws a chart of numbers it was given. It talks only to the program that served it, on this computer.
const Q = new URLSearchParams(location.search);
if (Q.get('embedded') === '1') { const band = document.querySelector('header .band'); if (band) band.style.display = 'none'; document.documentElement.setAttribute('data-theme', 'dark'); }          // inside the unified app the app's own frame is the header: this only hides the page's title band, it changes nothing else
const META = n => { const m = document.querySelector('meta[name="' + n + '"]'); return m ? m.content : ''; };
const TOKEN = META('live-token');                                       // the secret this page's own server wrote into it: a control without it (or from another site) is refused by the server
const TL = DATA.timelines;                                              // grows as the simulation publishes each trial
const S = { s: 0, at: performance.now(), speed: 300, status: 'ready', when: '', duration: 0, results: [], alerts: [], events: [], eventTotal: 0, saved: null, message: '', summary: null, setupId: null, setupLabel: '', setupsKey: '', layoutId: null };
let last = performance.now(), lastId = null, shownTrial = -1, lastChips = '', lastUi = '';
const mmss = s => { s = Math.round(s); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const hhmm = s => { s = Math.round(s / 60); return Math.floor(s / 60) + ' h ' + String(s % 60).padStart(2, '0') + ' min'; };
const simNow = () => S.s + (S.status === 'running' ? (performance.now() - S.at) / 1000 * S.speed : 0);
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function post(cmd, value) {
  return fetch('control', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Live-Token': TOKEN }, body: JSON.stringify({ cmd: cmd, value: value }) }).then(r => r.json()).then(d => { applyState(d); return d; }).catch(() => { $('status').textContent = 'Could not reach the live view'; });
}
function applyState(d) {
  if (!d || d.error) { if (d && d.error) $('status').textContent = d.error; return; }
  if (d.timelines) d.timelines.forEach(t => TL.push(t));
  if (d.event_total !== undefined) {
    if (d.event_total < S.eventTotal) { S.events = []; }                  // a restart: the feed began again
    S.events = S.events.concat(d.events).slice(-200); S.eventTotal = d.event_total;
  }
  Object.assign(S, { s: d.sim_s, at: performance.now(), speed: d.speed, status: d.status, when: d.clock_when, duration: d.duration_s, results: d.results, alerts: d.alerts, saved: d.saved, message: d.message, summary: d.summary || null });
  $('speed').value = String(d.speed);
  if (d.setups) showSetups(d);
}
function showSetups(d) {
  // the setups the page offers come from the server (names only); a different setup may bring a different equipment layout, and then the page is loaded again so that its 3D scene matches
  if (S.layoutId && d.layout_id && d.layout_id !== S.layoutId) { location.reload(); return; }
  S.layoutId = d.layout_id || S.layoutId; S.setupId = d.setup_id; S.setupLabel = d.setup_label;
  const key = JSON.stringify(d.setups); const sel = $('setupSel');
  if (key !== S.setupsKey) { S.setupsKey = key; sel.innerHTML = ''; d.setups.forEach(o => { const x = document.createElement('option'); x.value = o.id; x.textContent = o.label; sel.appendChild(x); }); }
  sel.value = d.setup_id;
}
function poll() {
  fetch('state?tl=' + TL.length + '&ev=' + S.eventTotal, { cache: 'no-store' }).then(r => r.json()).then(applyState)
    .catch(() => { $('status').textContent = 'Lost the connection to the live view. Please stop the live demo and start it again.'; })
    .then(() => setTimeout(poll, 400));
}
function resetLocal() { visionReset(); MJ.key = ''; TL.length = 0; Object.assign(S, { s: 0, status: 'ready', events: [], eventTotal: 0, results: [], alerts: [], saved: null, summary: null, when: '', message: '' }); lastId = null; shownTrial = -1; lastChips = ''; lastUi = ''; }

function verdictClass(tl) { return tl.outcome === 'skipped' ? 'skip' : tl.result.verdict === 'Good' ? 'pass' : 'fail'; }
function buildChips(t, cur) {
  // a trial's colour appears only once its result has been published (its test has finished); until then it is plain
  const key = TL.length + ':' + cur + ':' + S.results.length; if (key === lastChips) return; lastChips = key;
  const strip = $('strip'); strip.innerHTML = '';
  TL.forEach((tl, i) => {
    const row = S.results.find(r => r.trial === tl.trial);
    const b = document.createElement('div');
    b.className = 'tchip' + (row ? ' ' + (row.verdict === 'Good' ? 'pass' : row.verdict === 'No result' ? 'skip' : 'fail') : '') + (tl.outcome === 'completed_after_recovery' && row ? ' rec' : '') + (i === cur ? ' cur' : '');
    b.textContent = tl.trial; b.title = 'Trial ' + tl.trial + (row ? ': ' + row.verdict : ': in progress'); strip.appendChild(b);
  });
}
function renderLists() {
  const key = S.results.length + ':' + S.alerts.length + ':' + S.eventTotal + ':' + S.status + ':' + S.message + ':' + VC.log.length; if (key === lastUi) return; lastUi = key;
  const rows = S.results.slice().reverse().map(r => '<tr class="' + (r.verdict === 'Good' ? 'g' : r.verdict === 'No result' ? 'n' : 'b') + '"><td>' + r.trial + '</td><td>' + esc(r.when) + '</td><td class="num">' + (r.dissolution_pct === null ? '' : r.dissolution_pct.toFixed(1)) + '</td><td class="num">' + (r.hardness_kp === null ? '' : r.hardness_kp.toFixed(2)) + '</td><td>' + r.verdict + '</td></tr>').join('');
  $('results').innerHTML = rows ? '<table><thead><tr><th>Trial</th><th>When</th><th>Dissolution %</th><th>Hardness kP</th><th>Result</th></tr></thead><tbody>' + rows + '</tbody></table>' : '<p class="note">No result yet: a result appears here when its test has finished.</p>';
  $('alerts').innerHTML = S.alerts.length ? S.alerts.slice().reverse().map(a => '<li><b>' + esc(a.when) + '</b> ' + esc(a.message) + '</li>').join('') : '<li class="note">No fault so far.</li>';
  $('events').innerHTML = S.events.slice(-14).reverse().map(e => '<li><b>' + esc(e.when) + '</b> ' + esc(e.message) + '</li>').join('') || '<li class="note">Nothing has happened yet.</li>';
  const good = S.results.length ? S.results[S.results.length - 1].good_so_far : 0, done = S.results.filter(r => r.verdict !== 'No result').length;
  $('kStarted').textContent = TL.length; $('kDone').textContent = done; $('kGood').textContent = good;
  drawChart(); drawDots('chartD', 'dissolution_pct', 100, '%'); drawDots('chartH', 'hardness_kp', 0, ' kP'); renderVlog();
  const st = $('status'); st.className = 'pill ' + S.status;
  st.textContent = S.message || ({ ready: 'Ready: press Start', running: 'Running (simulated time runs faster than real time)', paused: 'Paused', finished: 'Finished: the run window has ended' + (S.summary ? '. ' + S.summary.headline : ''), stopped: 'Stopped', failed: 'Stopped' }[S.status] || S.status);
  $('btnRun').textContent = S.status === 'running' ? 'Pause' : S.status === 'finished' ? 'Finished' : S.status === 'ready' ? 'Start the run' : 'Resume';
  $('btnRun').disabled = S.status === 'finished' || S.status === 'failed';
  $('saved').textContent = S.saved ? 'The finished run has been saved.' : '';
}
// The charts draw numbers the simulation published; the axes only scale them to fit.
function axes(W, H, pl, pr, pt, pb, top, n, fmt) {
  const x = k => pl + (W - pl - pr) * (k - 1) / Math.max(1, n - 1), y = v => H - pb - (H - pb - pt) * v / top;
  let g = '';
  [0, 0.5, 1].forEach(f => { const v = top * f; g += '<line class="gl" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="tx" x="' + (pl - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end">' + fmt(v) + '</text>'; });
  g += '<line class="ax" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
  [1, Math.round(n / 2), n].forEach(k => { g += '<text class="tx" x="' + x(k) + '" y="' + (H - 6) + '" text-anchor="middle">' + k + '</text>'; });
  g += '<text class="tx" x="' + (W - pr) + '" y="' + (pt - 3) + '" text-anchor="end">trial</text>';
  return { x: x, y: y, g: g };
}
const dotClass = r => r.verdict === 'Good' ? 'pg' : r.verdict === 'No result' ? 'pn' : 'pb';
function drawChart() {
  const W = 360, H = 170, n = Math.max(30, TL.length), last = S.results.length ? S.results[S.results.length - 1].good_so_far : 0, top = Math.max(10, last);
  const a = axes(W, H, 28, 10, 16, 22, top, n, v => String(Math.round(v)));
  const pts = S.results.map(r => a.x(r.trial) + ',' + a.y(r.good_so_far));
  const area = pts.length ? '<polygon class="ar" points="' + a.x(S.results[0].trial) + ',' + a.y(0) + ' ' + pts.join(' ') + ' ' + a.x(S.results[S.results.length - 1].trial) + ',' + a.y(0) + '"/>' : '';
  $('chart').innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Good recipes so far, by trial">' + a.g + area + (pts.length ? '<polyline class="ln" points="' + pts.join(' ') + '"/>' : '')
    + S.results.map(r => '<circle class="' + dotClass(r) + '" cx="' + a.x(r.trial) + '" cy="' + a.y(r.good_so_far) + '" r="3"/>').join('') + '<text class="big" x="38" y="34">' + last + '</text></svg>';
}
function drawDots(id, key, fixedTop, unit) {
  const W = 360, H = 170, n = Math.max(30, TL.length), rows = S.results.filter(r => r[key] !== null && r[key] !== undefined);
  const top = fixedTop || Math.max(1, Math.ceil(Math.max(0, ...rows.map(r => r[key])) * 1.15));
  const a = axes(W, H, 34, 10, 16, 22, top, n, v => (v >= 10 ? String(Math.round(v)) : v.toFixed(1)));
  const lastRow = rows.length ? rows[rows.length - 1] : null;
  $(id).innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + key + ' by trial">' + a.g
    + rows.map(r => '<circle class="' + dotClass(r) + '" cx="' + a.x(r.trial) + '" cy="' + a.y(r[key]) + '" r="3.4"/>').join('')
    + (lastRow ? '<text class="big" x="44" y="34">' + lastRow[key].toFixed(unit === '%' ? 1 : 2) + unit + '</text>' : '') + '</svg>';
}
function hud(st, tl, tIn, t, a) {
  $('clockT').textContent = S.when || '—'; $('clockW').textContent = 'run time ' + hhmm(Math.min(t, S.duration || t)) + (S.duration ? ' of ' + hhmm(S.duration) : '');
  document.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', !!a && c.dataset.p === a.phase));
  const n = $('now');
  if (!a) { $('cap').textContent = S.status === 'ready' ? 'Press Start the run.' : 'Waiting for the first trial to start.'; $('fault').style.display = 'none'; $('recov').style.display = 'none'; n.className = 'now'; n.innerHTML = '<b>Between trials</b><small>The next trial starts when the cell reaches it.</small>'; $('res').innerHTML = ''; return; }
  $('cap').textContent = a.caption;
  const failed = a.outcome === 'failed', rec = a.origin === 'recovery';
  $('fault').style.display = failed ? 'block' : 'none'; $('fault').textContent = failed && a.fault ? 'FAULT: ' + a.fault.cause + '. ' + a.fault.detail : '';
  $('recov').style.display = rec ? 'block' : 'none';
  n.className = 'now' + (failed ? ' fail' : rec ? ' rec' : '');
  n.innerHTML = '<b>Trial ' + tl.trial + ': ' + a.id + ' ' + a.type + ' (' + a.step + ', ' + a.phase + ')' + (rec ? ' - RECOVERY of ' + a.recovers : '') + '</b>' + (a.reason ? '<small>Why: ' + esc(a.reason) + '</small><br>' : '') + '<small>' + mmss(tIn) + ' into this trial</small>';
  const res = $('res'); res.innerHTML = '';
  st.readings.forEach(r => { const d = document.createElement('div'); d.className = r.bad ? 'no' : 'ok'; d.innerHTML = '<span>' + (QUANTITY_LABEL[r.quantity] || r.quantity) + '</span><b>' + r.text + '</b>'; res.appendChild(d); });
  if (st.resultsShown) { const x = tl.result, d = document.createElement('div'); d.className = x.verdict === 'Good' ? 'ok' : 'no'; d.innerHTML = '<span>Result of trial ' + tl.trial + '</span><b>' + x.verdict + '</b>'; res.appendChild(d); }
}
// The MuJoCo picture: the server draws the cell with its MuJoCo model (read-only requests for one picture at a time, for the moment the run's clock is at) and this page shows it in place of its own 3D scene.
// If a picture cannot be made (MuJoCo missing, a plan the arm cannot play) the page keeps its own scene; open the page with ?mujoco=0 to keep that scene on purpose.
const MJ = { on: Q.get('mujoco') !== '0', busy: false, last: 0, fails: 0, key: '' };
function mujocoShow(on) {
  const img = $('mj'); if (img) img.style.display = on ? 'block' : 'none';
  if (renderer) renderer.domElement.style.display = on ? 'none' : 'block';
  ['camSel', 'cap', 'recov'].forEach(id => { const e = $(id); if (e) e.style.display = on ? 'none' : ''; });
  const lab = document.querySelector('label[for="camSel"]'); if (lab) lab.style.display = on ? 'none' : '';
}
function mujocoTick(now, tl, tIn) {
  if (!MJ.on || MJ.busy || now - MJ.last < 110) return;
  const idle = !tl;                                               // before the first trial starts the cell is shown at rest, drawn by MuJoCo too
  const key = idle ? 'rest' : tl.trial + ':' + tIn.toFixed(1); if (key === MJ.key) return;
  MJ.busy = true; MJ.last = now;
  const im = new Image();
  im.onload = () => { MJ.key = key; MJ.busy = false; MJ.fails = 0; $('mj').src = im.src; mujocoShow(true); };
  im.onerror = () => { MJ.busy = false; MJ.fails += 1; if (MJ.fails >= 3) { MJ.on = false; mujocoShow(false); } };
  im.src = idle ? 'mujoco.jpg?trial=0&t=0' : 'mujoco.jpg?trial=' + tl.trial + '&t=' + tIn.toFixed(2);
}
// The vision check: when the arm picks up an ingredient bottle the server's vision part reads a photograph of it (there is no camera in the simulation) and reads the bottle's barcode (its identity), then says which solution it holds,
// how full it is and whether it is the bottle the plan asked for. Colour alone cannot tell two ingredients apart, so the barcode decides which bottle it is and the colour is the second look. This page only asks, once per action, and shows the answer:
// the vision panel, a badge over the stage, the count in the top row, a log, and a frame that flashes green (right bottle), red (wrong bottle) or amber (check it) on the stage and the panel.
const VC = { key: '', busy: false, right: 0, wrong: 0, check: 0, seen: {}, log: [] };
const clsOf = v => v === 'right bottle' ? 'ok' : v === 'wrong bottle' ? 'bad' : 'warn';
const MARK = { ok: '\u2713', bad: '\u2717', warn: '!' };
function flash(cls) {
  ['stage', 'vcard'].forEach(id => { const e = $(id); e.classList.remove('fl-look', 'fl-ok', 'fl-bad', 'fl-warn'); if (cls) { void e.offsetWidth; e.classList.add('fl-' + cls); } });
}
function visionKpi() {
  $('kRight').textContent = VC.right; $('kWrong').textContent = VC.wrong; $('kCheck').textContent = VC.check;
  $('seg').innerHTML = '<i class="a" style="flex-grow:' + VC.right + '"></i><i class="b" style="flex-grow:' + VC.wrong + '"></i><i class="c" style="flex-grow:' + VC.check + '"></i>';
}
function vrow(cls, key, html, extra) { return '<div class="vr ' + cls + '"><span class="k">' + key + '</span><span>' + html + (extra || '') + '</span><span class="t">' + (MARK[cls] || '') + '</span></div>'; }
function visionBadge(cls, text) { const b = $('vbadge'); b.className = 'vbadge ' + cls; b.textContent = text; }
function visionInset(cls, text) { const v = $('vinset'); v.className = 'vinset ' + (cls === 'look' ? '' : cls); v.style.display = 'flex'; $('vdot').textContent = cls === 'look' ? '\u2022' : MARK[cls]; $('vinsettext').innerHTML = text; }
function visionReset() {
  Object.assign(VC, { key: '', busy: false, right: 0, wrong: 0, check: 0, seen: {}, log: [] });
  flash(''); visionKpi(); visionBadge('', 'WAITING');
  $('vinset').style.display = 'none'; $('vimg').style.display = 'none'; $('vph').style.display = ''; $('vph').textContent = 'No bottle picked up yet'; $('scan').style.display = 'none'; $('vphoto').classList.remove('looking');
  $('vtext').innerHTML = ''; $('vnote').textContent = '';
  const s = $('vstat'); s.className = 'vv2'; s.innerHTML = '<b>Waiting</b><small>The check starts when the arm picks up the first ingredient bottle.</small>';
}
function visionLooking(tl, a, kind) {
  const tablet = kind === 'tablet', name = tablet ? 'tablet' : esc(String(a.object).replace('bottle_', '')) + ' bottle';
  flash('look'); visionBadge('look', 'LOOKING'); visionInset('look', '<b>' + (tablet ? 'INSPECTING' : 'SCANNING') + '</b> the ' + name);
  $('vtitle').textContent = tablet ? 'Vision check: tablet' : 'Vision check: bottle';
  $('vsub').textContent = tablet ? 'The tablet the arm has just lifted out of the press is inspected for chips, cracks, wear and discolouration. A defective tablet would go to the discard bin instead of the hardness gauge.'
    : 'Every ingredient bottle the arm picks up is checked by the cell\'s camera: it scans the barcode and reads the name (either one identifies the bottle), then looks at the liquid\'s colour and level.';
  $('vphoto').classList.add('looking'); $('scan').style.display = 'block'; $('vph').style.display = $('vimg').style.display === 'block' ? 'none' : ''; $('vph').textContent = 'Camera looking at the ' + name + '...';
  $('vtext').innerHTML = tablet ? vrow('', 'Tablet', 'Inspecting...') : vrow('', 'Barcode', 'Reading...') + vrow('', 'Liquid', 'Looking...');
  const s = $('vstat'); s.className = 'vv2'; s.innerHTML = '<b>' + (tablet ? 'Inspecting' : 'Scanning') + '</b><small>Trial ' + tl.trial + ': the arm holds up the ' + name + ' in front of the camera.</small>';
}
function visionUnavailable(kind) {
  flash(''); visionBadge('', 'NOT AVAILABLE'); $('vinset').style.display = 'none'; $('vphoto').classList.remove('looking'); $('scan').style.display = 'none';
  const s = $('vstat'); s.className = 'vv2 warn'; s.innerHTML = '<b>Check not available</b><small>The ' + kind + ' check is not set up on this computer (the trained network or its demonstration photographs are missing). The run carries on.</small>';
}
// what both kinds of check do when their answer arrives: count it, log it, flash the frames, show the badge and the photograph
function settle(d, kind, cls, verdict, item, reading, insetText) {
  const key = kind + ':' + d.trial + ':' + d.action;
  if (!VC.seen[key]) {
    VC.seen[key] = 1; if (cls === 'ok') VC.right += 1; else if (cls === 'bad') VC.wrong += 1; else VC.check += 1;
    VC.log.push({ trial: d.trial, kind: kind, item: item, reading: reading, verdict: verdict, cls: cls });
  }
  flash(cls); visionKpi(); visionBadge(cls, verdict.toUpperCase());
  visionInset(cls, '<b>' + esc(verdict.toUpperCase()) + '</b> ' + insetText);
  $('vphoto').classList.remove('looking'); $('scan').style.display = 'none'; $('vph').style.display = 'none'; const im = $('vimg'); im.src = d.image; im.style.display = 'block';
}
function showVision(d) {
  const verdict = d.overall || d.verdict, cls = clsOf(verdict);
  settle(d, 'bottle', cls, verdict, d.name + ' bottle', (d.name_read ? d.name_read + ', ' : '') + (d.label_read || 'barcode not read') + (d.read ? ', ' + d.read + ' ' + d.level + '%' : ''), '<code>' + esc(d.name_read || d.label_read || 'nothing read') + '</code>');
  const match = d.label_read && d.label_read === d.label_expected, engine = d.engine === 'model' ? 'trained model' : 'colour rules';
  const colourOk = d.read && d.read === d.expected, lowLevel = d.level !== null && d.level < 15;
  $('vtext').innerHTML =
    vrow(d.label_read ? (match ? 'ok' : 'bad') : 'warn', 'Barcode scanned', '<span class="m">' + esc(d.label_read || 'not readable') + '</span>', d.label_name ? ' <small>' + esc(d.label_name) + ' bottle</small>' : '')
    + (d.name_reader ? vrow(d.name_read ? (d.name_read === d.name_expected ? 'ok' : 'bad') : 'warn', 'Name read', '<span class="m">' + esc(d.name_read || 'not readable') + '</span>') : vrow('warn', 'Name read', 'text reader not installed'))
    + vrow('', 'Plan expects', '<span class="m">' + esc(d.name_expected || '') + '</span> <small>' + esc(d.label_expected || '') + '</small>')
    + vrow(d.read ? (colourOk ? 'ok' : 'warn') : 'warn', 'Liquid colour', d.read ? esc(d.read) + ' <small>(expected ' + esc(d.expected) + ')</small>' : 'not seen')
    + vrow(d.level === null ? 'warn' : (lowLevel ? 'warn' : 'ok'), 'Liquid level', d.level === null ? 'not seen' : d.level + '% full' + (lowLevel ? ' <small>refill soon</small>' : '') + '<div class="gauge"><i style="width:' + d.level + '%"></i><u style="left:15%"></u></div>');
  const s = $('vstat'); s.className = 'vv2 ' + cls; s.innerHTML = '<b>' + esc(verdict.toUpperCase()) + '</b><small>' + esc(d.label_detail || d.detail) + '</small>';
  $('vnote').textContent = 'Trial ' + d.trial + '. ' + (d.demo ? 'Demonstration scenario chosen by the presenter; the run itself is unchanged. ' : '') + 'Illustrative: a photograph stands in for the cell\'s camera, and the stickers are added by the simulation.';
}
function showTablet(d) {
  const defective = d.label === 'defective', cls = defective ? 'bad' : 'ok';
  settle(d, 'tablet', cls, d.verdict, 'tablet', 'defect score ' + d.probability + '%', '<code>score ' + d.probability + '%</code>');
  $('vtext').innerHTML = vrow(cls, 'Tablet', defective ? 'defective' : 'normal')
    + vrow(cls, 'Defect score', d.probability + '% <small>(defective from 50%)</small><div class="gauge' + (defective ? ' bad' : '') + '"><i style="width:' + d.probability + '%"></i><u style="left:50%"></u></div>')
    + vrow(cls, 'Next', esc(d.action_taken));
  const s = $('vstat'); s.className = 'vv2 ' + cls; s.innerHTML = '<b>' + esc(d.verdict.toUpperCase()) + '</b><small>' + (defective ? 'The network found signs of damage (outlined in red on the photograph). ' : 'The network found no sign of damage. ') + esc(d.action_taken) + '</small>';
  $('vnote').textContent = 'Trial ' + d.trial + '. ' + (d.demo ? 'Demonstration scenario chosen by the presenter; the run itself is unchanged. ' : '') + 'Illustrative: a photograph stands in for the cell\'s camera; the simulation makes no real tablet.';
}
function renderVlog() {
  $('vlog').innerHTML = VC.log.length ? '<table><thead><tr><th>Trial</th><th>Check</th><th>Item</th><th>Reading</th><th>Answer</th></tr></thead><tbody>' + VC.log.slice().reverse().map(x => '<tr class="' + (x.cls === 'ok' ? 'g' : x.cls === 'bad' ? 'n' : 'w') + '"><td>' + x.trial + '</td><td>' + esc(x.kind) + '</td><td>' + esc(x.item) + '</td><td class="m">' + esc(x.reading) + '</td><td>' + esc(x.verdict) + '</td></tr>').join('') + '</tbody></table>' : '<p class="note">No check yet: the first appears when the arm picks up an ingredient bottle.</p>';
}
function visionTick(a, tl) {
  if (!a || !tl || a.type !== 'pick') return;
  const bottle = String(a.object || '').startsWith('bottle'), tablet = a.object === 'tablet' && a.from === 'press';           // an ingredient bottle is read; the tablet lifted out of the press is inspected
  if (!bottle && !tablet) return;
  const key = tl.trial + ':' + a.id; if (key === VC.key || VC.busy) return;
  VC.busy = true; visionLooking(tl, a, tablet ? 'tablet' : 'bottle');
  const sel = $('demoSel').value, use = tablet ? sel === 'defective' : ['wrong', 'unreadable', 'blank', 'liquid'].includes(sel), demo = use ? sel : '';
  if (use) $('demoSel').value = '';                                           // a demonstration case applies to the one bottle (or tablet) that comes next, then the camera is shown things as planned again
  const done = (d, show, kind) => { VC.busy = false; VC.key = key; if (d) show(d); else visionUnavailable(kind); };
  if (tablet) fetch('tablet_check?trial=' + tl.trial + '&action=' + a.id + (demo ? '&demo=' + demo : ''), { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(d => done(d, showTablet, 'tablet')).catch(() => { VC.busy = false; });
  else fetch('vision_check?trial=' + tl.trial + '&action=' + a.id + (demo ? '&demo=' + demo : ''), { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(d => done(d, showVision, 'bottle')).catch(() => { VC.busy = false; });
}
function frame(now) {
  last = now; const t = simNow();
  let cur = -1; TL.forEach((tl, i) => { if (tl.trial_start_minute * 60 <= t + 1e-6) cur = i; });
  let st, a = null, tIn = 0, tl = null;
  if (cur >= 0) { tl = TL[cur]; tIn = clamp(t - tl.trial_start_minute * 60, 0, total(tl)); st = simulate(tl, tIn); a = st.current || tl.actions[tl.actions.length - 1]; }
  else if (TL.length) { st = simulate(TL[0], 0); }
  else { st = initialState(); }
  hud(st, tl, tIn, t, a); visionTick(a, tl); buildChips(t, cur); renderLists(); draw(st); mujocoTick(now, tl || TL[0], tIn); requestAnimationFrame(frame);
}
function boot() {
  visionReset();
  const d0 = Q.get('demo'); if (['wrong', 'unreadable', 'blank', 'liquid', 'defective'].includes(d0)) $('demoSel').value = d0;          // a link can open the page with a demonstration case already chosen for the first bottle
  if (GL) build();
  if (MJ.on && renderer) renderer.domElement.style.display = 'none';          // the stage is MuJoCo's picture from the first moment; the page's own 3D scene comes back only if pictures cannot be made
  if (!GL || !renderer) { $('nogl').style.display = 'flex'; }
  const cs = $('camSel'); cs.innerHTML = ''; ['overview', 'top'].concat(L.camera_presets.filter(p => p !== 'overview' && p !== 'top')).forEach(n => { const o = document.createElement('option'); o.value = n; o.textContent = n[0].toUpperCase() + n.slice(1); cs.appendChild(o); });
  cs.onchange = () => setCam(cs.value); const cname = Q.get('cam') || 'overview'; cs.value = cname; setCam(cname);
  $('speed').onchange = () => post('speed', parseFloat($('speed').value));
  $('setupSel').onchange = () => {
    const want = $('setupSel').value, midRun = TL.length > 0 && (S.status === 'running' || S.status === 'paused');
    if (midRun && !confirm('Switching to another setup restarts the run from the beginning. Continue?')) { $('setupSel').value = S.setupId; return; }
    $('status').textContent = 'Preparing the chosen setup...';
    post('setup', want).then(d => { if (d && !d.error) resetLocal(); $('setupSel').value = S.setupId; });
  };
  $('btnRun').onclick = () => post(S.status === 'running' ? 'pause' : 'start');
  $('btnRestart').onclick = () => post('restart').then(resetLocal);
  poll();
  if (Q.get('autostart') === '1' && META('live-autostart') === '1') setTimeout(() => { if (S.status === 'ready') $('btnRun').click(); }, 600);     // only on a server started for tests: the same click handler the Start button has
  requestAnimationFrame(frame);
}
window.__live = { S, TL, simNow, simulate };
boot();
