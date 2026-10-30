// The recorded replay: the console page with no server behind it. This file is placed after window.REPLAY_DATA (the recorded run) and before the console's own script.
// It answers the page's four kinds of request (state, control, the two camera checks) from what was recorded, keeping a play/pause/speed clock of its own,
// and supplies the pictures of the cell. It invents nothing: every number the page shows is in the recording, shown at the moment it was published.
(function () {
  const D = window.REPLAY_DATA;
  const SPEEDS = [60, 120, 300, 600, 1800, 3600, 7200];
  const R = { s: 0, speed: 300, status: 'ready', last: performance.now() };
  const at = Number(new URLSearchParams(location.search).get('at'));                       // ?at=SECONDS opens the replay paused at that simulated moment (for a presenter, and for the health check)
  if (isFinite(at) && at > 0) { R.s = Math.min(at, D.duration_s); R.status = 'paused'; }
  const times = list => list.map(x => x.published_at_sim_s);
  const T = { events: times(D.events), results: times(D.results), alerts: times(D.alerts), timelines: D.timeline_times };
  const upto = (sorted, t) => { let lo = 0, hi = sorted.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (sorted[mid] <= t) lo = mid + 1; else hi = mid; } return lo; };      // how many were published by simulated second t
  const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], two = n => (n < 10 ? '0' : '') + n;
  const START = (m => Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]))(/(\d+)-(\d+)-(\d+) (\d+):(\d+)/.exec(D.clock_start));
  const when = s => { const d = new Date(START + Math.min(s, D.duration_s) * 1000); return WD[d.getUTCDay()] + ' ' + two(d.getUTCDate()) + ' ' + MON[d.getUTCMonth()] + ' ' + two(d.getUTCHours()) + ':' + two(d.getUTCMinutes()); };
  function advance() {
    const now = performance.now();
    if (R.status === 'running') { R.s = Math.min(D.duration_s, R.s + (now - R.last) / 1000 * R.speed); if (R.s >= D.duration_s) R.status = 'finished'; }
    R.last = now;
  }
  function state(tlSeen, evSeen, brief) {
    advance();
    const t = R.s, nTl = upto(T.timelines, t), nEv = upto(T.events, t), nRes = upto(T.results, t), nAl = upto(T.alerts, t);
    const out = { run_id: 'replay', label: D.label, status: R.status, speed: R.speed, sim_s: t, duration_s: D.duration_s, clock_when: when(t), message: '', saved: null, good_so_far: nRes ? D.results[nRes - 1].good_so_far : 0,
      results: D.results.slice(0, nRes), alerts: D.alerts.slice(0, nAl), setup_id: D.setup_id, setups: D.setups, layout_id: D.layout_id, setup_label: D.setup_label };
    if (!brief) Object.assign(out, { timelines: D.timelines.slice(tlSeen, nTl), timeline_total: nTl, events: D.events.slice(evSeen, nEv), event_total: nEv });
    if (R.status === 'finished') out.summary = D.summary;
    return out;
  }
  function control(cmd, value) {
    advance();
    if (cmd === 'start') { if (R.status === 'ready' || R.status === 'paused') R.status = 'running'; }
    else if (cmd === 'pause') { if (R.status === 'running') R.status = 'paused'; }
    else if (cmd === 'speed') { if (SPEEDS.indexOf(Number(value)) < 0) return { error: 'That speed is not one of the choices.' }; R.speed = Number(value); }
    else if (cmd === 'restart') { R.s = 0; R.status = 'ready'; }
    else return { error: 'This is a recorded replay, so that control is not available in it.' };
    return state(0, 0, cmd !== 'restart');
  }
  const reply = (obj, status) => Promise.resolve(new Response(JSON.stringify(obj), { status: status || 200, headers: { 'Content-Type': 'application/json' } }));
  window.fetch = function (url, options) {
    const parts = String(url).split('?'), q = new URLSearchParams(parts[1] || '');
    if (parts[0] === 'state') return reply(state(Math.max(0, +q.get('tl') || 0), Math.max(0, +q.get('ev') || 0), false));
    if (parts[0] === 'control') { let body = {}; try { body = JSON.parse((options && options.body) || '{}'); } catch (e) { /* a body that is not understood does nothing */ } const out = control(body.cmd, body.value); return reply(out, out.error ? 400 : 200); }
    if (parts[0] === 'vision_check') { const found = D.vision[q.get('trial') + '|' + q.get('action') + '|' + (q.get('demo') || '')]; return found ? reply(found) : reply({ error: 'This recorded replay carries the camera checks of the first trial only.' }, 404); }
    if (parts[0] === 'tablet_check') { const found = D.vision['t|' + q.get('trial') + '|' + q.get('action') + '|' + (q.get('demo') || '')]; return found ? reply(found) : reply({ error: 'This recorded replay carries the tablet check of the first trial only.' }, 404); }
    return reply({ error: 'There is nothing at this address.' }, 404);
  };
  // the cell's picture: the one at rest, and trial 1 as recorded (the nearest recorded moment); a later trial has none, and the page then draws its own 3D scene
  const FRAMES = Object.keys(D.frames).map(Number).sort((a, b) => a - b), jpeg = b64 => 'data:image/jpeg;base64,' + b64;
  window.REPLAY_PICTURE = function (trial, t) {
    if (trial === 0) return jpeg(D.rest);
    if (trial !== 1 || t > FRAMES[FRAMES.length - 1] + 30) return 'data:,';
    let best = FRAMES[0]; for (let i = 0; i < FRAMES.length; i++) { if (Math.abs(FRAMES[i] - t) < Math.abs(best - t)) best = FRAMES[i]; else if (FRAMES[i] > t) break; }
    return jpeg(D.frames[best]);
  };
  window.REPLAY_SAY = hash => { document.title = 'say:' + hash; };                                              // the page's title names the sentence being spoken (the demo video is timed from it)
  document.addEventListener('DOMContentLoaded', () => {
    const last = document.querySelector('#ctx > div:last-child .v'); if (last) last.textContent = 'Simulation, illustrative · recorded replay';
  });
})();
