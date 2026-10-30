// ======================================================================== PART 3 (console): the page
// Spliced onto parts 1 and 2 of the replay viewer (the state engine and the drawing), unchanged. This page asks the local live simulation what it has published so far (state) and shows it: every number on the page is one the
// simulation published, or a count of such things. The page decides nothing and calculates no result: it only moves the clock between updates, scales bars and charts to fit, and lays the answers out. It talks only to the program that served it, on this computer.
const Q = new URLSearchParams(location.search);
// the look: light or dark, both in the brand's colours. ?theme= chooses it, else the last choice made in this browser, else light
const THEME_KEY = 'console-theme';
function savedTheme() { try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; } }
function setTheme(name, remember) {
  document.documentElement.setAttribute('data-theme', name);
  const b = document.getElementById('themeBtn'); if (b) { b.textContent = name === 'dark' ? 'Light' : 'Dark'; b.setAttribute('aria-label', 'Switch to the ' + (name === 'dark' ? 'light' : 'dark') + ' look'); }
  if (remember) { try { localStorage.setItem(THEME_KEY, name); } catch (e) { /* private window: the choice just is not remembered */ } }
}
setTheme(Q.get('theme') === 'dark' || Q.get('theme') === 'light' ? Q.get('theme') : (savedTheme() === 'dark' ? 'dark' : 'light'), false);
const META = n => { const m = document.querySelector('meta[name="' + n + '"]'); return m ? m.content : ''; };
const TOKEN = META('live-token');                                       // the secret this page's own server wrote into it: a control without it (or from another site) is refused by the server
const TL = DATA.timelines;                                              // grows as the simulation publishes each trial
const S = { s: 0, at: performance.now(), speed: 300, status: 'ready', when: '', duration: 0, results: [], alerts: [], events: [], eventTotal: 0, saved: null, message: '', summary: null, setupId: null, setupLabel: '', setupsKey: '', layoutId: null, approval: null, decisions: [], replacedTotal: 0, queue: null, epoch: '', design: null, whatif: null };
let gateSig = '', queueSig = '', designSig = '';
let lastUi = '', lastChips = '', lastAct = '', lastPhase = '', TAB = 'overview', ARMKIND = '';
const mmss = s => { s = Math.round(s); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const hhmm = s => { s = Math.round(s / 60); return Math.floor(s / 60) + ' h ' + String(s % 60).padStart(2, '0') + ' min'; };
const simNow = () => S.s + (S.status === 'running' ? (performance.now() - S.at) / 1000 * S.speed : 0);
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ---------------------------------------------------------------- what the page says about the product (fixed text)
const CHALLENGE = [
  ['9 experiments a week', 'What a team can run by hand. This is an assumption: replace it with your own figure.'],
  ['8 h a day, five days a week', 'Typical working hours. Nights and weekends are lost, so good recipes wait.'],
  ['By eye: every bottle, every tablet', 'Which bottle, how full, is the tablet damaged: each one is checked by a person.'],
];
const SOLUTION = [
  ['A robot does the lab work', 'The arm weighs, mixes, presses and tests tablets, trial after trial, with nobody in the lab.'],
  ['Cameras check everything', 'Every ingredient bottle is identified by its barcode and printed name and its liquid is checked; every pressed tablet is inspected.'],
  ['An engine chooses what to try next', 'Each new recipe comes from the results so far. Faults are handled, and the morning team gets a handover.'],
];
const SHOWS = [
  'A robotic lab station that makes and tests tablets by itself, trial after trial, day and night.',
  'How the cell chooses its next recipe, copes when something goes wrong (for example a jammed bottle) and hands over to the morning team.',
  "The cell's cameras at work: reading which bottle is which (barcode and printed name), how full it is, and inspecting every pressed tablet.",
];
const NOSHOW = [
  'Real tablets. Every number (dissolution, hardness, timings, results) is an illustrative value from a simulation. It says nothing about real products.',
  'A real robot. The arm, its reach and its timings are stand-ins; a real arm and real instruments would behave differently.',
  "The cameras on real equipment. The photographs are stock photographs standing in for the cell's camera, and the stickers on the bottles are added by the simulation. The camera checks were trained on public photographs and have not seen your bottles, labels, lighting or tablets, so how accurate they are on your equipment is not known.",
  'A promised speed-up. The comparison with manual work (9 trials a week) is an assumption: replace it with your own figure.',
  'Safety, quality or regulatory approval. Nothing here has been validated for use in a regulated laboratory.',
  'An exact number of trials. About 29 to 30 trials fit a run; the exact count depends on a small timing margin.',
];
const EXPLAIN = {
  overview: ['Overview', 'This view is for leadership and clients. The top says what the product is; the challenge and the solution say why it matters. The six tiles count what the simulated cell has done so far, as it happens. Needs attention lists faults and alerts, Trial status colours each trial once its result is published, and the loop at the bottom lights the phase the cell is in right now. Every number is illustrative.'],
  operator: ['Operator', 'This view is for the person watching the cell. The picture is the cell as the simulation publishes each moment, and the five steps show where the current trial is. When the arm lifts an ingredient bottle the camera scans its barcode, reads its printed name and looks at the liquid; a pressed tablet is inspected the same way. A green frame means right, red means wrong, amber means please check. Inject event arms a wrong bottle or a defective tablet for the next pick, so you can see how the cell reacts. The panel "How the engine chose this recipe" shows the reasoning behind the latest decision of the engine: how likely it thinks the recipe is to pass, what it expects to measure and how unsure it is, and which earlier results it is reacting to. Some findings are high risk: if the cell finds a vial that is not the one the plan expects, the run stops and a red card asks a person to accept or reject it. Rejecting skips that batch and the cell moves on by itself. Faults the cell can fix alone are tagged low risk and carry on.'],
  try: ['Try it', 'This view lets you try your own recipe. Type a value for each ingredient, within the ranges shown, and press the button. The virtual lab measures the recipe, says whether it meets both specifications, and the engine says what it would try next and why. The engine has already seen the usual six starting recipes, and sees yours as the next trial. Everything is illustrative: the lab and the engine are simulations.'],
  jobs: ['Jobs', 'This view is for the person who plans the work. It lists the jobs for several drugs, each one a whole run, and says where each one stands: pending, in progress, completed or blocked. Start one job, or run the whole queue and it works through them by itself, one at a time. A job that runs out of an ingredient stops and is marked blocked, with the reason, and the queue moves on to the next. The shelf shows how much of each ingredient is left, and Restock fills it again. The order is first come, first served for now, and the shelf is a made-up one.'],
  manager: ['Lab manager', 'This view is for the person who runs the lab. It shows what needs a person, every result as its test finishes, how the results develop over the run, and the log of faults, alerts and events. A person is asked only when the cell cannot carry on alone.'],
};
const PIPE = [['dispense', 'Dispense'], ['mix', 'Mix'], ['press', 'Press'], ['test', 'Test'], ['clean', 'Clean']];
const PHASES = [['sense', 'Sense', 'Reads the instruments'], ['reason', 'Reason', 'Chooses the next recipe'], ['act', 'Act', 'Makes and tests the tablets'], ['adapt', 'Adapt', 'Recovers from faults, then hands over']];
const ARMTEXT = { wrong: 'a wrong bottle', unreadable: 'an unreadable barcode', blank: 'a bottle with no stickers', liquid: 'a liquid that does not match', defective: 'a defective tablet' };

// ---------------------------------------------------------------- talking to the live program
function post(cmd, value) {
  return fetch('control', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Live-Token': TOKEN }, body: JSON.stringify({ cmd: cmd, value: value }) }).then(r => r.json()).then(d => { applyState(d); return d; }).catch(() => { toast('Could not reach the live view'); });
}
function applyState(d) {
  if (!d || d.error) { if (d && d.error) toast(d.error); tryDone(); return; }
  if (d.whatif) { S.whatif = d.whatif; renderTry(); return; }                    // the answer to a recipe typed on the Try it view
  if (d.epoch !== undefined) {                                           // a different run than the page was showing (the next job of the queue began): start the page over from this run's beginning
    const changed = S.epoch && d.epoch !== S.epoch;
    S.epoch = d.epoch;
    if (changed) { resetLocal(); return; }
  }
  if (d.timelines) d.timelines.forEach(t => TL.push(t));
  if (d.event_total !== undefined) {
    if (d.event_total < S.eventTotal) { S.events = []; }                  // a restart: the feed began again
    S.events = S.events.concat(d.events).slice(-200); S.eventTotal = d.event_total;
  }
  if (d.replaced) d.replaced.forEach(t => { const i = TL.findIndex(x => x.trial === t.trial); if (i >= 0) TL[i] = t; });                       // an accepted vial changes how a trial that was already published goes on
  if (d.replaced_total !== undefined) S.replacedTotal = d.replaced_total;
  Object.assign(S, { s: d.sim_s, at: performance.now(), speed: d.speed, status: d.status, when: d.clock_when, duration: d.duration_s, results: d.results, alerts: d.alerts, saved: d.saved, message: d.message, summary: d.summary || null,
    approval: d.approval === undefined ? S.approval : d.approval, decisions: d.decisions || S.decisions });
  gateChanged();
  if (d.jobs) { const sig = JSON.stringify(d.jobs); if (sig !== queueSig) { queueSig = sig; S.queue = d.jobs; lastUi = ''; } }
  if (d.design) { const sig = JSON.stringify(d.design); if (sig !== designSig) { designSig = sig; S.design = d.design; S.whatif = null; renderTryForm(); renderTry(); } }
  if (d.setups) showSetups(d);
}
function showSetups(d) {
  if (S.layoutId && d.layout_id && d.layout_id !== S.layoutId) { location.reload(); return; }       // a different setup may bring a different equipment layout: load the page again so that its scene matches
  S.layoutId = d.layout_id || S.layoutId; S.setupId = d.setup_id; S.setupLabel = d.setup_label;
  const key = JSON.stringify(d.setups), sel = $('setupSel');
  if (key !== S.setupsKey) { S.setupsKey = key; sel.innerHTML = ''; d.setups.forEach(o => { const x = document.createElement('option'); x.value = o.id; x.textContent = o.label; sel.appendChild(x); }); }
  sel.value = d.setup_id;
}
function poll() {
  fetch('state?tl=' + TL.length + '&ev=' + S.eventTotal + '&rp=' + S.replacedTotal, { cache: 'no-store' }).then(r => r.json()).then(applyState)
    .catch(() => { toast('Lost the connection to the live view. Please close this page and open it again.'); })
    .then(() => setTimeout(poll, 400));
}
function resetLocal() { visionReset(); MJ.key = ''; TL.length = 0; Object.assign(S, { s: 0, status: 'ready', events: [], eventTotal: 0, results: [], alerts: [], saved: null, summary: null, when: '', message: '', approval: null, decisions: [], replacedTotal: 0 }); gateSig = ''; renderGate(); lastUi = ''; lastChips = ''; lastAct = ''; }

// ---------------------------------------------------------------- small helpers
function toast(text) {
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = text; $('toast').appendChild(t);
  setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 3600);
}
function setTab(name) {
  TAB = name;
  document.querySelectorAll('#tabs button').forEach(b => { const on = b.dataset.tab === name; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); });
  ['overview', 'operator', 'manager', 'jobs', 'try'].forEach(n => $('view-' + n).classList.toggle('on', n === name));
  lastUi = ''; lastChips = ''; MJ.key = '';
}
function setArm(kind) {
  ARMKIND = kind;
  $('armed').classList.toggle('show', !!kind); $('armedText').textContent = kind ? 'Armed: ' + ARMTEXT[kind] + ' at the next ' + (kind === 'defective' ? 'tablet inspection' : 'bottle pick') : '';
}
function closeMenus() { document.querySelectorAll('.menu').forEach(m => m.classList.remove('open')); }
function toggleMenu(id) { const m = $(id), was = m.classList.contains('open'); closeMenus(); if (!was) m.classList.add('open'); }
function startRun(speed) { const go = () => post('start'); if (speed) post('speed', speed).then(go); else go(); }

// ---------------------------------------------------------------- the picture of the cell, drawn by MuJoCo on the server
const MJ = { on: Q.get('mujoco') !== '0', busy: false, last: 0, fails: 0, key: '' };
// the address of the cell's picture; a recorded replay (window.REPLAY_PICTURE) answers from the pictures it carries instead of asking a server
const pictureUrl = (trial, t) => window.REPLAY_PICTURE ? window.REPLAY_PICTURE(trial, t) : (trial === 0 ? 'mujoco.jpg?trial=0&t=0' : 'mujoco.jpg?trial=' + trial + '&t=' + t.toFixed(2));
function mujocoShow(on) {
  const img = $('mj'); if (img) img.style.display = on ? 'block' : 'none';
  if (renderer) renderer.domElement.style.display = on ? 'none' : 'block';
}
function mujocoTick(now, tl, tIn) {
  if (!MJ.on || MJ.busy || now - MJ.last < 110 || TAB !== 'operator') return;
  const idle = !tl, key = idle ? 'rest' : tl.trial + ':' + tIn.toFixed(1);
  if (key === MJ.key) return;
  MJ.busy = true; MJ.last = now;
  const im = new Image();
  im.onload = () => { MJ.key = key; MJ.busy = false; MJ.fails = 0; $('mj').src = im.src; mujocoShow(true); };
  im.onerror = () => { MJ.busy = false; MJ.fails += 1; if (MJ.fails >= 3) { MJ.on = false; mujocoShow(false); } };
  im.src = idle ? pictureUrl(0, 0) : pictureUrl(tl.trial, tIn);
}
function heroPicture() {
  const im = new Image();
  im.onload = () => { $('heroImg').src = im.src; };
  im.onerror = () => { $('heroShot').style.display = 'none'; $('hero').style.gridTemplateColumns = 'minmax(0,1fr)'; };
  im.src = pictureUrl(0, 0);
}

// ---------------------------------------------------------------- the cell's cameras: a check when the arm picks up an ingredient bottle or lifts the tablet out of the press
const VC = { key: '', busy: false, right: 0, wrong: 0, check: 0, seen: {}, log: [], sel: -1 };
const clsOf = v => v === 'right bottle' ? 'ok' : v === 'wrong bottle' ? 'bad' : 'warn';
function flash(cls) {
  ['stage', 'pCam'].forEach(id => { const e = $(id); e.classList.remove('fl-look', 'fl-ok', 'fl-bad', 'fl-warn'); if (cls) { void e.offsetWidth; e.classList.add('fl-' + cls); } });
}
function inset(cls, html) { const v = $('vinset'); v.className = 'vinset ' + (cls === 'look' ? '' : cls); v.style.display = 'flex'; $('vdot').textContent = cls === 'look' ? '•' : cls === 'ok' ? '✓' : cls === 'bad' ? '✗' : '!'; $('vinsettext').innerHTML = html; }
function camHead(cls, tagText, banner, small) {
  const t = $('camTag'); t.className = 'tag ' + cls; t.textContent = tagText;
  const b = $('camBan'); b.className = 'ban ' + cls; b.innerHTML = esc(banner) + '<small>' + small + '</small>';
}
function visionReset() {
  Object.assign(VC, { key: '', busy: false, right: 0, wrong: 0, check: 0, seen: {}, log: [], sel: -1 });
  flash(''); $('vinset').style.display = 'none';
  camHead('', 'waiting', 'WAITING', 'The check starts when the arm picks up an ingredient bottle');
  $('camImg').style.display = 'none'; $('camHold').style.display = ''; $('camHold').textContent = 'No bottle picked up yet'; $('camScan').style.display = 'none'; $('camPhoto').classList.remove('looking');
  $('camChips').innerHTML = ''; $('camTitle').textContent = 'Camera check';
  lastUi = '';
}
function visionLooking(tl, a, kind) {
  const tablet = kind === 'tablet', name = tablet ? 'tablet' : esc(String(a.object).replace('bottle_', '')) + ' bottle';
  flash('look'); $('camTitle').textContent = tablet ? 'Camera check: tablet' : 'Camera check: bottle';
  camHead('look', 'looking', tablet ? 'INSPECTING' : 'SCANNING', 'Trial ' + tl.trial + ': the arm holds up the ' + name + ' in front of the camera');
  inset('look', '<b>' + (tablet ? 'INSPECTING' : 'SCANNING') + '</b> the ' + name);
  $('camPhoto').classList.add('looking'); $('camScan').style.display = 'block'; $('camHold').style.display = $('camImg').style.display === 'block' ? 'none' : ''; $('camHold').textContent = 'Camera looking at the ' + name + '...';
}
function visionUnavailable(kind) {
  flash(''); camHead('warn', 'not available', 'NOT AVAILABLE', 'The ' + kind + ' check is not set up on this computer. The run carries on.'); $('vinset').style.display = 'none'; $('camPhoto').classList.remove('looking'); $('camScan').style.display = 'none';
}
function settle(d, kind, cls, verdict, item, banner, stats) {
  const key = kind + ':' + d.trial + ':' + d.action;
  if (!VC.seen[key]) {
    VC.seen[key] = 1; if (cls === 'ok') VC.right += 1; else if (cls === 'bad') VC.wrong += 1; else VC.check += 1;
    VC.log.push({ trial: d.trial, kind: kind, item: item, verdict: verdict, cls: cls, d: d }); VC.sel = VC.log.length - 1;
  }
  flash(cls); camHead(cls, cls === 'ok' ? 'passed' : cls === 'bad' ? 'failed' : 'please check', banner, stats);
  inset(cls, '<b>' + esc(verdict.toUpperCase()) + '</b> <code>' + esc(kind === 'tablet' ? 'score ' + d.probability + '%' : (d.name_read || d.label_read || 'nothing read')) + '</code>');
  $('camPhoto').classList.remove('looking'); $('camScan').style.display = 'none'; $('camHold').style.display = 'none'; const im = $('camImg'); im.src = d.image; im.style.display = 'block';
  lastUi = '';
}
function cchip(cls, label, value, extra) { return '<span class="cc ' + cls + '">' + esc(label) + ' <b>' + value + '</b>' + (extra || '') + '</span>'; }
function gauge(pct, mark, bad) { return '<span class="gauge' + (bad ? ' bad' : '') + '"><i style="width:' + pct + '%"></i><u style="left:' + mark + '%"></u></span>'; }
function showVision(d) {
  const verdict = d.overall || d.verdict, cls = clsOf(verdict), codeOk = d.label_read && d.label_read === d.label_expected, nameOk = d.name_read && d.name_read === d.name_expected;
  const stats = 'barcode ' + (d.label_read ? (codeOk ? '✓' : '✗') : 'not read') + ' &middot; name ' + (d.name_reader ? (d.name_read ? (nameOk ? '✓' : '✗') : 'not read') : 'n/a') + ' &middot; liquid ' + (d.read ? esc(d.read) + ' ' + d.level + '%' : 'not seen');
  settle(d, 'bottle', cls, verdict, d.name + ' bottle', verdict.toUpperCase(), stats);
  const low = d.level !== null && d.level < 15;
  $('camChips').innerHTML = cchip(d.label_read ? (codeOk ? 'ok' : 'bad') : 'warn', 'Barcode', '<code>' + esc(d.label_read || 'not readable') + '</code>')
    + (d.name_reader ? cchip(d.name_read ? (nameOk ? 'ok' : 'bad') : 'warn', 'Name', esc(d.name_read || 'not readable')) : '')
    + cchip('', 'Plan expects', esc(d.name_expected || '') + ' <code>' + esc(d.label_expected || '') + '</code>')
    + cchip(d.read ? (d.read === d.expected ? 'ok' : 'warn') : 'warn', 'Liquid', d.read ? esc(d.read) + ' <span style="color:var(--muted)">(expected ' + esc(d.expected) + ')</span>' : 'not seen')
    + (d.level === null ? '' : cchip(low ? 'warn' : 'ok', 'Level', d.level + '%', ' ' + gauge(d.level, 15, false)));
  $('camNote').textContent = (d.label_detail || d.detail) + ' ' + (d.demo ? 'Demonstration scenario chosen by the presenter; the run itself is unchanged. ' : '') + 'Illustrative: a photograph stands in for the cell\'s camera, and the stickers are added by the simulation.';
}
function showTablet(d) {
  const defective = d.label === 'defective', cls = defective ? 'bad' : 'ok';
  settle(d, 'tablet', cls, d.verdict, 'tablet', d.verdict.toUpperCase(), 'defect score ' + d.probability + '%');
  $('camChips').innerHTML = cchip(cls, 'Tablet', defective ? 'defective' : 'normal') + cchip(cls, 'Defect score', d.probability + '%', ' ' + gauge(d.probability, 50, defective)) + cchip(cls, 'Next', esc(d.action_taken));
  $('camNote').textContent = (defective ? 'The network found signs of damage (outlined in red on the photograph). ' : 'The network found no sign of damage. ') + (d.demo ? 'Demonstration scenario chosen by the presenter; the run itself is unchanged. ' : '') + 'Illustrative: a photograph stands in for the cell\'s camera; the simulation makes no real tablet.';
}
function visionTick(a, tl) {
  if (!a || !tl || a.type !== 'pick') return;
  const bottle = String(a.object || '').startsWith('bottle'), tablet = a.object === 'tablet' && a.from === 'press';           // an ingredient bottle is read; the tablet lifted out of the press is inspected
  if (!bottle && !tablet) return;
  const key = tl.trial + ':' + a.id; if (key === VC.key || VC.busy) return;
  VC.busy = true; visionLooking(tl, a, tablet ? 'tablet' : 'bottle');
  const use = tablet ? ARMKIND === 'defective' : ['wrong', 'unreadable', 'blank', 'liquid'].includes(ARMKIND), demo = use ? ARMKIND : '';
  if (use) setArm('');                                                        // an armed scenario applies to the one bottle (or tablet) that comes next
  const done = (d, show, kind) => { VC.busy = false; VC.key = key; if (d) show(d); else visionUnavailable(kind); };
  if (tablet) fetch('tablet_check?trial=' + tl.trial + '&action=' + a.id + (demo ? '&demo=' + demo : ''), { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(d => done(d, showTablet, 'tablet')).catch(() => { VC.busy = false; });
  else fetch('vision_check?trial=' + tl.trial + '&action=' + a.id + (demo ? '&demo=' + demo : ''), { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(d => done(d, showVision, 'bottle')).catch(() => { VC.busy = false; });
}

// ---------------------------------------------------------------- drawing the views
const verdictOf = tl => tl.outcome === 'skipped' ? 'skip' : (tl.result && tl.result.verdict === 'Good') ? 'pass' : 'fail';
function chipsHtml(cur) {
  return TL.map((tl, i) => {
    const row = S.results.find(r => r.trial === tl.trial);
    const cls = row ? (row.verdict === 'Good' ? 'pass' : row.verdict === 'No result' ? 'skip' : 'fail') : '';
    return '<div class="tchip ' + cls + (tl.outcome === 'completed_after_recovery' && row ? ' rec' : '') + (i === cur ? ' cur' : '') + '" title="Trial ' + tl.trial + (row ? ': ' + esc(row.verdict) : ': in progress') + '">' + tl.trial + '</div>';
  }).join('') || '<span class="empty">The trials appear here as the cell starts them.</span>';
}
function alertInfo(a) {
  return { fault: ['bad', 'Fault'], recovery: ['ok', 'Recovered'], candidate_skipped: ['warn', 'Skipped'], alert_queued: ['bad', 'Waiting for staff'], batch_rejected: ['ok', 'Batch rejected'], deviation_accepted: ['warn', 'Accepted deviation'], job_blocked: ['bad', 'Job blocked'] }[a.kind] || ['', a.kind];
}
function svgAxes(W, H, pl, pr, pt, pb, top, n, fmt) {
  const x = k => pl + (W - pl - pr) * (k - 1) / Math.max(1, n - 1), y = v => H - pb - (H - pb - pt) * v / top;
  let g = '';
  [0, 0.5, 1].forEach(f => { const v = top * f; g += '<line class="gl" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="tx" x="' + (pl - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end">' + fmt(v) + '</text>'; });
  g += '<line class="ax" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
  [1, Math.round(n / 2), n].forEach(k => { g += '<text class="tx" x="' + x(k) + '" y="' + (H - 6) + '" text-anchor="middle">' + k + '</text>'; });
  g += '<text class="tx" x="' + (W - pr) + '" y="' + (H - 6) + '" text-anchor="end" dx="-18">trial</text>';
  return { x: x, y: y, g: g };
}
const dotClass = r => r.verdict === 'Good' ? 'pg' : r.verdict === 'No result' ? 'pn' : 'pb';
function drawGood() {
  const W = 420, H = 150, n = Math.max(30, TL.length), last = S.results.length ? S.results[S.results.length - 1].good_so_far : 0, top = Math.max(10, last);
  const a = svgAxes(W, H, 28, 10, 22, 22, top, n, v => String(Math.round(v)));
  const pts = S.results.map(r => a.x(r.trial) + ',' + a.y(r.good_so_far));
  const area = pts.length ? '<polygon class="ar" points="' + a.x(S.results[0].trial) + ',' + a.y(0) + ' ' + pts.join(' ') + ' ' + a.x(S.results[S.results.length - 1].trial) + ',' + a.y(0) + '"/>' : '';
  $('chart').innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Good recipes so far, by trial"><text class="ttl" x="4" y="12">Good recipes so far</text>' + a.g + area + (pts.length ? '<polyline class="ln" points="' + pts.join(' ') + '"/>' : '')
    + S.results.map(r => '<circle class="' + dotClass(r) + '" cx="' + a.x(r.trial) + '" cy="' + a.y(r.good_so_far) + '" r="2.8"/>').join('') + '<text class="big" x="40" y="42">' + last + '</text></svg>';
}
function drawDots(id, key, fixedTop, unit, title) {
  const W = 420, H = 150, n = Math.max(30, TL.length), rows = S.results.filter(r => r[key] !== null && r[key] !== undefined);
  const top = fixedTop || Math.max(1, Math.ceil(Math.max(0, ...rows.map(r => r[key])) * 1.15));
  const a = svgAxes(W, H, 34, 10, 22, 22, top, n, v => (v >= 10 ? String(Math.round(v)) : v.toFixed(1)));
  const lastRow = rows.length ? rows[rows.length - 1] : null;
  $(id).innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(title) + ' by trial"><text class="ttl" x="4" y="12">' + esc(title) + '</text>' + a.g
    + rows.map(r => '<circle class="' + dotClass(r) + '" cx="' + a.x(r.trial) + '" cy="' + a.y(r[key]) + '" r="3"/>').join('')
    + (lastRow ? '<text class="big" x="44" y="42">' + lastRow[key].toFixed(unit === '%' ? 1 : 2) + unit + '</text>' : '') + '</svg>';
}
function renderChecks() {
  $('checksCount').textContent = VC.log.length ? VC.log.length + (VC.log.length === 1 ? ' check' : ' checks') : 'none yet';
  $('checksList').innerHTML = VC.log.length ? VC.log.map((x, i) => '<button class="chk ' + x.cls + (i === VC.sel ? ' sel' : '') + '" data-i="' + i + '"><span class="p">T' + x.trial + '</span><span><b>' + esc(x.item) + '</b><small>' + esc(x.kind === 'tablet' ? 'defect score ' + x.d.probability + '%' : (x.d.name_read || 'name not read') + ' · ' + (x.d.label_read || 'barcode not read')) + '</small></span><span class="tag ' + x.cls + '">' + esc(x.verdict) + '</span></button>').reverse().join('')
    : '<p class="empty">No check yet: the first appears when the arm picks up an ingredient bottle.</p>';
  document.querySelectorAll('#checksList .chk').forEach(b => b.onclick = () => { VC.sel = Number(b.dataset.i); lastUi = ''; });
  const x = VC.log[VC.sel];
  if (!x) return;
  const d = x.d;
  $('lookMeta').textContent = 'Trial ' + x.trial + ' · ' + x.item;
  $('lookBody').innerHTML = '<div class="look"><img src="' + d.image + '" alt="The photograph the cell took"><dl class="kv">'
    + '<dt>Answer</dt><dd><span class="tag ' + x.cls + '">' + esc(x.verdict) + '</span></dd>'
    + (x.kind === 'tablet' ? '<dt>Defect score</dt><dd>' + d.probability + '% (defective from 50%)</dd><dt>Next</dt><dd>' + esc(d.action_taken) + '</dd>'
      : '<dt>Barcode read</dt><dd>' + esc(d.label_read || 'not readable') + '</dd><dt>Barcode expected</dt><dd>' + esc(d.label_expected || '') + '</dd><dt>Name read</dt><dd>' + esc(d.name_read || 'not readable') + '</dd><dt>Name expected</dt><dd>' + esc(d.name_expected || '') + '</dd><dt>Liquid</dt><dd>' + (d.read ? esc(d.read) + ' at ' + d.level + '%' : 'not seen') + '</dd><dt>Why</dt><dd>' + esc(d.label_detail || d.detail) + '</dd>')
    + (d.demo ? '<dt>Note</dt><dd>Demonstration scenario chosen by the presenter</dd>' : '') + '</dl></div>';
}
function renderLists() {
  const key = S.results.length + ':' + S.alerts.length + ':' + S.eventTotal + ':' + S.status + ':' + S.message + ':' + VC.log.length + ':' + VC.sel + ':' + TL.length + ':' + TAB + ':' + gateSig + ':' + S.decisions.length + ':' + queueSig;
  if (key === lastUi) return; lastUi = key;
  const resultsRows = S.results.filter(r => r.verdict !== 'No result'), skipped = S.results.length - resultsRows.length;
  const good = S.results.length ? S.results[S.results.length - 1].good_so_far : 0, notGood = resultsRows.length - good;
  const rec = S.alerts.filter(a => a.kind === 'recovery').length, faults = S.alerts.filter(a => a.kind === 'fault').length, waiting = S.alerts.filter(a => a.kind === 'alert_queued').length, skips = S.alerts.filter(a => a.kind === 'candidate_skipped').length;
  // chrome
  const gateN = S.approval ? 1 : 0; $('mgrBadge').textContent = waiting + gateN; $('mgrBadge').classList.toggle('show', waiting + gateN > 0);
  $('cxStudy').textContent = S.setupLabel || 'Loading...';
  const st = $('cxState'); st.className = 'pill ' + S.status; st.textContent = S.approval ? 'Waiting for a decision' : (S.message || ({ ready: 'Ready: press play', running: 'Running', paused: 'Paused', finished: 'Finished', stopped: 'Stopped', failed: 'Stopped' }[S.status] || S.status));
  $('cxProgress').textContent = TL.length + (TL.length === 1 ? ' trial' : ' trials') + ' started · ' + resultsRows.length + ' with a result · ' + good + ' good';
  const pb = $('playBtn'); pb.innerHTML = S.status === 'running' ? '&#10074;&#10074;' : '&#9654;'; pb.setAttribute('aria-label', S.status === 'running' ? 'Pause the run' : S.status === 'finished' ? 'The run has finished' : 'Start the run'); pb.disabled = S.status === 'finished' || S.status === 'blocked' || S.status === 'failed' || !!S.approval;
  document.querySelectorAll('#speedGroup button').forEach(b => b.classList.toggle('on', Number(b.dataset.speed) === S.speed)); $('speedSel').value = String(S.speed);
  $('saved').textContent = S.saved ? 'The finished run has been saved.' : '';
  // overview
  $('kStarted').textContent = TL.length; $('kDone').textContent = resultsRows.length; $('kGood').textContent = good; $('kFaults').textContent = rec; $('kFaultsS').textContent = 'recovered of ' + faults + ' fault' + (faults === 1 ? '' : 's'); $('kAlerts').textContent = waiting;
  $('kRight').textContent = VC.right; $('kWrong').textContent = VC.wrong; $('kCheck').textContent = VC.check;
  $('kMini').innerHTML = '<i class="a" style="flex-grow:' + VC.right + '"></i><i class="b" style="flex-grow:' + VC.wrong + '"></i><i class="c" style="flex-grow:' + VC.check + '"></i>';
  const att = S.alerts.slice().reverse().slice(0, 6).map(a => { const i = alertInfo(a); return '<div class="rowitem ' + i[0] + '"><div><b>' + esc(i[1]) + '</b> ' + riskTag(a) + ' <small>' + (a.trial ? 'Trial ' + a.trial : '') + '</small><br><small>' + esc(a.message) + '</small></div><small>' + esc(a.when) + '</small></div>'; }).join('');
  $('attBody').innerHTML = (gateAttention() + att) || '<p class="empty">No fault so far. The cell asks a person only when it cannot carry on alone.</p>';
  $('attMeta').textContent = S.alerts.length ? S.alerts.length + ' so far' : 'Faults and alerts as they happen';
  $('ovBars').innerHTML = [['Good', good, 'var(--green)'], ['Not good', notGood, 'var(--amber)'], ['Skipped', skipped, 'var(--red)']].map(r => '<div class="bar"><span>' + r[0] + '</span><div class="t"><i style="width:' + (TL.length ? r[1] / TL.length * 100 : 0) + '%;background:' + r[2] + '"></i></div><b>' + r[1] + '</b></div>').join('');
  // operator
  $('checksList').scrollTop = 0; renderChecks(); renderReason();
  // manager
  $('aNeeds').classList.toggle('hot', waiting > 0 || gateN > 0);
  $('aNeedsBig').textContent = [S.approval ? '1 waiting for approval' : '', waiting > 0 ? waiting + ' waiting for staff' : ''].filter(Boolean).join(' \u00b7 ') || 'Nothing waiting';
  const lastWait = S.alerts.filter(a => a.kind === 'alert_queued').slice(-1)[0];
  $('aNeedsS').textContent = S.approval ? 'High risk: a person must accept or reject the flagged vial (see the Operator view).' : (lastWait ? lastWait.message : 'A person is asked only when the cell cannot carry on alone.');
  $('aHand').textContent = S.status === 'finished' ? 'Run complete' : S.status === 'running' ? 'In progress' : 'Not yet';
  $('aHandS').textContent = S.summary ? S.summary.headline + '. ' + S.summary.attempts_text + '.' : 'The cell hands over to the morning team at the end of the run.';
  $('aRec').textContent = rec; $('aSkip').textContent = skips; $('aWait').textContent = waiting;
  $('results').innerHTML = S.results.length ? '<table><thead><tr><th>Trial</th><th>When</th><th class="num">Dissolution %</th><th class="num">Hardness kP</th><th>Result</th></tr></thead><tbody>' + S.results.slice().reverse().map(r => '<tr class="' + (r.verdict === 'Good' ? 'g' : r.verdict === 'No result' ? 'n' : 'b') + '"><td>' + r.trial + '</td><td>' + esc(r.when) + '</td><td class="num">' + (r.dissolution_pct === null ? '' : r.dissolution_pct.toFixed(1)) + '</td><td class="num">' + (r.hardness_kp === null ? '' : r.hardness_kp.toFixed(2)) + '</td><td><span class="tag ' + (r.verdict === 'Good' ? 'ok' : r.verdict === 'No result' ? 'bad' : 'warn') + '">' + esc(r.verdict) + '</span></td></tr>').join('') + '</tbody></table>' : '<p class="empty" style="padding:14px">No result yet: a result appears here when its test has finished.</p>';
  drawGood(); drawDots('chartD', 'dissolution_pct', 100, '%', 'Dissolution at 30 min (%)'); drawDots('chartH', 'hardness_kp', 0, ' kP', 'Hardness (kP)');
  $('alerts').innerHTML = S.alerts.length ? S.alerts.slice().reverse().map(a => { const i = alertInfo(a); return '<li><span class="tag ' + i[0] + '">' + esc(i[1]) + '</span> ' + riskTag(a) + ' <b>' + esc(a.when) + '</b> ' + esc(a.message) + '</li>'; }).join('') : '<li class="empty">No fault so far.</li>';
  $('events').innerHTML = S.events.slice(-16).reverse().map(e => '<li><b>' + esc(e.when) + '</b> ' + esc(e.message) + '</li>').join('') || '<li class="empty">Nothing has happened yet.</li>';
  renderDecisions(); renderJobs();
}
// ---------------------------------------------------------------- how the engine chose its latest recipe
// The engine wrote its numbers into the reason sentence of its decision event. This reads them back out of that sentence and lays them out; it calculates nothing and decides nothing
// (the one comparison is which of two published chances to name as the weaker). A chance is never printed as a flat 100% or 0%: an estimate is never certain.
const DECISION_RE = /^Trial (\d+): ([\s\S]*?)\. Recipe: ([\s\S]*?)\.( \([\s\S]*\))?$/;
const LEARNED_RE = /^Chosen from (\d+) measured results\. Estimated chance of passing both specifications(, allowing for test-to-test scatter)?: ([<>]?\d+)% \(dissolution of (.+?): ([<>]?\d+)%; hardness (.+?): ([<>]?\d+)%\)\. Expected dissolution (\d+)% \(give or take (\d+)\) and hardness ([\d.]+) kP \(give or take ([\d.]+)\)\. This recipe sits (?:close to trial (\d+)'s recipe, refining what worked there|in a part of the space not yet tested \(nearest earlier recipe: trial (\d+)\))\. Best result so far: trial (\d+)\.(?: (\d+) skipped trial\(s\) with no result are ignored\.)?$/;
const pctNum = s => parseFloat(String(s).replace(/[<>]/, ''));
const pctText = s => (s === '100' ? '>99%' : s === '0' ? '<1%' : s + '%');
function resultLine(n) {
  const r = S.results.find(x => x.trial === Number(n));
  return r && r.dissolution_pct !== null ? 'trial ' + n + ' measured dissolution ' + r.dissolution_pct.toFixed(1) + '% and hardness ' + r.hardness_kp.toFixed(2) + ' kP (' + esc(r.verdict.toLowerCase()) + ')' : 'trial ' + n;
}
function renderReason() {
  let ev = null; for (let i = S.events.length - 1; i >= 0; i--) { if (S.events[i].kind === 'decision') { ev = S.events[i]; break; } }
  const m = ev && DECISION_RE.exec(ev.message), meta = $('reasonMeta'), body = $('reasonBody');
  if (!m) { meta.textContent = 'Waiting for the first decision'; body.innerHTML = '<p class="empty">When the engine chooses a recipe, the reasoning behind the choice appears here.</p>'; return; }
  const reason = m[2], recipe = '<p><b>Recipe chosen</b><br>' + esc(m[3]) + '</p>', L = LEARNED_RE.exec(reason);
  meta.textContent = 'Recipe for trial ' + m[1] + ' \u00b7 decided ' + ev.when;
  if (!L) {
    const badge = /^Spread-out/.test(reason) ? 'STARTING SET' : /^Only \d+ usable/.test(reason) ? 'EXPLORING' : 'REASON';
    body.innerHTML = '<div class="rs-top"><span class="rs-mode">' + badge + '</span><span>' + esc(reason) + '.</span></div><div class="rs-cols"><div>' + recipe + '</div><div></div></div>';
    return;
  }
  const refining = L[12] !== undefined, near = L[12] || L[13], best = L[14], chance = pctText(L[3]), pd = pctText(L[5]), ph = pctText(L[7]);
  const weakest = (pd === '>99%' && ph === '>99%') ? 'Both specifications look safe: dissolution ' + pd + ', hardness ' + ph + '.'
    : pctNum(L[5]) <= pctNum(L[7]) ? 'Weakest point: dissolution ' + esc(L[4]) + ' (' + pd + ').' : 'Weakest point: hardness ' + esc(L[6]) + ' (' + ph + ').';
  const reacting = near === best ? '<li>The closest earlier recipe, and the best result so far: ' + resultLine(near) + '.</li>'
    : '<li>Closest earlier recipe: ' + resultLine(near) + '.</li><li>Best result so far: ' + resultLine(best) + '.</li>';
  const scatter = L[2] ? 'The chance allows for the scatter seen between repeat tests and can still be wrong.'
    : 'In this recording the chance leaves out the scatter seen between repeat tests, so it can read higher than the real chance that a test passes.';
  body.innerHTML =
    '<div class="rs-top"><span class="rs-mode ' + (refining ? 'refining' : 'exploring') + '">' + (refining ? 'REFINING' : 'EXPLORING') + '</span><span>' +
    (refining ? 'The best-looking recipe sits close to trial ' + near + "'s, so the engine is refining what has already worked."
              : 'The best-looking recipe is in a part of the space not yet tested (nearest earlier recipe: trial ' + near + '), so the engine is exploring.') + '</span></div>' +
    '<div class="rs-cols"><div class="rs-tile"><div class="k">Chance a test of this recipe passes both specifications</div><div class="v">' + chance + '</div><div class="t"><i style="width:' + pctNum(L[3]) + '%"></i></div>' +
    '<div class="s">From ' + L[1] + ' measured results</div><div class="w">' + weakest + '</div></div>' +
    '<div><h5>What it expects</h5><p>Dissolution <b>' + L[8] + '% (give or take ' + L[9] + ')</b><br>Hardness <b>' + L[10] + ' kP (give or take ' + L[11] + ')</b></p>' + recipe + '</div></div>' +
    '<div class="rs-cols" style="grid-template-columns:minmax(0,1fr)"><div><h5>What it is reacting to</h5><ul>' + reacting + '</ul></div></div>' +
    '<p class="rs-note">' + scatter + (L[15] ? ' ' + L[15] + ' skipped trial(s) with no result were left out.' : '') + ' Illustrative: these are the simulation\'s estimates, not predictions about real tablets.</p>' +
    '<details class="rs-more"><summary>The engine\'s own wording</summary><p>' + esc(reason) + '.</p></details>';
}
// ---------------------------------------------------------------- high-risk findings wait for a person
// A finding that could change what goes into the tablet (a vial that is not the one the plan expects) makes the cell stop: the simulation's clock stands still and this card asks a person to accept or reject it.
// The simulation goes on only when the answer reaches it. Faults the cell can clear by itself are tagged low risk and carry on as before. Every decision is logged in the Lab manager view.
const LOWTAG = '<span class="tag" title="Handled automatically: no decision needed">LOW RISK</span>';
const riskTag = a => (a.risk === 'high' ? '<span class="tag bad">HIGH RISK</span>' : (['fault', 'recovery', 'candidate_skipped', 'alert_queued'].includes(a.kind) ? LOWTAG : ''));
function renderGate() {
  const g = S.approval, el = $('gate');
  if (g) {
    el.innerHTML = '<div class="gate-card" tabindex="-1"><div class="gate-head"><span class="risk">HIGH RISK</span><b>Needs your decision: ' + esc(g.title.toLowerCase()) + '</b><small>Trial ' + g.trial + ' &middot; ' + esc(g.when) + ' &middot; run paused</small></div>' +
      '<p><b>What the cell found:</b> ' + esc(g.found) + '</p><p><b>What the cell recommends:</b> ' + esc(g.recommend) + ' The run stays paused until a person decides.</p>' +
      '<div class="gate-btns"><button class="accept" id="gateAccept">Accept: carry on with this vial</button><button class="reject" id="gateReject">Reject: skip this batch</button></div>' +
      '<p class="gate-note">Illustrative. Reject skips this batch and the cell moves on to the next one by itself. Accept lets the batch go on and logs it as an accepted deviation. Either way the decision is logged in the Lab manager view.</p></div>';
    $('gateAccept').onclick = () => post('decide', 'accept'); $('gateReject').onclick = () => post('decide', 'reject');
  } else el.innerHTML = '';
  ['playBtn', 'resetBtn', 'restartBtn', 'speedSel', 'setupSel'].forEach(id => { const b = $(id); if (b) b.disabled = !!g; });
  document.querySelectorAll('#speedGroup button').forEach(b => { b.disabled = !!g; });
}
function gateChanged() {
  const sig = S.approval ? S.approval.trial + ':' + S.approval.decision : '';
  if (sig === gateSig) return;
  const opened = !!S.approval && !gateSig;
  gateSig = sig; lastUi = ''; renderGate();
  if (opened) { setTab('operator'); window.scrollTo({ top: 0, behavior: 'instant' }); toast('High risk: the run is paused and needs a person to decide.'); }
}
function gateAttention() {
  const g = S.approval;
  return g ? '<div class="rowitem bad"><div><b>Waiting for approval</b> <span class="tag bad">HIGH RISK</span> <small>Trial ' + g.trial + '</small><br><small>' + esc(g.title) + ': a person must accept or reject (see the Operator view).</small></div><small>' + esc(g.when) + '</small></div>' : '';
}
function renderDecisions() {
  const rows = S.decisions.slice().reverse().map(e => '<div class="rowitem ' + (e.decision === 'Accepted' ? 'warn' : e.decision === 'Rejected' ? 'ok' : 'bad') + '"><div><b>' + esc(e.title) + '</b> <span class="tag bad">HIGH RISK</span><br><small>' + esc(e.found) + '</small><br><small>Trial ' + e.trial + ' &middot; ' + esc(e.when) + '</small></div>' +
    '<div style="text-align:right"><b>' + esc(e.decision) + '</b><br><small>' + (e.decided_at ? 'decided by a person at ' + esc(e.decided_at) + ' (this computer\'s clock)' : '') + '</small></div></div>').join('');
  $('decisions').innerHTML = rows || '<p class="empty">No high-risk finding so far. When the cell finds something that could change what is in the tablet (for example a vial that is not the one the plan expects) it stops and a person must accept or reject it. Choose Example 4 in the Study list to see it.</p>';
}
// ---------------------------------------------------------------- the job queue
// The queue lists the jobs of several drugs (one whole run each) and says where each one stands. The cell does one job at a time. A job is started by a click, or the queue runs itself, one job after another.
// A job that runs out of an ingredient stops and is marked blocked, with the reason in plain words, and the queue moves on. The order is first come, first served until the real rules are written down.
const JOB_STATUS = { 'pending': ['', 'PENDING'], 'in progress': ['look', 'IN PROGRESS'], 'completed': ['ok', 'COMPLETED'], 'blocked': ['bad', 'BLOCKED'] };
function jobButton(j, busy) {
  if (j.status === 'in progress') return '<span class="empty">Running now</span>';
  if (j.status === 'completed') return '';
  return '<button class="ghost" data-job="' + esc(j.id) + '"' + (busy ? ' disabled' : '') + '>' + (j.status === 'blocked' ? 'Start again' : 'Start') + '</button>';
}
function renderJobs() {
  const q = S.queue; if (!q) return;
  const busy = !!q.active, waiting = q.jobs.filter(j => j.status === 'pending').length, blocked = q.jobs.filter(j => j.status === 'blocked').length;
  $('jobsBadge').textContent = blocked; $('jobsBadge').classList.toggle('show', blocked > 0);
  $('jobsMeta').textContent = q.automated ? 'Running itself, one job after another' : busy ? 'One job is running' : 'Nothing is running';
  $('jobsBody').innerHTML = q.jobs.map(j => {
    const st = JOB_STATUS[j.status] || ['', j.status];
    return '<div class="jobrow"><div class="jn"><b>' + esc(j.drug) + '</b><small>' + esc(j.setup_label) + '</small></div><div class="jst"><span class="tag ' + st[0] + '">' + st[1] + '</span></div>' +
      '<div class="jpr">' + (j.status === 'pending' ? 'Waiting' : j.trials_started + ' trials started &middot; ' + j.trials_with_result + ' with a result &middot; ' + j.good + ' good') + '</div><div class="jact">' + jobButton(j, busy) + '</div>' +
      (j.reason ? '<div class="jwhy"><b>Why it stopped:</b> ' + esc(j.reason) + '</div>' : '') + '</div>';
  }).join('');
  document.querySelectorAll('#jobsBody [data-job]').forEach(b => { b.onclick = () => post('job_start', b.dataset.job); });
  $('jobsRunAll').disabled = busy || waiting === 0; $('jobsStopAuto').hidden = !q.automated;
  $('shelfBody').innerHTML = q.supplies.map(s => {
    const pct = Math.max(0, Math.min(100, s.left_g / s.full_g * 100));
    return '<div class="shelfbar"><span>' + esc(s.label) + '</span><div class="t"><i style="width:' + pct + '%;background:' + (pct < 12 ? 'var(--red)' : pct < 30 ? 'var(--amber)' : 'var(--green)') + '"></i></div><b>' + s.left_g.toFixed(1) + ' g</b></div>';
  }).join('');
}
// ---------------------------------------------------------------- try a recipe yourself
// The person types their own recipe. The server's virtual lab measures it and the engine says what it would do next. The page sends five numbers and shows what comes back: it measures and chooses nothing itself.
function tryDone() { const b = $('tryGo'); if (b) b.disabled = false; }
function renderTryForm() {
  const d = S.design; if (!d) return;
  $('tryForm').innerHTML = d.ingredients.map(i => '<label class="tryrow" for="tryIn_' + esc(i.key) + '"><span>' + esc(i.label) + '</span><input type="number" id="tryIn_' + esc(i.key) + '" step="0.1" min="' + i.min + '" max="' + i.max + '" value="' + i.start + '"><small>' + i.min + ' to ' + i.max + ' %</small></label>').join('');
  $('tryTargets').textContent = 'A recipe is good when dissolution is ' + d.targets.dissolution + ' and hardness is ' + d.targets.hardness + '. Type your own values, within the ranges, and the lab will measure them.';
}
function tryRecipe() {
  const d = S.design; if (!d) return;
  const v = {}; d.ingredients.forEach(i => { const el = $('tryIn_' + i.key); v[i.key] = el && el.value !== '' ? Number(el.value) : null; });
  $('tryGo').disabled = true; setTimeout(tryDone, 15000);
  post('try_recipe', v);
}
function renderTry() {
  const r = S.whatif, out = $('tryOut'); tryDone();
  if (!r || !S.design) { out.innerHTML = '<p class="empty">Press the button. The lab measures the recipe, and the engine says what it would try next.</p>'; return; }
  const m = r.measured, t = S.design.targets, lines = rec => S.design.ingredients.map(i => '<li>' + esc(i.label) + ': <b>' + rec[i.key] + '%</b></li>').join('');
  const met = ok => '<span class="tag ' + (ok ? 'ok' : 'warn') + '">' + (ok ? 'MET' : 'MISSED') + '</span>';
  out.innerHTML = '<div class="rs-cols"><div class="rs-tile"><div class="k">What the lab measured (trial ' + r.trial + ')</div><div class="v">' + (m.good ? 'GOOD' : 'Not good') + '</div>' +
    '<div class="w">Dissolution <b>' + m.dissolution_pct + '%</b> (needs ' + esc(t.dissolution) + ') ' + met(m.dissolution_ok) + '<br>Hardness <b>' + m.hardness_kp + ' kP</b> (needs ' + esc(t.hardness) + ') ' + met(m.hardness_ok) + '</div></div>' +
    '<div><h5>What the engine would try next (trial ' + r.next.trial + ')</h5><ul>' + lines(r.next.recipe) + '</ul><p><b>Why:</b> ' + esc(r.next.reason) + '</p></div></div>' +
    '<p class="rs-note">Illustrative. The engine has already seen the usual six starting recipes and what the lab measured for them, and then sees yours as trial ' + r.trial + '. Each try is measured afresh, so the same recipe tried twice reads a little differently, as in a real lab.</p>' +
    '<details class="rs-more"><summary>The six starting results the engine had already seen</summary><p>' + r.starting.map(x => 'Trial ' + x.trial + ': dissolution ' + x.dissolution_pct + '%, hardness ' + x.hardness_kp + ' kP, ' + (x.good ? 'good' : 'not good')).join('<br>') + '</p></details>';
}
function renderStrips(cur) {
  const key = TL.length + ':' + cur + ':' + S.results.length + ':' + TAB; if (key === lastChips) return; lastChips = key;
  const h = chipsHtml(cur); $('strip').innerHTML = h; $('ovStrip').innerHTML = h;
}
function renderScrub(t) {
  const p = S.duration ? clamp(t / S.duration, 0, 1) * 100 : 0;
  $('fill').style.width = p + '%'; $('knob').style.left = p + '%';
  $('tlabel').textContent = 'T+' + hhmm(Math.min(t, S.duration || t)) + ' / ' + (S.duration ? Math.round(S.duration / 3600) : 0) + ' h';
  const key = TL.length + ':' + S.results.length + ':' + S.duration;
  if (key !== $('track').dataset.k) {
    $('track').dataset.k = key;
    $('track').querySelectorAll('.tick').forEach(e => e.remove());
    if (S.duration) TL.forEach(tl => { const row = S.results.find(r => r.trial === tl.trial); const e = document.createElement('div'); e.className = 'tick ' + (row ? (row.verdict === 'Good' ? 'good' : row.verdict === 'No result' ? 'skip' : 'bad') : ''); e.style.left = (tl.trial_start_minute * 60 / S.duration * 100) + '%'; $('track').appendChild(e); });
  }
  $('clockT').textContent = S.when || '—';
}
function renderAction(st, tl, tIn, a) {
  const k = (tl ? tl.trial : 0) + ':' + (a ? a.id : '') + ':' + (st.readings ? st.readings.length : 0) + ':' + (a && a.outcome) + ':' + S.status + ':' + (st.resultsShown ? 1 : 0);
  const phase = a ? a.phase : '';
  if (phase !== lastPhase) { lastPhase = phase; document.querySelectorAll('#loopBody .lstep').forEach(e => e.classList.toggle('on', e.dataset.p === phase)); }
  if (k === lastAct) return; lastAct = k;
  const n = $('now');
  if (!a) {
    $('steps').innerHTML = PIPE.map(p => '<div class="stp">' + p[1] + '</div>').join('');
    n.className = 'now'; n.innerHTML = '<b>' + (S.status === 'ready' ? 'Ready' : 'Between trials') + '</b><small>' + (S.status === 'ready' ? 'Press play to start the simulated run.' : 'The next trial starts when the cell reaches it.') + '</small>'; $('reads').innerHTML = ''; $('fault').style.display = 'none'; return;
  }
  const at = PIPE.findIndex(p => p[0] === a.step);
  $('steps').innerHTML = PIPE.map((p, i) => '<div class="stp' + (i < at ? ' done' : i === at ? ' on' : '') + '">' + p[1] + '</div>').join('');
  const failed = a.outcome === 'failed', recov = a.origin === 'recovery';
  $('fault').style.display = failed ? 'block' : 'none'; $('fault').textContent = failed && a.fault ? 'FAULT: ' + a.fault.cause + '. ' + a.fault.detail : '';
  n.className = 'now' + (failed ? ' fail' : recov ? ' rec' : '');
  n.innerHTML = '<b>Trial ' + tl.trial + ' &middot; ' + esc(a.type) + (recov ? ' &middot; RECOVERY' : '') + '</b><small>' + esc(a.caption) + '</small>' + (a.reason ? '<br><small>Why: ' + esc(a.reason) + '</small>' : '') + '<br><small>' + mmss(tIn) + ' into this trial</small>';
  const rows = st.readings.map(r => '<div class="' + (r.bad ? 'no' : '') + '"><span>' + esc(QUANTITY_LABEL[r.quantity] || r.quantity) + '</span><b>' + r.text + '</b></div>').join('');
  $('reads').innerHTML = rows + (st.resultsShown ? '<div class="' + (tl.result.verdict === 'Good' ? '' : 'no') + '"><span>Result of trial ' + tl.trial + '</span><b>' + esc(tl.result.verdict) + '</b></div>' : '');
}

// ---------------------------------------------------------------- the welcome, the explanation, the limits
function openModal(html) { $('sheet').innerHTML = '<button class="x" id="mx" aria-label="Close">&times;</button>' + html; $('modal').classList.add('open'); $('mx').onclick = closeModal; }
function closeModal() { $('modal').classList.remove('open'); }
const points = (rows, no) => rows.map((r, i) => '<div class="point"><span class="n">' + (i + 1) + '</span><div><b>' + esc(r[0]) + '</b><span>' + esc(r[1]) + '</span></div></div>').join('');
function openWelcome() {
  openModal('<div class="ring"><i></i></div><h2>Welcome to the Autonomous Formulation Cell</h2><p class="sub">Experiments that run themselves, day and night.</p>'
    + '<div class="duo"><div><span class="eyebrow">The challenge</span><p>Formulating a tablet is slow and manual: about 9 experiments a week by hand (an assumption), nothing at night or at weekends, and every bottle and tablet checked by eye.</p></div>'
    + '<div class="gain"><span class="eyebrow">The solution</span><p>A robotic lab station that makes, tests and learns from tablet recipes by itself, around the clock, and checks every ingredient bottle and every tablet with its own cameras.</p></div></div>'
    + '<div class="trio">' + SOLUTION.map(r => '<div><b>' + esc(r[0]) + '</b>' + esc(r[1]) + '</div>').join('') + '</div>'
    + '<p class="lbl" style="margin:0 0 12px">This is a simulated prototype: every number you will see is illustrative.</p>'
    + '<div class="acts"><button class="btn primary" id="wGo">Watch the guided demo</button><button class="btn" id="wTour">Take the tour</button><button class="btn" id="wSkip">Explore on my own</button></div>');
  $('wGo').onclick = () => { closeModal(); demoStart(); };
  $('wTour').onclick = () => { closeModal(); tourStart(); };
  $('wSkip').onclick = closeModal;
  try { sessionStorage.setItem('welcomed', '1'); } catch (e) { /* the welcome simply opens again next time */ }
}
function openExplain() { const e = EXPLAIN[TAB]; openModal('<h2>' + esc(e[0]) + ': what you are looking at</h2><p class="sub">' + esc(e[1]) + '</p><div class="acts"><button class="btn primary" id="eOk">Got it</button><button class="btn" id="eTour">Take the tour</button></div>'); $('eOk').onclick = closeModal; $('eTour').onclick = () => { closeModal(); tourStart(); }; }
function openAbout() {
  openModal('<span class="eyebrow">About</span><h2>What this shows, and what it does not</h2><p class="sub">Please read this before drawing any conclusion from the numbers.</p><div class="pan2"><div><h3>What this shows</h3><ul>' + SHOWS.map(l => '<li>' + esc(l) + '</li>').join('') + '</ul></div><div class="no"><h3>What it does not show</h3><ul>' + NOSHOW.map(l => '<li>' + esc(l) + '</li>').join('') + '</ul></div></div>');
}

// ---------------------------------------------------------------- the guided tour: a spotlight on the real console, step by step
const TOUR = [
  { tab: 'overview', id: 'hero', title: 'What this is', text: 'A robotic lab station that makes and tests tablets by itself, and checks every ingredient bottle and every tablet with its own cameras. Everything you see is a simulation with illustrative values.' },
  { tab: 'overview', id: 'tabs', title: 'Three views for three audiences', text: 'Overview is for leadership and clients, Operator is for whoever watches the cell, and Lab manager is for alerts, results and logs. Switch any time.' },
  { tab: 'overview', id: 'playBtn', title: 'Run the simulation', text: 'Press play. Simulated time runs faster than real time, and the clock beside it shows the cell\'s own date and time. The same button pauses.' },
  { tab: 'overview', id: 'speedGroup', title: 'Choose the speed', text: 'A trial takes four simulated hours. At 600x that is under half a minute, so a whole run fits in a demo.' },
  { tab: 'overview', id: 'kpis', title: 'Live numbers', text: 'These count what the cell has done so far, as it happens: trials started, results, good recipes, faults handled, alerts for staff and the camera checks.' },
  { tab: 'overview', id: 'pAttention', title: 'What needs attention', text: 'Faults and alerts appear here at the moment they strike. The cell handles what it can; the rest waits for a person.' },
  { tab: 'operator', id: 'pCell', title: 'The cell at work', text: 'The arm, the instruments and the bottles, drawn by a physics model. The five steps underneath show where the current trial is, and the box shows what the arm is doing.' },
  { tab: 'operator', id: 'pCam', title: 'The camera\'s verdict', text: 'When the arm lifts a bottle, the camera scans its barcode, reads its name and looks at the liquid. Green is right, red is wrong, amber means check. Pressed tablets are inspected the same way.' },
  { tab: 'operator', id: 'injectBtn', title: 'Inject an event', text: 'Arm a wrong bottle, an unreadable barcode or a defective tablet for the next pick, and watch the frames flash red. It changes only what the camera is shown, never the run.' },
  { tab: 'operator', id: 'pChecks', title: 'Every check is kept', text: 'Each camera check is logged. Choose one to see the photograph, the readings and what the cell does next.' },
  { tab: 'manager', id: 'alerts3', title: 'For the lab manager', text: 'What needs a person, what the cell recovered from by itself, and the handover for the morning team.' },
  { tab: 'manager', id: 'pResults', title: 'Every result', text: 'Dissolution and hardness are published when each trial\'s test finishes. Green means the recipe met every requirement.' },
  { tab: 'manager', id: 'explainBtn', title: 'Explain and About', text: 'Explain says what the current view shows. About says plainly what is illustrative and what this does not show.' },
  { tab: 'overview', id: '', title: 'That is the tour', text: 'Watch the guided demo to see the simulation run with a narrator explaining each thing as it comes up, or press play to run it yourself.' },
];
let TI = -1;
function tourStart() { if (DEMO.on) demoEnd(true); TI = 0; $('pop').className = 'pop'; $('tour').classList.add('open'); tourShow(); }
function tourEnd() { TI = -1; $('tour').classList.remove('open', 'demo'); }
function tourShow() {
  const s = TOUR[TI]; if (!s) return tourEnd();
  setTab(s.tab);
  const el = s.id ? $(s.id) : null;
  if (el) { const r = el.getBoundingClientRect(); if (r.top < 150 || r.bottom > innerHeight - 10) window.scrollTo({ top: Math.max(0, scrollY + r.top - 150), behavior: 'instant' }); }          // only move the page when the target is not already comfortably in view (the header stays at the top)
  const last = TI === TOUR.length - 1;
  $('pop').innerHTML = '<div class="st">Tour &middot; step ' + (TI + 1) + ' of ' + TOUR.length + '</div><h3>' + esc(s.title) + '</h3><p>' + esc(s.text) + '</p><div class="btns">' + (TI > 0 ? '<button id="tBack">Back</button>' : '') + '<span class="sp"></span><button class="txt" id="tEnd">End tour</button><button class="pri" id="tNext">' + (last ? 'Watch the guided demo' : 'Next') + '</button></div>';
  $('tNext').onclick = () => { if (last) { tourEnd(); demoStart(); } else { TI += 1; tourShow(); } };
  if ($('tBack')) $('tBack').onclick = () => { TI -= 1; tourShow(); };
  $('tEnd').onclick = tourEnd;
  setTimeout(tourPlace, 60);
}
function tourPlace() {
  const s = TOUR[TI]; if (!s) return;
  const pop = $('pop'), hole = $('hole'), el = s.id ? $(s.id) : null, W = innerWidth, H = innerHeight, pw = pop.offsetWidth, ph = pop.offsetHeight;
  if (!el) { hole.style.display = 'none'; pop.style.left = (W - pw) / 2 + 'px'; pop.style.top = (H - ph) / 2 + 'px'; return; }
  const r = el.getBoundingClientRect(), pad = 6;
  hole.style.display = 'block'; hole.style.left = (r.left - pad) + 'px'; hole.style.top = (r.top - pad) + 'px'; hole.style.width = (r.width + pad * 2) + 'px'; hole.style.height = (r.height + pad * 2) + 'px';
  let x = r.left + r.width / 2 - pw / 2, y = r.bottom + 16;
  if (y + ph > H - 12) y = r.top - ph - 16;
  if (y < 12) { y = H - ph - 20; x = W - pw - 20; }
  pop.style.left = clamp(x, 12, W - pw - 12) + 'px'; pop.style.top = clamp(y, 12, H - ph - 12) + 'px';
}

// ---------------------------------------------------------------- the guided demo: the simulation runs, and a narrator explains each thing as it comes up
// Each step says what is about to happen while the simulation runs, and when the thing it is waiting for has happened (a camera check, a fault, a recovery) the simulation is paused and the narrator explains exactly what is on the screen.
// Nothing here changes the simulation except what the page's own buttons do (restart, speed, start, pause) and the camera scenario it arms, as Inject event does.
const DEMO = { on: false, i: -1, phase: 'done', t0: 0, t1: 0, auto: true, shown: '', seen: '' };
// The narrator's voice: the computer's own speech (built into Windows and the browser), so it works offline and sends the words nowhere.
// Only voices that live on this computer are used (an 'online' voice would send the sentences to another company). Mute is remembered in this browser.
const VOICE_KEY = 'console-voice';
DEMO.voice = (() => { try { return localStorage.getItem(VOICE_KEY) !== 'off'; } catch (e) { return true; } })();
DEMO.speaking = false; DEMO.deadline = 0; DEMO.utt = null; DEMO.spoken = ''; DEMO.pending = false;
const canSpeak = () => 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
if (canSpeak()) { speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices(); }
function pickVoice() {
  if (!canSpeak()) return null;
  const rank = v => (/natural/i.test(v.name) ? 0 : /mark|aria|jenny|guy|libby|ryan|sonia/i.test(v.name) ? 1 : /zira/i.test(v.name) ? 2 : /david/i.test(v.name) ? 3 : 4) + (/^en[-_](US|GB)/i.test(v.lang) ? 0 : 0.5);
  const local = speechSynthesis.getVoices().filter(v => v.localService && /^en/i.test(v.lang));
  return local.reduce((best, v) => (!best || rank(v) < rank(best) ? v : best), null);
}
// Recordings made with an offline neural voice (tools/make_voice.py) are used when the page carries them, looked up by a fingerprint of the sentence
// (FNV-1a, the same as narration.py's hash_text); a sentence with no recording, or a page with none, uses the computer's own voice instead.
function hashText(text) { let h = 2166136261; for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return ('00000000' + h.toString(16)).slice(-8); }
const recorded = () => window.NARRATION_AUDIO || {};
const voiceReady = () => Object.keys(recorded()).length > 0 || !!(canSpeak() && pickVoice());
function playClip(b64, text) {
  const a = new Audio('data:audio/mpeg;base64,' + b64); DEMO.audio = a;
  if (window.REPLAY_SAY) window.REPLAY_SAY(hashText(text));                                                       // (a recorded replay can announce which sentence has begun: used to make the demo video)
  const finished = () => { if (DEMO.audio === a) { DEMO.speaking = false; DEMO.t1 = performance.now() / 1000; } };
  a.onended = finished; a.onerror = finished;
  DEMO.speaking = true; DEMO.deadline = performance.now() / 1000 + 8 + text.split(' ').length * 0.6;        // a safety limit, as for the computer's own voice
  const started = a.play(); if (started && started.catch) started.catch(finished);                       // a browser that blocks sound until the page is clicked: carry on silently
}
const isSpeaking = () => DEMO.speaking && performance.now() / 1000 < DEMO.deadline;
function sayStop() { DEMO.speaking = false; DEMO.utt = null; if (DEMO.audio) { DEMO.audio.onended = null; DEMO.audio.pause(); DEMO.audio = null; } if (canSpeak()) speechSynthesis.cancel(); }
function say(text) {
  sayStop();
  if (!DEMO.voice) return;
  const clip = recorded()[hashText(text)]; if (clip) { playClip(clip, text); return; }
  const v = pickVoice(); if (!v) return;
  const u = new SpeechSynthesisUtterance(text); u.voice = v; u.lang = v.lang; u.rate = 0.95; u.pitch = 1;
  const finished = () => { if (DEMO.utt === u) { DEMO.speaking = false; DEMO.t1 = performance.now() / 1000; } };
  u.onend = finished; u.onerror = finished;
  DEMO.utt = u; DEMO.speaking = true; DEMO.deadline = performance.now() / 1000 + 4 + text.split(' ').length * 0.55;          // a safety limit: if the browser never says it has finished, the demo carries on
  speechSynthesis.speak(u);
}
const hasTablet = () => VC.log.some(x => x.kind === 'tablet');
const hasAlert = kind => S.alerts.some(a => a.kind === kind);
const runAt = speed => post('speed', speed).then(() => post('start'));
const DSTEPS = [
  { title: 'Let us run the cell', tab: 'operator', target: 'pCell', dwell: 8, text: 'This is a simulated lab station. We will start it from the beginning and watch it work: the arm, the camera that checks every bottle, and what happens when something goes wrong. Everything shown is illustrative.',
    setup() { setArm(''); post('restart').then(resetLocal); } },
  { title: 'Trial 1 starts', tab: 'operator', target: 'pCell', stopWhen: () => VC.log.length >= 1, maxWait: 30, dwell: 12, setup() { runAt(120); },
    text: 'The first trial begins. Each trial makes one tablet recipe: dispense, mix, press, test, clean. The arm walks to the rack and lifts the first ingredient bottle in front of the camera.',
    doneTitle: 'The camera checks the bottle', doneTarget: 'pCam', done: 'The arm lifted the drug bottle. The camera scanned its barcode, read the printed name and looked at the liquid: all three agree, so the answer is RIGHT BOTTLE and the frame flashes green. The same thing happens for every bottle, every trial.' },
  { title: 'Now let us make it go wrong', tab: 'operator', target: 'pCell', stopWhen: () => VC.log.length >= 2, maxWait: 30, dwell: 13, setup() { setArm('wrong'); runAt(120); },
    text: 'We have swapped the stickers on the next bottle for another ingredient\'s, the way a mix-up in the rack would. Watch what the camera says.',
    doneTitle: 'Wrong bottle caught', doneTarget: 'pCam', done: 'The barcode and the name both belong to another ingredient, and the plan wanted a different one. The frame flashes red. Colour alone could never catch this: two different ingredients can look exactly the same.' },
  { title: 'A defective tablet', tab: 'operator', target: 'pCell', stopWhen: hasTablet, maxWait: 40, dwell: 13, setup() { setArm('defective'); runAt(600); },
    text: 'Back to normal bottles. The cell mixes the powders and presses a tablet, and the camera inspects it. We have armed a defective tablet for this inspection.',
    doneTitle: 'The tablet is inspected', doneTarget: 'pCam', done: 'A trained model looked at the pressed tablet. It found a chip, outlined it in red, and says this tablet would go to the discard bin instead of on to the hardness gauge.' },
  { title: 'Now the cell runs on its own', tab: 'overview', target: 'kpis', stopWhen: () => hasAlert('fault'), maxWait: 70, dwell: 12, setup() { setArm(''); runAt(3600); },
    text: 'From here nobody touches anything. Trials start, tests finish and results appear on their own. We carry on until something goes wrong.',
    doneTitle: 'A bottle jams', doneTarget: 'pAttention', done: 'A bottle jammed at the dispenser. The cell does not stop and nobody is called: it purges the line and retries by itself. Faults and alerts are listed here at the moment they happen.' },
  { title: 'Will it recover?', tab: 'overview', target: 'pAttention', stopWhen: () => hasAlert('recovery'), maxWait: 25, dwell: 10, setup() { runAt(1800); },
    text: 'Watch what the cell does about it.',
    doneTitle: 'Recovered', doneTarget: 'pAttention', done: 'The retry worked. The faults-handled number went up and the trial carried on. The cell recovered without a person.' },
  { title: 'The rest of the run', tab: 'manager', target: 'pCharts', stopWhen: () => hasAlert('alert_queued'), maxWait: 70, dwell: 14, setup() { runAt(7200); },
    text: 'The remaining trials now run at high speed. In the lab manager view the results, the charts and the alerts build up as each test finishes.',
    doneTitle: 'A jam the cell could not fix', doneTarget: 'aNeeds', done: 'This time the retry failed, so the cell skipped that recipe and queued an alert for the morning team. It is shown in red because a person is needed. Everything else carried on.' },
  { title: 'Finishing the run', tab: 'manager', target: 'pCharts', final: true, stopWhen: () => S.status === 'finished', maxWait: 70, dwell: 14, setup() { runAt(7200); },
    text: 'The last trials run on their own.',
    doneTitle: 'Run complete', doneTab: 'overview', doneTarget: 'kpis', done: () => 'The run is finished. ' + (S.summary ? S.summary.headline + '. ' + S.summary.attempts_text + '.' : 'The cell has run all its trials.') + ' Everything here is illustrative: a simulation with made-up values.' },
  { title: 'That was the demo', tab: 'overview', target: '', dwell: 0, text: 'You have seen the cell work, the camera catch a wrong bottle and a defective tablet, a fault recovered and a jam handed to the morning team. Run it again, or explore any view yourself.' },
];
function demoHole(id) {
  const hole = $('hole'), el = id ? $(id) : null;
  if (!el) { hole.style.display = 'none'; return; }
  const r = el.getBoundingClientRect(), pad = 5;
  hole.style.display = 'block'; hole.style.left = (r.left - pad) + 'px'; hole.style.top = (r.top - pad) + 'px'; hole.style.width = (r.width + pad * 2) + 'px'; hole.style.height = (r.height + pad * 2) + 'px';
}
function demoTarget() { const s = DSTEPS[DEMO.i]; return s ? (DEMO.phase === 'run' ? s.target : (s.doneTarget || s.target)) : ''; }
function demoCard() {
  const s = DSTEPS[DEMO.i], run = DEMO.phase === 'run', last = DEMO.i === DSTEPS.length - 1;
  const title = run ? s.title : (s.doneTitle || s.title), text = run ? s.text : (typeof s.done === 'function' ? s.done() : (s.done || s.text));
  const key = DEMO.i + ':' + DEMO.phase + ':' + DEMO.auto + ':' + DEMO.voice; if (key === DEMO.shown) return; DEMO.shown = key;
  const spoken = DEMO.i + ':' + DEMO.phase; if (spoken !== DEMO.spoken) { DEMO.spoken = spoken; say(title + '. ' + text); }
  const pop = $('pop'); pop.className = 'pop dm'; pop.removeAttribute('style');
  pop.innerHTML = '<div class="st">Guided demo &middot; step ' + (DEMO.i + 1) + ' of ' + DSTEPS.length + ' <span class="live ' + (run ? 'run' : '') + '">' + (run ? 'simulation running' : 'paused for the explanation') + '</span></div><h3>' + esc(title) + '</h3><p>' + esc(text) + '</p>'
    + '<div class="dbar"><i id="dFill"></i></div><div class="btns">' + (last ? '' : '<button id="dAuto">' + (DEMO.auto ? 'Pause narration' : 'Resume narration') + '</button>') + (voiceReady() ? '<button id="dVoice">' + (DEMO.voice ? 'Mute voice' : 'Voice on') + '</button>' : '<button id="dVoice" disabled title="This computer has no speech voice the console can use">No voice here</button>') + '<span class="sp"></span><button class="txt" id="dEnd">' + (last ? 'Explore on my own' : 'End demo') + '</button>'
    + (last ? '<button class="pri" id="dAgain">Run it again</button>' : '<button class="pri" id="dNext"' + (run ? ' disabled' : '') + '>' + (run ? 'Running...' : 'Next') + '</button>') + '</div>';
  if ($('dAuto')) $('dAuto').onclick = () => { DEMO.auto = !DEMO.auto; DEMO.t1 = performance.now() / 1000; demoCard(); };
  if ($('dNext')) $('dNext').onclick = demoNext;
  if ($('dVoice') && !$('dVoice').disabled) $('dVoice').onclick = () => { DEMO.voice = !DEMO.voice; try { localStorage.setItem(VOICE_KEY, DEMO.voice ? 'on' : 'off'); } catch (e) { /* not remembered */ } DEMO.spoken = ''; DEMO.shown = ''; if (!DEMO.voice) sayStop(); demoCard(); };
  if ($('dAgain')) $('dAgain').onclick = () => { DEMO.on = false; demoStart(); };
  $('dEnd').onclick = () => demoEnd(true);
}
function demoStart() {
  closeModal(); closeMenus(); tourEnd();
  DEMO.on = true; DEMO.i = -1; DEMO.auto = true; DEMO.shown = ''; DEMO.seen = '';
  $('tour').classList.add('open', 'demo'); demoNext();
}
function demoEnd(pauseRun) {
  DEMO.on = false; DEMO.shown = ''; DEMO.pending = false; sayStop(); $('tour').classList.remove('open', 'demo'); $('pop').className = 'pop'; $('pop').removeAttribute('style');
  if (pauseRun && S.status === 'running') post('pause');
}
function demoNext() {
  DEMO.i += 1; DEMO.shown = ''; DEMO.pending = false;
  const s = DSTEPS[DEMO.i]; if (!s) return demoEnd(true);
  const now = performance.now() / 1000;
  DEMO.phase = s.stopWhen ? 'run' : 'done'; DEMO.t0 = now; DEMO.t1 = now;
  if (s.tab) setTab(s.tab);
  if (s.setup) s.setup();
  demoCard();
}
function demoStop(s) {
  if (!DEMO.pending) { post('pause'); DEMO.pending = true; }                        // freeze the picture at the moment at once
  if (isSpeaking()) return;                                                         // let the narrator finish the sentence before explaining it
  DEMO.pending = false; DEMO.phase = 'done'; DEMO.t1 = performance.now() / 1000; DEMO.shown = '';
  if (s.doneTab) setTab(s.doneTab);
  demoCard();
}
function demoTick() {
  if (!DEMO.on) return;
  const s = DSTEPS[DEMO.i]; if (!s) return;
  const now = performance.now() / 1000;
  if (DEMO.phase === 'run') {
    if (DEMO.pending || s.stopWhen()) demoStop(s);
    else if (now - DEMO.t0 > s.maxWait) { if (s.final) demoStop(s); else demoNext(); }          // the thing it waited for did not happen (for example a camera check that is not set up here): move on
  } else if (DEMO.auto && s.dwell > 0) {
    if (isSpeaking()) DEMO.t1 = now;                                                // the clock for moving on starts when the voice has finished
    const hold = DEMO.voice && voiceReady() ? 2.5 : s.dwell;
    const p = (now - DEMO.t1) / hold; if ($('dFill')) $('dFill').style.width = Math.min(100, p * 100) + '%';
    if (p >= 1) { if (DEMO.i < DSTEPS.length - 1) demoNext(); }
  }
  const t = demoTarget();
  if (t !== DEMO.seen) {                                                    // a new thing to look at: bring it into view above the narrator's caption
    DEMO.seen = t; const el = t ? $(t) : null;
    if (el) { const r = el.getBoundingClientRect(); if (r.top < 150 || r.bottom > innerHeight - 250) window.scrollTo({ top: Math.max(0, scrollY + r.top - 150), behavior: 'instant' }); }
  }
  demoHole(t);
}

// ---------------------------------------------------------------- the loop of the page
function frame(now) {
  const t = simNow();
  let cur = -1; TL.forEach((tl, i) => { if (tl.trial_start_minute * 60 <= t + 1e-6) cur = i; });
  let st, a = null, tIn = 0, tl = null;
  if (cur >= 0) { tl = TL[cur]; tIn = clamp(t - tl.trial_start_minute * 60, 0, total(tl)); st = simulate(tl, tIn); a = st.current || tl.actions[tl.actions.length - 1]; }
  else if (TL.length) { st = simulate(TL[0], 0); }
  else { st = initialState(); }
  renderScrub(t); renderAction(st, tl, tIn, a); visionTick(a, tl); renderStrips(cur); renderLists(); demoTick();
  if (!MJ.on && TAB === 'operator') draw(st);
  mujocoTick(now, tl || TL[0], tIn);
  requestAnimationFrame(frame);
}
function boot() {
  if (GL) build();
  if (MJ.on && renderer) renderer.domElement.style.display = 'none';          // the stage is MuJoCo's picture; the page's own 3D scene comes back only if pictures cannot be made, or with ?mujoco=0
  if (!GL || !renderer) { $('nogl').style.display = 'flex'; }
  if (typeof setCam === 'function') setCam('overview');
  $('challengeBody').innerHTML = points(CHALLENGE); $('solutionBody').innerHTML = points(SOLUTION);
  $('loopBody').innerHTML = PHASES.map((p, i) => '<div class="lstep" data-p="' + p[0] + '"><div class="c">' + (i + 1) + '</div><b>' + p[1] + '</b><span>' + p[2] + '</span></div>').join('');
  $('steps').innerHTML = PIPE.map(p => '<div class="stp">' + p[1] + '</div>').join('');
  visionReset(); heroPicture();
  document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => setTab(b.dataset.tab));
  $('playBtn').onclick = () => post(S.status === 'running' ? 'pause' : 'start');
  $('jobsRunAll').onclick = () => post('job_run_all'); $('jobsStopAuto').onclick = () => post('job_stop_auto');
  $('jobsRestock').onclick = () => post('job_restock'); $('jobsReset').onclick = () => post('job_reset');
  $('tryGo').onclick = tryRecipe; renderTry();
  $('resetBtn').onclick = $('restartBtn').onclick = () => { closeMenus(); post('restart').then(resetLocal); };
  document.querySelectorAll('#speedGroup button').forEach(b => b.onclick = () => post('speed', Number(b.dataset.speed)));
  $('speedSel').onchange = () => post('speed', parseFloat($('speedSel').value));
  $('setupSel').onchange = () => {
    const want = $('setupSel').value, midRun = TL.length > 0 && (S.status === 'running' || S.status === 'paused');
    if (midRun && !confirm('Switching to another study restarts the run from the beginning. Continue?')) { $('setupSel').value = S.setupId; return; }
    toast('Preparing the chosen study...');
    post('setup', want).then(d => { if (d && !d.error) resetLocal(); $('setupSel').value = S.setupId; });
  };
  $('demoBtn').onclick = e => { e.stopPropagation(); toggleMenu('demoMenu'); };
  $('injectBtn').onclick = e => { e.stopPropagation(); toggleMenu('injectMenu'); };
  document.querySelectorAll('.menu .item').forEach(b => b.onclick = () => { closeMenus(); setArm(b.dataset.arm); toast('Armed: ' + ARMTEXT[b.dataset.arm] + ' at the next ' + (b.dataset.arm === 'defective' ? 'tablet inspection' : 'bottle pick')); });
  $('disarm').onclick = () => setArm('');
  $('welcomeBtn').onclick = () => { closeMenus(); openWelcome(); };
  document.addEventListener('click', e => { if (!e.target.closest('.menu') && !e.target.closest('.menuwrap')) closeMenus(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeMenus(); closeModal(); tourEnd(); if (DEMO.on) demoEnd(true); } });
  window.addEventListener('resize', () => { if (TI >= 0) tourPlace(); });
  $('themeBtn').onclick = () => setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark', true);
  setTheme(document.documentElement.getAttribute('data-theme'), false);
  $('explainBtn').onclick = openExplain; $('aboutBtn').onclick = openAbout; $('tourBtn').onclick = tourStart; $('heroTour').onclick = tourStart;
  $('heroStart').onclick = demoStart; $('guidedBtn').onclick = demoStart;
  $('modal').onclick = e => { if (e.target === $('modal')) closeModal(); };
  if (Q.get('tab') && ['overview', 'operator', 'manager', 'jobs', 'try'].includes(Q.get('tab'))) setTab(Q.get('tab'));
  if (['wrong', 'unreadable', 'blank', 'liquid', 'defective'].includes(Q.get('demo'))) setArm(Q.get('demo'));          // a link can open the console with a scenario already armed for the first pick
  let seen = false; try { seen = !!sessionStorage.getItem('welcomed'); } catch (e) { /* no storage: the welcome opens each time */ }
  if (Q.get('welcome') !== 'off' && !seen) openWelcome();
  if (Q.get('guided') === '1') {
    demoStart();
    const g = Q.get('gstep');                                              // ?gstep=N shows step N as it looks once it has paused (for looking at a step without waiting for it)
    if (g !== null) { DEMO.i = Math.max(0, Math.min(DSTEPS.length - 1, Number(g))); const s = DSTEPS[DEMO.i]; DEMO.phase = 'done'; DEMO.auto = false; DEMO.shown = ''; if (s.doneTab || s.tab) setTab(s.doneTab || s.tab); demoCard(); }
  }
  if (Q.get('tour') === '1') { TI = Math.max(0, Number(Q.get('step') || 0)); $('tour').classList.add('open'); tourShow(); }
  poll();
  if (Q.get('autostart') === '1' && META('live-autostart') === '1') setTimeout(() => { if (S.status === 'ready') $('playBtn').click(); }, 600);     // only on a server started for tests: the same click handler the play button has
  requestAnimationFrame(frame);
}
window.__live = { S, TL, simNow, simulate };
boot();
