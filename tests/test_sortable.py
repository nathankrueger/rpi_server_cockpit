"""
Pins drag-to-reorder for charts (/charts) and sensor tiles (/monitor), and
collapse for charts (sensor tiles are deliberately not collapsible).

  * test_sortable_unit — Node tests of the pure ordering math in
    static/sortable.js (tests/js/sortable.test.js).
  * test_charts_* / test_sensors_* — render the REAL page templates through
    Jinja with the real CSS/JS, stub `fetch` with canned timeseries data, and
    drive real PointerEvents at the drag handles in headless Chromium. They
    assert on DOM order, collapse state, localStorage persistence, and that a
    periodic refresh neither rebuilds the tiles nor fights an in-progress drag.

dashboard.js (matrix animation + socket.io) is dropped from the harness: a
never-idle page hangs headless Chromium (see CLAUDE.md), and neither feature
depends on it.
"""

import json
import pathlib
import re
import shutil
import subprocess

import jinja2
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / 'static'
NODE = shutil.which('node')
CHROMIUM = shutil.which('chromium') or shutil.which('chromium-browser')

needs_chromium = pytest.mark.skipif(CHROMIUM is None, reason='chromium not installed')

# Canned API: six numeric series; 'empty' has no data (its chart isn't drawn).
SERIES = [
    {'id': f's{i}', 'name': f'Sensor {i}', 'units': 'W', 'category': 'Power'}
    for i in range(1, 6)
] + [{'id': 'empty', 'name': 'Empty', 'units': 'W', 'category': 'Power'}]

FETCH_STUB = """
<script>
(function () {
  const SERIES = %(series)s;
  const now = Date.now() / 1000;
  function pts(id) {
    if (id === 'empty') return [];
    const n = parseInt(id.slice(1), 10);
    return Array.from({length: 30}, (_, i) => ({timestamp: now - (30 - i) * 60, value: n * 10 + i}));
  }
  function ok(body) {
    return Promise.resolve({ok: true, status: 200, statusText: 'OK',
      json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body))});
  }
  window.__fetchCount = 0;
  window.fetch = function (url, opts) {
    url = String(url);
    window.__fetchCount++;
    if (url.endsWith('/api/timeseries/list')) return ok(SERIES);
    if (url.endsWith('/api/timeseries/data/batch')) {
      const ids = JSON.parse(opts.body).timeseries_ids;
      return ok(ids.map(id => {
        const meta = SERIES.find(s => s.id === id);
        return Object.assign({}, meta, {data: pts(id)});
      }));
    }
    if (url.endsWith('/api/timeseries/minmax/batch')) {
      const ids = JSON.parse(opts.body).timeseries_ids;
      const out = {};
      ids.forEach(id => { const p = pts(id); if (p.length) out[id] = {
        min: p[0].value, max: p[p.length - 1].value, oldest: p[0].value}; });
      return ok(out);
    }
    if (url.includes('/api/claude/usage')) return ok({enabled: false});
    return Promise.reject(new TypeError('offline harness: ' + url));
  };
  %(seed)s
})();
</script>
"""

# Shared in-page test helpers: pointer simulation + assertion log.
HELPERS = """
<script>
window.__results = [];
function check(name, ok, detail) {
  window.__results.push({name: name, ok: !!ok, detail: detail === undefined ? null : detail});
}
const wait = ms => new Promise(r => setTimeout(r, ms));
// rAF can stall under headless virtual time; never let a test hang on it
const frame = () => Promise.race([new Promise(r => requestAnimationFrame(() => r())), wait(50)]);
function ptr(type, target, x, y) {
  target.dispatchEvent(new PointerEvent(type, {bubbles: true, cancelable: true, pointerId: 7,
    pointerType: 'touch', isPrimary: true, clientX: x, clientY: y, button: 0}));
}
function center(el) {
  const r = el.getBoundingClientRect();
  return {x: r.left + r.width / 2, y: r.top + r.height / 2};
}
// Press a handle, glide to (x, y) in steps, optionally hold before releasing,
// then wait for the snap animation to settle (ghost removed).
async function dragTo(handle, x, y, opts) {
  opts = opts || {};
  const s = center(handle);
  ptr('pointerdown', handle, s.x, s.y);
  const steps = 12;
  for (let i = 1; i <= steps; i++) {
    ptr('pointermove', handle, s.x + (x - s.x) * i / steps, s.y + (y - s.y) * i / steps);
    await frame();
  }
  if (opts.beforeRelease) await opts.beforeRelease();
  ptr(opts.cancel ? 'pointercancel' : 'pointerup', handle, x, y);
  await settled();
}
// The animation clock doesn't advance under --virtual-time-budget, so tests
// fast-forward in-flight slides before measuring positions. (The driver itself
// never depends on animations finishing: every one has a timer fallback.)
function flush() {
  document.getAnimations().forEach(a => { try { a.finish(); } catch (e) {} });
}
async function settled() {
  for (let i = 0; i < 60 && document.querySelector('.sort-ghost'); i++) await wait(25);
  flush();
  await frame();
}
function finish() {
  const out = document.createElement('pre');
  out.id = '__out';
  out.textContent = 'RESULT' + JSON.stringify(window.__results) + 'END';
  document.body.appendChild(out);
}
</script>
"""


def _render(template, seed_js, test_js, tmp_path):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / 'templates')))
    html = env.get_template(template).render(
        versioned_static=lambda f: (STATIC / f).as_uri(),
        url_for=lambda *a, **k: (STATIC / k.get('filename', '')).as_uri(),
    )
    # Drop the never-idle matrix/socket script (see module docstring).
    html = re.sub(r'<script[^>]*dashboard\.js[^>]*></script>', '', html)
    stub = FETCH_STUB % {'series': json.dumps(SERIES), 'seed': seed_js}
    html = html.replace('<head>', '<head>' + stub + HELPERS, 1)
    html = html.replace('</body>', f'<script>window.addEventListener("load", () => setTimeout(async () => {{\n'
                                   f'try {{ {test_js} }} catch (e) {{ check("exception", false, String(e && e.stack || e)); }}\n'
                                   f'finish(); }}, 1500));</script></body>', 1)
    page = tmp_path / template
    page.write_text(html)
    return page


def _run(page, width, height):
    proc = subprocess.run(
        [CHROMIUM, '--headless=new', '--no-sandbox', '--disable-gpu',
         '--disable-dev-shm-usage', '--hide-scrollbars',
         f'--window-size={width},{height}', '--virtual-time-budget=60000',
         '--dump-dom', page.as_uri()],
        capture_output=True, text=True, timeout=180,
    )
    m = re.search(r'<pre id="__out">RESULT(.*?)END</pre>', proc.stdout, re.S)
    assert m, f'harness produced no result:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}'
    raw = m.group(1).replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return json.loads(raw)


def _assert_all(results):
    assert results, 'no checks ran'
    failed = [r for r in results if not r['ok']]
    assert not failed, json.dumps(failed, indent=2)


# --------------------------------------------------------------------- unit

@pytest.mark.skipif(NODE is None, reason='node not installed')
def test_sortable_unit():
    proc = subprocess.run([NODE, '--test', str(ROOT / 'tests' / 'js' / 'sortable.test.js')],
                          capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert re.search(r'^# fail 0$', proc.stdout, re.M), proc.stdout


@pytest.mark.parametrize('template, page_script', [
    ('charts.html', 'charts.js'), ('monitor.html', 'monitor.js')])
def test_pages_load_sortable_before_page_script(template, page_script):
    html = (ROOT / 'templates' / template).read_text()
    scripts = re.findall(r"versioned_static\('([^']+\.js)'\)", html)
    assert 'sortable.js' in scripts
    assert scripts.index('sortable.js') < scripts.index(page_script), scripts


# ------------------------------------------------------------------- charts

CHART_SEED = """
localStorage.setItem('autoRefreshEnabled', 'false');
localStorage.setItem('chartConfigs', JSON.stringify([
  {id: 'A', name: 'Chart A', seriesIds: ['s1'], nameManuallySet: true},
  {id: 'B', name: 'Chart B', seriesIds: ['s2'], nameManuallySet: true},
  {id: 'X', name: 'No data', seriesIds: ['empty'], nameManuallySet: true},
  {id: 'C', name: '<b>Chart C</b>', seriesIds: ['s3'], nameManuallySet: true},
]));
"""

CHART_TEST = r"""
const container = document.getElementById('charts-container');
const domIds = () => Array.from(container.querySelectorAll(':scope > .chart-wrapper')).map(e => e.dataset.sortId);
const savedIds = () => JSON.parse(localStorage.getItem('chartConfigs')).map(c => c.id);
const saved = id => JSON.parse(localStorage.getItem('chartConfigs')).find(c => c.id === id);
const wrap = id => document.getElementById('chart-' + id);

check('renders charts with data, in saved order', JSON.stringify(domIds()) === '["A","B","C"]', domIds());
check('each chart has a drag handle and a title', ['A','B','C'].every(id =>
  wrap(id).querySelector(':scope > .drag-handle') && wrap(id).querySelector('.chart-title')));
check('handle is not on the title row', !document.querySelector('.chart-header .drag-handle'));
check('handle is small, faint, in the top-right corner', (() => {
  const w = wrap('A').getBoundingClientRect(), h = wrap('A').querySelector('.drag-handle');
  const r = h.getBoundingClientRect(), op = parseFloat(getComputedStyle(h).opacity);
  return Math.abs(r.right - (w.right - 2)) <= 2 && Math.abs(r.top - (w.top + 2)) <= 2
    && r.width <= 30 && r.height <= 30 && op <= 0.3;
})(), (() => { const r = wrap('A').querySelector('.drag-handle').getBoundingClientRect();
  const w = wrap('A').getBoundingClientRect();
  return {dRight: w.right - r.right, dTop: r.top - w.top, w: r.width, h: r.height,
    opacity: getComputedStyle(wrap('A').querySelector('.drag-handle')).opacity}; })());
check('title is text, not HTML (no injection)', wrap('C').querySelector('.chart-title').textContent === '<b>Chart C</b>'
  && !wrap('C').querySelector('.chart-title b'));
check('plotly drew into the plot area', !!wrap('A').querySelector('.chart-plot .main-svg'));
const plotA = wrap('A').querySelector('.chart-plot');
check('expanded chart has a real plot height', plotA.getBoundingClientRect().height > 200,
  plotA.getBoundingClientRect().height);

// --- drag A below C, inspecting the lift / follow / slide / snap mechanics
let c = wrap('C').getBoundingClientRect();
const bTop0 = wrap('B').getBoundingClientRect().top;
// drag straight down, in the grip's own column (the grip is in the top-right corner)
const gx = center(wrap('A').querySelector('.drag-handle')).x;
const gy = c.top + c.height * 0.8;
let midDrag = null;
await dragTo(wrap('A').querySelector('.drag-handle'), gx, gy, {
  beforeRelease: async () => {
    const bSlid = wrap('B').getAnimations().some(a => a.id === 'sort-slide');
    flush();
    const ghost = document.querySelector('.sort-ghost');
    const gr = ghost && ghost.getBoundingClientRect();
    midDrag = {
      ghostOnBody: !!ghost && ghost.parentElement === document.body,
      ghostFixed: !!ghost && getComputedStyle(ghost).position === 'fixed',
      // no id in the ghost duplicates one in the page
      ghostNoIds: !!ghost && !ghost.id && [...ghost.querySelectorAll('[id]')].every(
        e => document.querySelectorAll('[id="' + e.id + '"]').length === 1),
      // the trace's clip-path must resolve to the GHOST's own clipPath: the
      // original's is inside the visibility:hidden placeholder and clips all
      ghostHasTrace: !!ghost && (() => {
        const clipped = ghost.querySelector('.scatterlayer path.js-line').closest('[clip-path]');
        const id = clipped && (clipped.getAttribute('clip-path').match(/#([^)'"]+)/) || [])[1];
        const clip = id && document.getElementById(id);
        return !!clip && ghost.contains(clip);
      })(),
      ghostOpaque: !!ghost && getComputedStyle(ghost).backgroundColor === 'rgb(10, 12, 14)',
      // the pointer is still inside the ghost: it follows the finger
      ghostUnderPointer: !!gr && gx >= gr.left && gx <= gr.right && gy >= gr.top && gy <= gr.bottom,
      ghostRect: gr && [gr.left, gr.top, gr.right, gr.bottom].map(Math.round),
      pointer: [Math.round(gx), Math.round(gy)],
      placeholder: wrap('A').classList.contains('sort-placeholder'),
      placeholderContentHidden: getComputedStyle(wrap('A').querySelector('.chart-plot')).visibility === 'hidden',
      bSlid: bSlid,
      bMovedUp: wrap('B').getBoundingClientRect().top < bTop0,
    };
  }
});
check('lift: ghost clone pinned to body, fixed, no duplicate ids',
  midDrag.ghostOnBody && midDrag.ghostFixed && midDrag.ghostNoIds, midDrag);
check('lift: ghost keeps the plot line and is opaque', midDrag.ghostHasTrace && midDrag.ghostOpaque, midDrag);
check('follow: ghost tracks the pointer', midDrag.ghostUnderPointer, midDrag);
check('placeholder: real tile marks the slot with its content hidden',
  midDrag.placeholder && midDrag.placeholderContentHidden, midDrag);
check('slide: neighbour B glided (animated) out of the way', midDrag.bSlid && midDrag.bMovedUp, midDrag);
check('snap: ghost removed and tile restored after release',
  !document.querySelector('.sort-ghost') && !wrap('A').classList.contains('sort-placeholder'));
check('drag A below C reorders the DOM', JSON.stringify(domIds()) === '["B","C","A"]', domIds());
check('new order persisted; hidden chart X keeps its slot',
  JSON.stringify(savedIds()) === '["B","C","X","A"]', savedIds());
check('dragging class cleared after drop', !container.querySelector('.sort-dragging')
  && !document.body.classList.contains('sort-in-progress'));
check('plot survived the move (not rebuilt)', wrap('A').querySelector('.chart-plot') === plotA);

// --- a cancelled drag restores the order
c = wrap('B').getBoundingClientRect();
const a = wrap('A').getBoundingClientRect();
await dragTo(wrap('B').querySelector('.drag-handle'), a.left + 50, a.top + a.height * 0.8, {cancel: true});
check('pointercancel restores the original order', JSON.stringify(domIds()) === '["B","C","A"]', domIds());
check('cancel does not persist', JSON.stringify(savedIds()) === '["B","C","X","A"]', savedIds());

// --- collapse B
const tall = wrap('B').getBoundingClientRect().height;
wrap('B').querySelector('.chart-collapse-btn').click();
await frame();
const short = wrap('B').getBoundingClientRect().height;
check('collapse shrinks the chart to its header', short < 80 && tall > 300, {tall: tall, short: short});
check('collapsed plot is hidden', getComputedStyle(wrap('B').querySelector('.chart-plot')).display === 'none');
check('collapse persisted', saved('B').collapsed === true, saved('B'));
check('aria-expanded reflects state',
  wrap('B').querySelector('.chart-collapse-btn').getAttribute('aria-expanded') === 'false');

// --- refresh keeps order + collapse, updates in place
await updateCharts(true);
await frame();
check('refresh keeps the dragged order', JSON.stringify(domIds()) === '["B","C","A"]', domIds());
check('refresh keeps the chart collapsed', wrap('B').classList.contains('collapsed'));
check('refresh updates in place (same plot element)', wrap('A').querySelector('.chart-plot') === plotA);
check('collapsed chart is not redrawn while collapsed',
  wrap('B').querySelector('.chart-plot').dataset.stale === '1');

// --- a refresh that lands mid-drag is deferred until the drop
const cRect = wrap('C').getBoundingClientRect();
await dragTo(wrap('A').querySelector('.drag-handle'), cRect.left + 50, cRect.top + 10, {
  beforeRelease: async () => {
    // structure change mid-drag: would normally rebuild the container
    chartConfigs.find(x => x.id === 'X').seriesIds = ['s4'];
    await updateCharts(true);
    check('mid-drag refresh does not rebuild the container',
      !!container.querySelector('.sort-dragging') && !wrap('X'));
  }
});
check('deferred render ran after the drop', !!wrap('X'), domIds());
check('dropped order survives the deferred rebuild',
  domIds().indexOf('A') < domIds().indexOf('C'), domIds());

// --- expand B again: drawn from cached data with real height
wrap('B').querySelector('.chart-collapse-btn').click();
await frame(); await frame();
const plotB = wrap('B').querySelector('.chart-plot');
check('expand draws the plot', !!plotB.querySelector('.main-svg') && plotB.getBoundingClientRect().height > 200,
  plotB.getBoundingClientRect().height);
check('expand persisted', saved('B').collapsed === false);

// --- keyboard reorder from the handle
const order0 = domIds();
const h = wrap(order0[1]).querySelector('.drag-handle');
h.focus();
h.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowUp', bubbles: true}));
check('ArrowUp on a handle moves the chart up one', domIds()[0] === order0[1], {before: order0, after: domIds()});
check('keyboard move persisted', savedIds().indexOf(order0[1]) < savedIds().indexOf(order0[0]), savedIds());
check('handle keeps focus after keyboard move', document.activeElement === h);
"""


@needs_chromium
def test_charts_drag_and_collapse(tmp_path):
    page = _render('charts.html', CHART_SEED, CHART_TEST, tmp_path)
    _assert_all(_run(page, 1240, 3000))


# ------------------------------------------------------------------ sensors

SENSOR_SEED = """
localStorage.setItem('selectedSensors', JSON.stringify(['s1', 's2', 's3', 's4', 'empty']));
localStorage.setItem('weatherLocation', 'Nowhere');
"""

SENSOR_TEST = r"""
const container = document.getElementById('sensor-data');
const domIds = () => Array.from(container.querySelectorAll(':scope > .sensor-item')).map(e => e.dataset.sortId);
const savedIds = () => JSON.parse(localStorage.getItem('selectedSensors'));
const tile = id => container.querySelector(`.sensor-item[data-sort-id="${id}"]`);

await updateSensorDisplay();
check('tiles render in saved order', JSON.stringify(domIds()) === '["s1","s2","s3","s4","empty"]', domIds());
check('values shown', tile('s1').querySelector('.sensor-value').textContent.startsWith('39.00'),
  tile('s1').querySelector('.sensor-value').textContent);
check('no-data tile marked', tile('empty').classList.contains('sensor-no-data'));
const s1 = tile('s1');

// --- drag s1 onto s3's far half
const r3 = tile('s3').getBoundingClientRect();
const r1 = s1.getBoundingClientRect();
const sameRow = Math.abs(r3.top - r1.top) < 10;
await dragTo(s1.querySelector('.drag-handle'),
  sameRow ? r3.left + r3.width * 0.8 : r3.left + 20,
  sameRow ? r3.top + r3.height / 2 : r3.top + r3.height * 0.8);
check('no ghost left behind', !document.querySelector('.sort-ghost') && !container.querySelector('.sort-placeholder'));
check('drag s1 past s3 reorders', JSON.stringify(domIds()) === '["s2","s3","s1","s4","empty"]',
  {layout: sameRow ? 'grid-row' : 'column', order: domIds()});
check('order persisted to selectedSensors', JSON.stringify(savedIds()) === '["s2","s3","s1","s4","empty"]', savedIds());

// --- refresh keeps order and reuses tiles
await updateSensorDisplay();
check('refresh keeps dragged order', JSON.stringify(domIds()) === '["s2","s3","s1","s4","empty"]', domIds());
check('refresh updates tiles in place', tile('s1') === s1);

// --- snap lands the ghost exactly on the slot
{
  flush();
  const r2 = tile('s2').getBoundingClientRect();
  const h = tile('s4').querySelector('.drag-handle');
  const hs = center(h);
  ptr('pointerdown', h, hs.x, hs.y);
  for (let i = 1; i <= 8; i++) { ptr('pointermove', h, hs.x + (r2.left + 20 - hs.x) * i / 8, hs.y + (r2.top + 5 - hs.y) * i / 8); await frame(); }
  ptr('pointerup', h, r2.left + 20, r2.top + 5);
  const ghost = document.querySelector('.sort-ghost');
  // the ghost's final inline translate is the slot's resting position, scale back to 1
  const m = ghost && ghost.style.translate.match(/^([-\d.]+)px ([-\d.]+)px/);
  await wait(400);   // > SNAP_MS: the glide has finished
  flush();
  const slot = tile('s4').getBoundingClientRect();
  check('snap: ghost glides onto the placeholder slot', !!m && Math.abs(parseFloat(m[1]) - slot.left) < 2
    && Math.abs(parseFloat(m[2]) - slot.top) < 2 && ghost.style.scale === '1',
    {ghost: ghost && ghost.style.translate, scale: ghost && ghost.style.scale, slot: [slot.left, slot.top]});
  await settled();
  check('snap: reorder committed after settle', domIds().indexOf('s4') < domIds().indexOf('s2'), domIds());
}

// --- sensor tiles are not collapsible; the grip sits in the corner, faint
check('sensor tiles have no collapse control', !container.querySelector('.sensor-collapse-btn, .collapse-arrow'));
check('sensor grip is in the top-right corner and faint', (() => {
  const t = tile('s1').getBoundingClientRect(), h = tile('s1').querySelector('.drag-handle');
  const r = h.getBoundingClientRect();
  return Math.abs(r.right - (t.right - 1)) <= 2 && Math.abs(r.top - (t.top + 1)) <= 2
    && parseFloat(getComputedStyle(h).opacity) <= 0.3;
})(), (() => { const t = tile('s1').getBoundingClientRect(), r = tile('s1').querySelector('.drag-handle').getBoundingClientRect();
  return {dRight: t.right - r.right, dTop: r.top - t.top}; })());

// --- a refresh mid-drag only updates values; order stays the user's
const r4 = tile('s4').getBoundingClientRect();
await dragTo(tile('s2').querySelector('.drag-handle'), r4.left + r4.width * 0.8, r4.top + r4.height * 0.8, {
  beforeRelease: async () => {
    const mid = domIds();
    await updateSensorDisplay();
    check('mid-drag refresh leaves the live order alone', JSON.stringify(domIds()) === JSON.stringify(mid),
      {mid: mid, after: domIds()});
  }
});
check('drop after mid-drag refresh persisted', JSON.stringify(savedIds()) === JSON.stringify(domIds()),
  {saved: savedIds(), dom: domIds()});

// --- saving settings keeps the dragged order, appends new picks
const before = savedIds();
openSettingsModal();
document.querySelector('.sensor-checkbox[data-sensor-id="s5"]').checked = true;
document.querySelector('.sensor-checkbox[data-sensor-id="empty"]').checked = false;
await saveSettings();
const expected = before.filter(id => id !== 'empty').concat(['s5']);
check('settings save keeps user order, appends new, drops removed',
  JSON.stringify(savedIds()) === JSON.stringify(expected), {expected: expected, got: savedIds()});
"""


@needs_chromium
@pytest.mark.parametrize('width', [1240, 390], ids=['desktop-grid', 'phone-column'])
def test_sensors_drag(tmp_path, width):
    page = _render('monitor.html', SENSOR_SEED, SENSOR_TEST, tmp_path)
    _assert_all(_run(page, width, 3000))
