"""
Pins the iOS 26 "stuck fixed layer" self-heal (static/viewport-heal.js).

Bug: after the iOS keyboard is dismissed, WebKit can leave the viewport that
position:fixed elements use shrunk by the keyboard's height — the matrix
canvas and nav dock end mid-screen over a black band that scrolling can't
clear. See the header of static/viewport-heal.js.

Two layers of tests:
  * test_viewport_heal_unit — runs tests/js/viewport_heal.test.js under Node:
    the decision logic plus the driver against a simulated buggy WebKit
    (heals, restores scroll position, escalates, gives up, never acts while
    typing / zoomed / healthy).
  * test_*_real_chromium — loads the real module in headless Chromium and
    proves its measurements read a healthy page as consistent, i.e. the
    healer never scroll-nudges a correctly behaving browser.
  * test_every_page_loads_the_healer — each page template includes the
    script, so a new page or a template edit can't silently drop it.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS_TEST = ROOT / 'tests' / 'js' / 'viewport_heal.test.js'
MODULE = ROOT / 'static' / 'viewport-heal.js'

NODE = shutil.which('node')
CHROMIUM = shutil.which('chromium') or shutil.which('chromium-browser')


@pytest.mark.skipif(NODE is None, reason='node not installed')
def test_viewport_heal_unit():
    proc = subprocess.run(
        [NODE, '--test', str(JS_TEST)],
        capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert re.search(r'^# fail 0$', proc.stdout, re.M), proc.stdout


@pytest.mark.parametrize('template', ['index.html', 'monitor.html', 'charts.html'])
def test_every_page_loads_the_healer(template):
    html = (ROOT / 'templates' / template).read_text()
    scripts = re.findall(r"versioned_static\('([^']+\.js)'\)", html)
    assert 'viewport-heal.js' in scripts, f'{template} must load viewport-heal.js'
    # load it first so it's armed before the heavier page scripts run
    assert scripts[0] == 'viewport-heal.js', scripts


def _chromium_measure(tmp_path, body_extra=''):
    """Load the real module in headless Chromium; return its stats as dict."""
    page = tmp_path / 'harness.html'
    page.write_text(f"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>body {{ margin:0; background:#000; min-height:100vh; }}
.tall {{ height: 4000px; }}</style>
<script src="{MODULE.as_uri()}"></script>
</head><body>
<div class="tall"></div>
{body_extra}
<pre id="out"></pre>
<script>
  setTimeout(function () {{
    var h = window.viewportHealer;
    window.scrollTo(0, 1500);
    h.check();
    setTimeout(function () {{
      h.check();
      document.getElementById('out').textContent = 'RESULT' + JSON.stringify({{
        stats: h.stats,
        probe: !!document.getElementById('viewport-probe'),
        scrollY: window.scrollY,
      }}) + 'END';
    }}, 1200);
  }}, 200);
</script>
</body></html>""")
    proc = subprocess.run(
        [CHROMIUM, '--headless=new', '--no-sandbox', '--disable-gpu',
         '--disable-dev-shm-usage', '--window-size=390,844',
         '--virtual-time-budget=5000', '--dump-dom', page.as_uri()],
        capture_output=True, text=True, timeout=90,
    )
    m = re.search(r'RESULT(.*?)END', proc.stdout, re.S)
    assert m, f'harness produced no result:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}'
    return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&'))


@pytest.mark.skipif(CHROMIUM is None, reason='chromium not installed')
def test_healthy_page_reads_consistent_in_real_chromium(tmp_path):
    r = _chromium_measure(tmp_path)
    assert r['probe'], 'fixed probe element was not installed'
    stats = r['stats']
    assert stats['checks'] >= 2
    assert stats['lastAssessment'] == {'state': 'ok', 'reason': 'consistent'}, stats
    m = stats['lastMetrics']
    assert abs(m['fixedHeight'] - m['vvHeight']) <= 2, m
    assert abs(m['innerHeight'] - m['vvHeight']) <= 2, m
    assert stats['heals'] == 0, 'healer nudged a healthy browser'
    assert r['scrollY'] == 1500


@pytest.mark.skipif(CHROMIUM is None, reason='chromium not installed')
def test_focused_input_is_skipped_in_real_chromium(tmp_path):
    r = _chromium_measure(
        tmp_path,
        '<input id="f" type="text"><script>document.getElementById("f").focus();</script>',
    )
    stats = r['stats']
    assert stats['lastAssessment']['state'] == 'skip', stats
    assert stats['lastAssessment']['reason'] == 'editing'
    assert stats['heals'] == 0
