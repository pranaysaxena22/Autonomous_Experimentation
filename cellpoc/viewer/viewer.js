// The platform's 3D replay viewer (Stage 7). It replays EXECUTED TIMELINES: where the arm and every object are at a moment comes from the timeline's actions and times,
// and every number on a screen is a reading in the timeline. It contains no decision logic, no model and no result calculation, and it never touches the network.
// Part 1 (the state engine) is plain data logic with no 3D in it, so it can be tested without a browser's graphics; part 2 draws it; part 3 is the page.
(function () {
'use strict';
const $ = id => document.getElementById(id);
const DATA = { layout: JSON.parse($('data-layout').textContent), timelines: JSON.parse($('data-timelines').textContent) };
const rad = d => d * Math.PI / 180, clamp = (v, a, b) => Math.min(b, Math.max(a, v)), lerp = (a, b, f) => a + (b - a) * f, ease = f => f * f * (3 - 2 * f);
const seg = (f, lo, hi) => clamp((f - lo) / (hi - lo), 0, 1);

// ======================================================================== PART 1: the state engine
const L = DATA.layout, ROBOT = L.robot, TABLE_H = L.table.height_m, H0 = ROBOT.shoulder_height_m;
const L1 = ROBOT.links_m.upper_arm, L2 = ROBOT.links_m.forearm, L3 = ROBOT.links_m.wrist_to_tip, REACH = L1 + L2;
const HOVER = 0.22;
const LOC = {};                                                    // every place the robot can go: {a: angle in degrees, r: radius in metres, y: height in metres}
const put = (id, p, y) => { LOC[id] = { a: p.angle_deg, r: p.radius_m, y: y }; };
L.stations.forEach(s => put(s.id, s.position, s.work_height_m));
L.bottle_shelf.slots.forEach(s => put(s.id, s.position, s.work_height_m));
L.tool_holders.forEach(h => put(h.id, h.position, h.work_height_m));
LOC.home = { a: ROBOT.home.angle_deg, r: ROBOT.home.radius_m, y: ROBOT.home.height_m };
const OBJ = {}; L.objects.forEach(o => { OBJ[o.id] = o; });
const STATION = {}; L.stations.forEach(s => { STATION[s.id] = s; });
const gripOf = id => { const o = OBJ[id]; if (!o) return 0; if (o.type === 'vial') return 0.17; if (o.type === 'tablet') return 0.03; if (o.type === 'bottle') return 0; return id === 'rod' ? 0.33 : 0.175; };
const UNIT = { mass_g: 'g', hardness_kp: 'kP', friability_pct: '%', dissolution_30min_pct: '%', barcode: '' };
const QUANTITY_LABEL = { mass_g: 'MASS', hardness_kp: 'HARDNESS', friability_pct: 'FRIABILITY', dissolution_30min_pct: 'DISSOLUTION 30 MIN', barcode: 'BARCODE' };
const total = tl => { const a = tl.actions[tl.actions.length - 1]; return a.actual_start_s + a.actual_duration_s; };
const posOf = (id, up) => { const l = LOC[id]; if (!l) throw new Error('unknown place ' + id); return { a: l.a, r: l.r, y: l.y + (up || 0) }; };
const mixPose = (p0, p1, f) => ({ a: p0.a + (((p1.a - p0.a + 540) % 360) - 180) * f, r: lerp(p0.r, p1.r, f), y: lerp(p0.y, p1.y, f) });
const grip = (place, obj, up) => posOf(place, gripOf(obj) + (up || 0));
const fmt = r => (typeof r.value === 'number' ? (Math.abs(r.value) < 10 && r.quantity !== 'mass_g' && r.quantity !== 'friability_pct' ? r.value.toFixed(1) : r.quantity === 'friability_pct' ? r.value.toFixed(2) : r.value.toFixed(r.quantity === 'mass_g' ? 2 : 1)) : String(r.value)) + (UNIT[r.quantity] ? ' ' + UNIT[r.quantity] : '');

function initialState() {
  const objs = {}; L.objects.forEach(o => { objs[o.id] = { loc: o.starts_at }; });
  return { pose: Object.assign({}, LOC.home), fingers: 1, held: null, tilt: 0, objs, mound: false, off: { x: 0, y: 0, z: 0 }, flow: null, laser: false, press: 0, drum: false, ring: null, screens: {},
           readings: [], current: null, done: [], poursDone: 0, resultsShown: false };
}
function show(st, a, p) {                                           // an instrument's screen shows a reading once the action is half done
  if (!a.reading) return;
  const station = a.type === 'pour' ? a.at : a.at;
  if (p >= 0.5 && station) {
    const bad = a.outcome !== 'ok';
    st.screens[station] = { title: QUANTITY_LABEL[a.reading.quantity] || a.reading.quantity.toUpperCase(), value: fmt(a.reading), bad };
    st.readings = st.readings.filter(r => r.id !== a.id).concat([{ id: a.id, quantity: a.reading.quantity, text: fmt(a.reading), expected: a.reading.expected, bad }]);
  }
}
const HANDLERS = {
  move(st, a, p, s0) { st.pose = mixPose(s0, posOf(a.to), ease(p)); },
  pick(st, a, p, s0) {
    const g = grip(a.from, a.object), hov = grip(a.from, a.object, HOVER);
    st.pose = p < 0.45 ? mixPose(s0, hov, ease(p / 0.45)) : p < 0.75 ? mixPose(hov, g, ease(seg(p, 0.45, 0.75))) : mixPose(g, hov, ease(seg(p, 0.75, 1)));
    st.fingers = p < 0.6 ? 1 : p < 0.75 ? 1 - seg(p, 0.6, 0.75) : 0;
    st.ring = a.from;
    if (p >= 0.75) { st.held = a.object; st.objs[a.object].loc = null; }
  },
  place(st, a, p, s0) {
    const g = grip(a.to, a.object), hov = grip(a.to, a.object, HOVER);
    st.pose = p < 0.45 ? mixPose(s0, hov, ease(p / 0.45)) : p < 0.75 ? mixPose(hov, g, ease(seg(p, 0.45, 0.75))) : mixPose(g, hov, ease(seg(p, 0.75, 1)));
    st.fingers = p < 0.6 ? 0 : p < 0.75 ? seg(p, 0.6, 0.75) : 1;
    st.ring = a.to;
    if (p >= 0.75) { st.held = null; st.objs[a.object].loc = a.to; st.tilt = 0; }
  },
  pour(st, a, p, s0) {
    const spot = { a: LOC[a.at].a, r: LOC[a.at].r, y: LOC[a.at].y + 0.34 };
    st.pose = mixPose(s0, spot, ease(seg(p, 0, 0.3)));
    st.tilt = p < 0.3 ? 0 : p < 0.5 ? 75 * ease(seg(p, 0.3, 0.5)) : p < 0.85 ? 75 : 75 * (1 - ease(seg(p, 0.85, 1)));
    st.flow = (p >= 0.5 && p < 0.85) ? { at: a.at, trickle: a.outcome === 'failed' } : null;
    st.ring = a.at; st.mound = a.at === 'press' ? (p >= 0.85 ? true : st.mound) : st.mound;
    if (p >= 1) { st.tilt = 0; st.flow = null; if (a.at === 'balance' || LOC[a.at]) st.poursDone += (a.into === 'vial' ? 1 : 0); }
    show(st, a, p);
  },
  shake(st, a, p, s0) {
    const spot = { a: s0.a, r: s0.r, y: Math.max(s0.y, 1.0) };
    st.pose = mixPose(s0, spot, ease(seg(p, 0, 0.1)));
    const amp = a.style === 'tap' ? 0.012 : 0.03, cycles = a.style === 'tap' ? 6 : clamp(a.actual_duration_s / 6, 6, 40);
    st.off.y = (p > 0.1 && p < 0.95) ? amp * Math.sin(2 * Math.PI * cycles * p) : 0;
    st.ring = null;
  },
  press(st, a, p, s0) {
    const dn = grip(a.at, a.object), hov = grip(a.at, a.object, 0.14);
    st.pose = p < 0.35 ? mixPose(s0, hov, ease(p / 0.35)) : p < 0.6 ? mixPose(hov, dn, ease(seg(p, 0.35, 0.6))) : p < 0.7 ? dn : mixPose(dn, hov, ease(seg(p, 0.7, 1)));
    st.press = p >= 0.6 && p < 0.7 ? 1 : 0; st.ring = a.at;
    if (p >= 0.6) { st.mound = false; st.objs.tablet.loc = a.at; }
  },
  stir(st, a, p, s0) {
    const c = grip(a.at, a.object, -0.2), hov = grip(a.at, a.object, 0.1);
    st.pose = p < 0.2 ? mixPose(s0, hov, ease(p / 0.2)) : p < 0.3 ? mixPose(hov, c, ease(seg(p, 0.2, 0.3))) : p < 0.9 ? c : mixPose(c, hov, ease(seg(p, 0.9, 1)));
    const cycles = clamp(a.actual_duration_s / 60, 6, 40), phi = 2 * Math.PI * cycles * seg(p, 0.3, 0.9);
    st.off.x = p >= 0.3 && p < 0.9 ? 0.025 * Math.cos(phi) : 0; st.off.z = p >= 0.3 && p < 0.9 ? 0.025 * Math.sin(phi) : 0; st.ring = a.at;
  },
  scan(st, a, p, s0) {
    const spot = { a: LOC[a.at].a, r: LOC[a.at].r, y: LOC[a.at].y + 0.34 }, back = grip(a.at, a.object, HOVER);
    st.pose = p < 0.35 ? mixPose(s0, spot, ease(p / 0.35)) : p < 0.85 ? spot : mixPose(spot, back, ease(seg(p, 0.85, 1)));
    st.laser = p >= 0.35 && p < 0.85 ? a.at : false; st.ring = a.at;
    show(st, a, p);
  },
  read(st, a, p) { st.ring = a.at; show(st, a, p); },
  wait(st, a) { st.drum = /friability drum/i.test(a.reason || ''); st.ring = null; }
};
function apply(st, a, p, s0) {
  const h = HANDLERS[a.type]; if (!h) throw new Error('no animation for the action type ' + a.type);
  h(st, a, p, s0);
}
function simulate(tl, t) {
  const st = initialState();
  for (const a of tl.actions) {
    const s = a.actual_start_s, e = s + a.actual_duration_s;
    const s0 = Object.assign({}, st.pose);
    if (t >= e) { st.flow = null; st.laser = false; st.press = 0; st.drum = false; st.off = { x: 0, y: 0, z: 0 }; apply(st, a, 1, s0); st.done.push(a.id); }
    else if (t >= s) { st.flow = null; st.laser = false; st.press = 0; st.drum = false; st.off = { x: 0, y: 0, z: 0 }; apply(st, a, clamp((t - s) / a.actual_duration_s, 0, 1), s0); st.current = a; break; }
    else break;
  }
  const lastTest = [...tl.actions].reverse().find(a => a.step === 'test');
  st.resultsShown = !!lastTest && t >= lastTest.actual_start_s + lastTest.actual_duration_s && tl.result;
  return st;
}
function reachProblems(st) { return Math.hypot(st.pose.r, 0) > REACH + 1e-6 ? ['beyond reach'] : []; }

// ======================================================================== PART 2: drawing it (needs WebGL)
let GL = typeof THREE !== 'undefined', renderer, scene, camera, ARM = {}, W = {}, SCR = {}, RINGS = {}, FLOW = [], LASER, DRUM, MOUND, POWDER;
const cam = { c: { x: 0, y: 0.75, z: -0.3, r: 3.6, th: 0.3, ph: 0.9 } };
const world = (a, r, y) => (GL ? new THREE.Vector3(r * Math.cos(rad(a)), y, -r * Math.sin(rad(a))) : null);
const mat = (c, o) => new THREE.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.55, metalness: 0.15 }, o || {}));
function mk(geo, m, parent, x, y, z) { const o = new THREE.Mesh(geo, m); o.position.set(x || 0, y || 0, z || 0); o.castShadow = true; o.receiveShadow = true; if (parent) parent.add(o); return o; }
function sprite(text, w) { const c = document.createElement('canvas'); c.width = 256; c.height = 64; const x = c.getContext('2d'); x.fillStyle = 'rgba(255,255,255,.92)'; x.fillRect(4, 8, 248, 48); x.strokeStyle = '#86BC25'; x.lineWidth = 4; x.strokeRect(4, 8, 248, 48); x.fillStyle = '#282728'; x.font = '700 24px "Open Sans",Arial,sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(text, 128, 33); const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true })); s.scale.set(w, w / 4, 1); return s; }
function screen(g, key, w, h, x, y, z) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 128; const t = new THREE.CanvasTexture(c);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: t })); m.position.set(x, y, z); m.rotation.y = -Math.PI / 2; g.add(m);
  SCR[key] = { c, t, last: null, title: '' }; drawScreen(key, { title: 'READY', value: '', bad: false });
}
function drawScreen(key, d) {
  const s = SCR[key]; if (!s) return; const j = JSON.stringify(d); if (s.last === j) return; s.last = j;
  const x = s.c.getContext('2d'); x.fillStyle = '#101214'; x.fillRect(0, 0, 256, 128); x.strokeStyle = d.bad ? '#DA291C' : '#86BC25'; x.lineWidth = 8; x.strokeRect(4, 4, 248, 120);
  x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillStyle = '#E6E6E6'; x.font = '400 20px "Open Sans",Arial,sans-serif'; x.fillText(d.title, 128, 40); x.fillStyle = d.bad ? '#FF7A70' : '#FFFFFF'; x.font = '700 34px "Open Sans",Arial,sans-serif'; x.fillText(d.value, 128, 86); s.t.needsUpdate = true;
}
function station(s) {
  const g = new THREE.Group(), p = LOC[s.id]; g.position.set(p.r * Math.cos(rad(p.a)), TABLE_H, -p.r * Math.sin(rad(p.a))); g.rotation.y = rad(p.a); scene.add(g);
  const top = s.work_height_m - TABLE_H, T = s.type;
  mk(new THREE.CylinderGeometry(0.17, 0.17, Math.max(0.02, top - 0.02), 40), mat(0xc9ccd0, { roughness: 0.3 }), g, 0, Math.max(0.02, top - 0.02) / 2, 0);
  if (T === 'vial_rack_with_scanner') { mk(new THREE.BoxGeometry(0.22, 0.05, 0.62), mat(0xc9ccd0), g, 0.34, 0.025, 0); for (let j = 0; j < 5; j++) { mk(new THREE.CylinderGeometry(0.04, 0.04, 0.2, 20), mat(0xdfeaf0, { transparent: true, opacity: 0.4 }), g, 0.34, 0.15, -0.24 + j * 0.12).castShadow = false; } mk(new THREE.BoxGeometry(0.1, 0.14, 0.1), mat(0x15171a), g, -0.02, top + 0.07, 0.27); }
  if (T === 'balance' || T === 'hardness_gauge' || T === 'friability_tester' || T === 'dissolution_vessel') mk(new THREE.BoxGeometry(0.05, 0.16, 0.26), mat(0x15171a), g, -0.2, top + 0.08, 0);
  if (s.instrument) screen(g, s.id, 0.24, 0.12, -0.226, top + 0.09, 0);
  if (T === 'hand_press') { mk(new THREE.CylinderGeometry(0.085, 0.085, 0.04, 32), mat(0xc9ccd0, { metalness: 0.5 }), g, 0, top + 0.02, 0); MOUND = mk(new THREE.CylinderGeometry(0.042, 0.042, 0.03, 24), mat(0xe9e2cf, { roughness: 0.9 }), g, 0, top + 0.055, 0); MOUND.visible = false; }
  if (T === 'friability_tester') { DRUM = mk(new THREE.CylinderGeometry(0.09, 0.09, 0.07, 32), mat(0xcfe7f2, { transparent: true, opacity: 0.55 }), g, 0, top + 0.1, 0); DRUM.rotation.x = Math.PI / 2; }
  if (T === 'dissolution_vessel') { mk(new THREE.CylinderGeometry(0.115, 0.1, 0.3, 32, 1, true), mat(0xcfe7f2, { transparent: true, opacity: 0.25, side: THREE.DoubleSide }), g, 0, top + 0.15, 0).castShadow = false; mk(new THREE.CylinderGeometry(0.112, 0.1, 0.22, 32), new THREE.MeshStandardMaterial({ color: 0x9fd6f0, transparent: true, opacity: 0.35 }), g, 0, top + 0.12, 0).castShadow = false; }
  if (T === 'discard_bin') { const m = mat(0x3a3d40); mk(new THREE.BoxGeometry(0.3, 0.02, 0.3), m, g, 0, top + 0.01, 0); [[0, 0.14], [0, -0.14]].forEach(q => mk(new THREE.BoxGeometry(0.3, 0.2, 0.02), m, g, q[0], top + 0.11, q[1])); [0.14, -0.14].forEach(q => mk(new THREE.BoxGeometry(0.02, 0.2, 0.3), m, g, q, top + 0.11, 0)); }
  const lb = sprite(s.label, 0.4); lb.position.set(0.1, top + 0.5, 0); g.add(lb);
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.19, 0.225, 48), new THREE.MeshBasicMaterial({ color: 0x86BC25, transparent: true, opacity: 0, side: THREE.DoubleSide })); ring.rotation.x = -Math.PI / 2; ring.position.y = top + 0.01; g.add(ring); RINGS[s.id] = ring;
}
function build() {
  const wrap = $('stage');
  try { renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); } catch (e) { GL = false; return; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; wrap.insertBefore(renderer.domElement, wrap.firstChild);
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  scene = new THREE.Scene(); scene.background = new THREE.Color(dark ? 0x1d1f21 : 0xe9ebee); scene.fog = new THREE.Fog(dark ? 0x1d1f21 : 0xe9ebee, 7, 16);
  camera = new THREE.PerspectiveCamera(42, 1.6, 0.1, 60);
  scene.add(new THREE.HemisphereLight(0xffffff, dark ? 0x30343a : 0x9aa0a6, dark ? 0.55 : 0.8));
  const dl = new THREE.DirectionalLight(0xffffff, 0.85); dl.position.set(3, 5.5, 3); dl.castShadow = true; dl.shadow.mapSize.set(2048, 2048); const sc = dl.shadow.camera; sc.left = -3; sc.right = 3; sc.top = 3; sc.bottom = -3; sc.near = 1; sc.far = 14; scene.add(dl);
  const fl = mk(new THREE.PlaneGeometry(80, 80), mat(dark ? 0x26292c : 0xeef0f2, { roughness: 0.9, metalness: 0 }), scene, 0, 0, 0); fl.rotation.x = -Math.PI / 2; fl.castShadow = false;
  const tr = L.table.radius_m; mk(new THREE.CylinderGeometry(tr * 0.85, tr * 0.88, TABLE_H - 0.06, 56), mat(0x2b2d30), scene, 0, (TABLE_H - 0.06) / 2, 0);
  mk(new THREE.CylinderGeometry(tr, tr, 0.06, 64), mat(0xf2f3f4, { roughness: 0.35 }), scene, 0, TABLE_H - 0.03, 0);
  const edge = new THREE.Mesh(new THREE.RingGeometry(tr - 0.08, tr - 0.03, 96), new THREE.MeshBasicMaterial({ color: 0x86BC25, side: THREE.DoubleSide })); edge.rotation.x = -Math.PI / 2; edge.position.y = TABLE_H + 0.002; scene.add(edge);
  // the arm: a generic three-segment arm with its dimensions from the layout
  const white = mat(0xf3f4f5, { roughness: 0.35 }), darkm = mat(0x2b2d30), grn = mat(0x86BC25, { roughness: 0.4 });
  const root = new THREE.Group(); root.position.set(ROBOT.base_m.x, TABLE_H, ROBOT.base_m.z); scene.add(root);
  mk(new THREE.CylinderGeometry(0.24, 0.28, 0.1, 40), darkm, root, 0, 0.05, 0); mk(new THREE.CylinderGeometry(0.19, 0.22, H0 - TABLE_H - 0.1, 40), white, root, 0, (H0 - TABLE_H) / 2, 0);
  ARM.yaw = new THREE.Group(); ARM.yaw.position.y = H0 - TABLE_H; root.add(ARM.yaw);
  mk(new THREE.CylinderGeometry(0.1, 0.1, 0.18, 32), darkm, ARM.yaw, 0, 0, 0).rotation.x = Math.PI / 2;
  ARM.up = new THREE.Group(); ARM.yaw.add(ARM.up); mk(new THREE.CylinderGeometry(0.058, 0.062, L1, 24), white, ARM.up, L1 / 2, 0, 0).rotation.z = Math.PI / 2; mk(new THREE.CylinderGeometry(0.066, 0.066, 0.04, 24), grn, ARM.up, 0.14, 0, 0).rotation.z = Math.PI / 2;
  ARM.el = new THREE.Group(); ARM.el.position.x = L1; ARM.up.add(ARM.el); mk(new THREE.SphereGeometry(0.08, 24, 16), darkm, ARM.el, 0, 0, 0); mk(new THREE.CylinderGeometry(0.044, 0.052, L2, 24), white, ARM.el, L2 / 2, 0, 0).rotation.z = Math.PI / 2;
  ARM.wr = new THREE.Group(); ARM.wr.position.x = L2; ARM.el.add(ARM.wr); mk(new THREE.SphereGeometry(0.058, 20, 14), darkm, ARM.wr, 0, 0, 0); mk(new THREE.BoxGeometry(0.08, 0.1, 0.14), darkm, ARM.wr, 0.06, 0, 0);
  ARM.f1 = mk(new THREE.BoxGeometry(0.15, 0.022, 0.018), white, ARM.wr, 0.12, 0, 0.06); ARM.f2 = mk(new THREE.BoxGeometry(0.15, 0.022, 0.018), white, ARM.wr, 0.12, 0, -0.06);
  L.stations.forEach(station);
  const pal = [0x00A3E0, 0xC9C9C9, 0x86BC25, 0x0D8390, 0x5A5A5A, 0xE8A317, 0xDA291C];
  L.bottle_shelf.slots.forEach(s => { const p = LOC[s.id]; mk(new THREE.CylinderGeometry(0.06, 0.06, 0.02, 24), mat(0x3a3d40), scene, p.r * Math.cos(rad(p.a)), s.work_height_m - 0.09, -p.r * Math.sin(rad(p.a))); const lb = sprite(s.ingredient_id.replace('_pct', ''), 0.22); lb.position.set(p.r * Math.cos(rad(p.a)), s.work_height_m + 0.28, -p.r * Math.sin(rad(p.a))); scene.add(lb); });
  L.tool_holders.forEach(h => { const p = LOC[h.id]; mk(new THREE.CylinderGeometry(0.05, 0.06, 0.03, 24), mat(0x3a3d40), scene, p.r * Math.cos(rad(p.a)), h.work_height_m - 0.015, -p.r * Math.sin(rad(p.a))); });
  // objects
  L.objects.forEach(o => {
    const g = new THREE.Group(); scene.add(g); W[o.id] = g;
    if (o.type === 'vial') { mk(new THREE.CylinderGeometry(0.04, 0.04, 0.2, 24, 1, true), mat(0xcfe3ee, { transparent: true, opacity: 0.55, side: THREE.DoubleSide }), g, 0, 0.1, 0).castShadow = false; mk(new THREE.CylinderGeometry(0.043, 0.043, 0.03, 24), darkm, g, 0, 0.215, 0); POWDER = mk(new THREE.CylinderGeometry(0.036, 0.036, 1, 24), mat(0xffffff, { roughness: 0.9 }), g, 0, 0.003, 0); POWDER.scale.y = 0.001; }
    else if (o.type === 'tablet') mk(new THREE.CylinderGeometry(0.05, 0.05, 0.03, 32), mat(0xfaf7ee, { roughness: 0.6 }), g, 0, 0.015, 0);
    else if (o.type === 'bottle') { const i = Math.max(0, L.bottle_shelf.slots.findIndex(s => s.bottle === o.id)), bm = mat(pal[i % pal.length], { roughness: 0.4 }); mk(new THREE.CylinderGeometry(0.045, 0.045, 0.15, 24), bm, g, 0, 0, 0); mk(new THREE.CylinderGeometry(0.022, 0.03, 0.04, 16), bm, g, 0, 0.095, 0); mk(new THREE.CylinderGeometry(0.027, 0.027, 0.03, 16), mat(0xf3f4f5), g, 0, 0.13, 0); }
    else if (o.id === 'rod') { mk(new THREE.CylinderGeometry(0.009, 0.009, 0.32, 12), mat(0xc9ccd0, { metalness: 0.5 }), g, 0, 0.16, 0); mk(new THREE.CylinderGeometry(0.022, 0.022, 0.04, 16), mat(0x0D8390), g, 0, 0.34, 0); }
    else { mk(new THREE.CylinderGeometry(0.036, 0.036, 0.16, 24), mat(0xc9ccd0, { metalness: 0.5 }), g, 0, 0.08, 0); mk(new THREE.CylinderGeometry(0.05, 0.05, 0.03, 24), mat(0x005587), g, 0, 0.175, 0); }
  });
  for (let j = 0; j < 12; j++) { const m = new THREE.Mesh(new THREE.SphereGeometry(0.0115, 8, 6), new THREE.MeshBasicMaterial({ color: 0xffffff })); m.visible = false; scene.add(m); FLOW.push(m); }
  LASER = new THREE.Mesh(new THREE.BoxGeometry(0.006, 0.006, 1), new THREE.MeshBasicMaterial({ color: 0xff2a1a })); LASER.visible = false; scene.add(LASER);
  const el = renderer.domElement; let drag = null;
  el.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY }; el.setPointerCapture(e.pointerId); });
  el.addEventListener('pointermove', e => { if (!drag) return; cam.c.th -= (e.clientX - drag.x) * 0.006; cam.c.ph = clamp(cam.c.ph - (e.clientY - drag.y) * 0.005, 0.12, 1.5); drag = { x: e.clientX, y: e.clientY }; });
  const up = () => { drag = null; }; el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
  el.addEventListener('wheel', e => { e.preventDefault(); cam.c.r = clamp(cam.c.r * (1 + e.deltaY * 0.001), 1.4, 8); }, { passive: false });
  new ResizeObserver(resize).observe(wrap); resize();
}
function resize() { if (!renderer) return; const w = $('stage').clientWidth, h = $('stage').clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
function presetCam(name) {
  if (name === 'top') return { x: 0, y: 0.5, z: -0.2, r: 4.2, th: 0, ph: 0.2 };
  const s = STATION[name]; if (!s) return { x: 0, y: 0.75, z: -0.3, r: 3.6, th: 0.3, ph: 0.9 };
  const p = LOC[name], a = rad(p.a); return { x: p.r * Math.cos(a) * 1.04, y: s.work_height_m + 0.15, z: -p.r * Math.sin(a) * 1.04, r: 2.0, th: Math.atan2(-Math.cos(a), Math.sin(a)) + 1.15, ph: 0.82 };
}
function setCam(name) { Object.assign(cam.c, name === 'overview' ? { x: 0, y: 0.75, z: -0.3, r: 3.6, th: 0.3, ph: 0.9 } : presetCam(name)); }
const eeWorld = st => { const p = st.pose; return new THREE.Vector3(p.r * Math.cos(rad(p.a)) + st.off.x, p.y + st.off.y, -p.r * Math.sin(rad(p.a)) + st.off.z); };
const quat = (yaw, tilt) => new THREE.Quaternion().setFromEuler(new THREE.Euler(0, rad(yaw), rad(tilt), 'YXZ'));
function draw(st) {
  if (!GL || !renderer) return;
  const ee = eeWorld(st), a = Math.atan2(-ee.z, ee.x) * 180 / Math.PI, r = Math.hypot(ee.x, ee.z), dx = r, dy = ee.y + L3 - H0;
  let d = Math.min(Math.hypot(dx, dy), L1 + L2 - 0.002); const c = clamp((d * d - L1 * L1 - L2 * L2) / (2 * L1 * L2), -1, 1), q2 = -Math.acos(c), phi = Math.atan2(dy, dx);
  const th1 = phi - Math.atan2(L2 * Math.sin(q2), L1 + L2 * Math.cos(q2)), th2 = th1 + q2;
  ARM.yaw.rotation.y = rad(a); ARM.up.rotation.z = th1; ARM.el.rotation.z = q2; ARM.wr.rotation.z = -Math.PI / 2 - th2;
  const gap = 0.048 + 0.05 * st.fingers; ARM.f1.position.z = gap; ARM.f2.position.z = -gap;
  L.objects.forEach(o => {
    const g = W[o.id], here = st.objs[o.id];
    if (st.held === o.id) { const q = quat(st.pose.a, st.tilt); g.quaternion.copy(q); g.position.copy(ee).sub(new THREE.Vector3(0, gripOf(o.id), 0).applyQuaternion(q)); g.visible = true; }
    else if (here.loc && LOC[here.loc]) { const l = LOC[here.loc]; g.visible = true; g.quaternion.copy(quat(l.a, 0)); g.position.copy(world(l.a, l.r, l.y + (o.type === 'bottle' ? 0 : 0))); }
    else g.visible = false;
  });
  if (POWDER) { const n = L.bottle_shelf.slots.length; POWDER.scale.y = Math.max(0.001, 0.16 * Math.min(1, st.poursDone / n)); POWDER.position.y = 0.003 + POWDER.scale.y / 2; }
  if (MOUND) MOUND.visible = !!st.mound;
  if (DRUM) DRUM.rotation.y += st.drum ? 0.25 : 0;
  Object.keys(RINGS).forEach(k => { RINGS[k].material.opacity = st.ring === k ? 0.9 : 0; });
  Object.keys(SCR).forEach(k => drawScreen(k, st.screens[k] || { title: 'READY', value: '', bad: false }));
  if (st.flow && st.held) {
    const q = quat(st.pose.a, st.tilt), mouth = W[st.held].position.clone().add(new THREE.Vector3(0, 0.145, 0).applyQuaternion(q)), l = LOC[st.flow.at], to = world(l.a, l.r, l.y + 0.08);
    FLOW.forEach((m, i) => { const f = ((performance.now() / 400) + i / FLOW.length) % 1; m.visible = true; m.position.lerpVectors(mouth, to, st.flow.trickle ? f * 0.5 : f); });
  } else FLOW.forEach(m => { m.visible = false; });
  if (st.laser) { const l = LOC[st.laser], from = world(l.a, l.r, l.y + 0.14), to = ee.clone(), mid = from.clone().add(to).multiplyScalar(0.5); LASER.visible = true; LASER.position.copy(mid); LASER.scale.z = Math.max(0.01, from.distanceTo(to)); LASER.lookAt(to); } else LASER.visible = false;
  const c2 = cam.c; camera.position.set(c2.x + c2.r * Math.sin(c2.ph) * Math.sin(c2.th), c2.y + c2.r * Math.cos(c2.ph), c2.z + c2.r * Math.sin(c2.ph) * Math.cos(c2.th)); camera.lookAt(c2.x, c2.y, c2.z);
  renderer.render(scene, camera);
}

// ======================================================================== PART 3: the page
const Q = new URLSearchParams(location.search);
const TL = DATA.timelines;
let ti = 0, tNow = 0, playing = false, speed = 60, lastId = null, last = performance.now();
const verdictClass = tl => tl.outcome === 'skipped' ? 'skip' : tl.result.verdict === 'Good' ? 'pass' : 'fail';
function pickTimeline() { const want = parseInt(Q.get('trial') || '', 10); const i = TL.findIndex(t => t.trial === want); if (i >= 0) return i; const f = TL.findIndex(t => t.faults.length); return f >= 0 ? f : 0; }
function mmss(s) { s = Math.round(s); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }
function buildHud() {
  const strip = $('strip'); strip.innerHTML = '';
  TL.forEach((tl, i) => { const b = document.createElement('div'); b.className = 'tchip ' + verdictClass(tl) + (tl.outcome === 'completed_after_recovery' ? ' rec' : ''); b.textContent = tl.trial; b.title = 'Trial ' + tl.trial + ': ' + tl.outcome; b.onclick = () => select(i, 0); b.dataset.i = i; strip.appendChild(b); });
  const cs = $('camSel'); cs.innerHTML = ''; ['overview', 'top'].concat(L.camera_presets.filter(p => p !== 'overview' && p !== 'top')).forEach(n => { const o = document.createElement('option'); o.value = n; o.textContent = n[0].toUpperCase() + n.slice(1); cs.appendChild(o); });
  cs.onchange = () => setCam(cs.value);
  $('foot').textContent = (TL.length + ' trial' + (TL.length === 1 ? '' : 's') + ' embedded. Executor: ' + (TL[0] ? TL[0].executor : '') + '. Data status: ' + (TL[0] ? TL[0].data_status : '') + '. Planned and actual times are both shown for every action.');
}
function select(i, t) {
  ti = i; tNow = t; lastId = null; const tl = TL[ti];
  Array.from($('strip').children).forEach(c => c.classList.toggle('cur', +c.dataset.i === i));
  const ul = $('acts'); ul.innerHTML = '';
  tl.actions.forEach(a => { const li = document.createElement('li'); li.className = a.outcome === 'failed' ? 'failed' : a.origin; li.id = 'li-' + a.id; li.textContent = a.id + '  ' + a.type + (a.origin === 'recovery' ? '  (recovery)' : '') + '  ' + mmss(a.actual_start_s); li.onclick = () => { tNow = a.actual_start_s + 0.5 * a.actual_duration_s; playing = false; $('btnPlay').textContent = 'Play'; }; ul.appendChild(li); });
  $('slider').max = total(tl);
}
function hud(st) {
  const tl = TL[ti], a = st.current || tl.actions[tl.actions.length - 1];
  $('slider').value = tNow; $('clockT').textContent = mmss(tNow) + ' of ' + mmss(total(tl)); $('clockW').textContent = 'Trial ' + tl.trial + ', run minute ' + (tl.trial_start_minute + tNow / 60).toFixed(1);
  document.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c.dataset.p === a.phase));
  $('cap').textContent = a.caption;
  const failed = a.outcome === 'failed', rec = a.origin === 'recovery';
  $('fault').style.display = failed ? 'block' : 'none'; $('fault').textContent = failed && a.fault ? 'FAULT: ' + a.fault.cause + '. ' + a.fault.detail : '';
  $('recov').style.display = rec ? 'block' : 'none';
  const n = $('now'); n.className = 'now' + (failed ? ' fail' : rec ? ' rec' : '');
  n.innerHTML = '<b>' + a.id + ' ' + a.type + ' (' + a.step + ', ' + a.phase + ')' + (rec ? ' - RECOVERY of ' + a.recovers : '') + '</b>' + (a.reason ? '<small>Why: ' + a.reason + '</small><br>' : '') +
    '<small>actual ' + a.actual_start_s + ' s for ' + a.actual_duration_s + ' s' + (a.planned_start_s !== undefined ? ' - planned ' + a.planned_start_s + ' s for ' + a.planned_duration_s + ' s' : ' - not in the plan') + ' - outcome ' + a.outcome + '</small>';
  const res = $('res'); res.innerHTML = '';
  st.readings.forEach(r => { const d = document.createElement('div'); d.className = r.bad ? 'no' : 'ok'; d.innerHTML = '<span>' + (QUANTITY_LABEL[r.quantity] || r.quantity) + (r.expected !== undefined ? ' (expected ' + r.expected + ')' : '') + '</span><b>' + r.text + '</b>'; res.appendChild(d); });
  if (st.resultsShown) { const x = tl.result, d = document.createElement('div'); d.className = x.verdict === 'Good' ? 'ok' : 'no'; d.innerHTML = '<span>Result of the trial</span><b>' + x.verdict + '</b>'; res.appendChild(d); }
  if (a.id !== lastId) { lastId = a.id; document.querySelectorAll('#acts li').forEach(li => li.classList.remove('cur')); const li = $('li-' + a.id); if (li) { li.classList.add('cur'); li.scrollIntoView({ block: 'nearest' }); } }
}
function frame(now) {
  const dt = (now - last) / 1000; last = now;
  if (playing) { tNow += dt * speed; if (tNow >= total(TL[ti])) { tNow = total(TL[ti]); playing = false; $('btnPlay').textContent = 'Play'; } }
  const st = simulate(TL[ti], tNow); hud(st); draw(st); requestAnimationFrame(frame);
}
function selftest() {
  const out = { timelines: TL.length, actions: 0, types: {}, errors: [], webgl: !!(GL && renderer), handlers: Object.keys(HANDLERS).sort() };
  TL.forEach(tl => tl.actions.forEach(a => {
    out.actions++; out.types[a.type] = (out.types[a.type] || 0) + 1;
    [a.actual_start_s + 1e-6, a.actual_start_s + a.actual_duration_s / 2, a.actual_start_s + a.actual_duration_s - 1e-6].forEach(t => {
      try {
        const st = simulate(tl, t);
        if (!st.current || st.current.id !== a.id) out.errors.push(a.id + ': not the current action at ' + t);
        ['a', 'r', 'y'].forEach(k => { if (!isFinite(st.pose[k])) out.errors.push(a.id + ': pose ' + k + ' is not a number'); });
        if (st.pose.r > REACH + 1e-6) out.errors.push(a.id + ': beyond reach');
      } catch (e) { out.errors.push(a.id + ': ' + e.message); }
    });
  }));
  TL.forEach(tl => { const st = simulate(tl, total(tl) + 1); if (st.held) out.errors.push('trial ' + tl.trial + ': the robot still holds ' + st.held + ' at the end'); });
  out.ok = out.errors.length === 0;
  $('selftest').textContent = JSON.stringify(out); document.title = (out.ok ? 'SELFTEST OK ' : 'SELFTEST FAIL ') + out.actions + ' actions';
}
function boot() {
  if (GL) build();
  if (!GL || !renderer) { $('nogl').style.display = 'flex'; }
  buildHud(); ti = pickTimeline(); select(ti, 0);
  const act = Q.get('action'); if (act) { const a = TL[ti].actions.find(x => x.id === act); if (a) tNow = a.actual_start_s + 0.5 * a.actual_duration_s; }
  if (Q.get('t')) tNow = clamp(parseFloat(Q.get('t')) || 0, 0, total(TL[ti]));
  if (Q.get('speed')) { speed = parseFloat(Q.get('speed')); $('speed').value = String(speed); }
  $('speed').onchange = () => { speed = parseFloat($('speed').value); };
  $('btnPlay').onclick = () => { playing = !playing; $('btnPlay').textContent = playing ? 'Pause' : 'Play'; };
  const jump = dir => { const tl = TL[ti]; const cur = tl.actions.findIndex(a => tNow >= a.actual_start_s && tNow < a.actual_start_s + a.actual_duration_s); const i = clamp((cur < 0 ? 0 : cur) + dir, 0, tl.actions.length - 1); tNow = tl.actions[i].actual_start_s + 0.5 * tl.actions[i].actual_duration_s; };
  $('btnPrev').onclick = () => jump(-1); $('btnNext').onclick = () => jump(1);
  $('slider').oninput = () => { tNow = parseFloat($('slider').value); playing = false; $('btnPlay').textContent = 'Play'; };
  const cname = Q.get('cam') || 'overview'; $('camSel').value = cname; setCam(cname);
  if (Q.get('autoplay') === '1') { playing = true; $('btnPlay').textContent = 'Pause'; }
  if (Q.get('selftest') === '1') selftest();
  requestAnimationFrame(frame);
}
window.__viewer = { simulate, HANDLERS, DATA, REACH, LOC };
boot();
})();
