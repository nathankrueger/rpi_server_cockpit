/**
 * Viewport healer — self-repair for the iOS 26 WebKit "stuck fixed layer" bug.
 *
 * THE BUG (WebKit regression, iOS 26.x; rdar://162396204, webkit.org/b/300523,
 * Apple forums thread 800125): after the on-screen keyboard is shown and then
 * dismissed, WebKit sometimes fails to restore the viewport that
 * `position: fixed` elements are laid out against. The fixed layer stays
 * shrunk to the keyboard-up size (or offset from the visual viewport), so on
 * this dashboard the matrix canvas (`fixed; height: 100%`) and the nav dock
 * (`fixed; bottom: 30px`) end ~a keyboard-height above the bottom of the
 * screen, leaving a black band of bare <body> below. Scrolling does not clear
 * it, and making the fixed element taller does not help either — WebKit clips
 * fixed content to the stale viewport. Only a reload or a fresh viewport
 * recomputation recovers.
 *
 * THE FIX: don't guess at triggers — *measure* the inconsistency and heal it.
 * A zero-width, invisible fixed probe (`top: 0; bottom: 0`) reports the height
 * WebKit is actually giving the fixed layer. In a healthy, unzoomed page with
 * no text field focused, that must equal `visualViewport.height`, the visual
 * viewport must sit at offsetTop 0, and `innerHeight` must match it too. Any
 * persistent disagreement is the bug; we heal it by nudging the scroll
 * position (scrolling forces WebKit to recompute the viewport), escalating to
 * a larger jump if the nudge doesn't take, and giving up after a few attempts
 * so an engine whose numbers legitimately differ can never be scroll-jittered
 * in a loop.
 *
 * Deliberately NOT treated as the bug (state 'skip'):
 *   - a focused text field: the keyboard is legitimately up;
 *   - pinch zoom (scale != 1): the visual viewport legitimately differs;
 *   - no visualViewport API: nothing to compare against.
 * A mismatch must also persist across two checks CONFIRM_MS apart, so the
 * toolbar-collapse / keyboard-close animations never trigger a nudge.
 *
 * The decision logic (`assessViewport`) and the driver (`createViewportHealer`)
 * take all their inputs by injection so they're unit-tested under Node
 * (tests/js/viewport_heal.test.js) against a simulated buggy WebKit.
 *
 * Debugging on a device: append `?vpdebug` to the URL to show a live overlay
 * of the measured metrics and healer stats.
 */
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.ViewportHealer = api;
        if (root.document) {
            root.viewportHealer = api.install(root);
        }
    }
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    // px of disagreement tolerated (sub-pixel rounding, hairline borders)
    const TOLERANCE_PX = 2;
    // a mismatch must persist this long before we act (rides out animations)
    const CONFIRM_MS = 250;
    // how long after a heal before we re-check whether it took
    const VERIFY_MS = 150;
    // healing attempts per episode before giving up (episode resets on a
    // healthy reading or a fresh trigger such as focusout / pageshow)
    const MAX_ATTEMPTS = 4;
    // low-rate safety net: catches the stuck state however it arose
    const POLL_MS = 3000;
    // keyboard-close animation length on iOS; check after it settles
    const FOCUSOUT_SETTLE_MS = 400;

    const EDITABLE_TAGS = { INPUT: true, TEXTAREA: true, SELECT: true };
    const NON_TEXT_INPUTS = {
        button: true, checkbox: true, color: true, file: true, hidden: true,
        image: true, radio: true, range: true, reset: true, submit: true,
    };

    /** True when `el` is a field that raises the on-screen keyboard. */
    function isEditable(el) {
        if (!el || !el.tagName) return false;
        if (el.isContentEditable) return true;
        if (!EDITABLE_TAGS[el.tagName]) return false;
        if (el.tagName === 'INPUT') {
            const type = (el.type || 'text').toLowerCase();
            return !NON_TEXT_INPUTS[type];
        }
        return true;
    }

    /**
     * Pure decision: is the viewport healthy, stuck, or not judgeable now?
     *
     * @param {object} m metrics:
     *   vvHeight, vvOffsetTop, vvScale  — window.visualViewport (null if absent)
     *   innerHeight                     — window.innerHeight
     *   fixedTop, fixedHeight           — fixed probe's bounding rect
     *   editing                         — a keyboard-raising field has focus
     * @returns {{state: 'ok'|'stuck'|'skip', reason: string}}
     */
    function assessViewport(m) {
        if (m.vvHeight == null) return { state: 'skip', reason: 'no-visual-viewport' };
        if (m.editing) return { state: 'skip', reason: 'editing' };
        if (Math.abs((m.vvScale == null ? 1 : m.vvScale) - 1) > 0.01) {
            return { state: 'skip', reason: 'zoomed' };
        }
        if (m.fixedHeight != null && Math.abs(m.fixedHeight - m.vvHeight) > TOLERANCE_PX) {
            return { state: 'stuck', reason: 'fixed-layer-height' };
        }
        if (m.fixedTop != null && Math.abs(m.fixedTop) > TOLERANCE_PX) {
            return { state: 'stuck', reason: 'fixed-layer-offset' };
        }
        if (Math.abs(m.vvOffsetTop || 0) > TOLERANCE_PX) {
            return { state: 'stuck', reason: 'visual-viewport-offset' };
        }
        if (m.innerHeight != null && Math.abs(m.innerHeight - m.vvHeight) > TOLERANCE_PX) {
            return { state: 'stuck', reason: 'inner-vs-visual-height' };
        }
        return { state: 'ok', reason: 'consistent' };
    }

    /**
     * Healing strategies, tried in order (cycling) on successive attempts.
     * Each receives the window and must leave the scroll position where it
     * found it.
     */
    const STRATEGIES = [
        // 1px scroll nudge and back. Scrolling makes WebKit recompute the
        // viewport. Nudge *toward* content so it isn't clamped to a no-op at
        // the top or bottom edge.
        function nudge(win, done) {
            const x = win.scrollX || 0;
            const y = win.scrollY || 0;
            win.scrollTo(x, y > 0 ? y - 1 : y + 1);
            nextFrame(win, function () {
                win.scrollTo(x, y);
                done();
            });
        },
        // Larger jump to the top and back: a bigger viewport change for the
        // cases a 1px nudge doesn't shake loose. Briefly visible, but only
        // ever runs while the page is already visibly broken.
        function jump(win, done) {
            const x = win.scrollX || 0;
            const y = win.scrollY || 0;
            win.scrollTo(x, 0);
            nextFrame(win, function () {
                win.scrollTo(x, y);
                done();
            });
        },
    ];

    function nextFrame(win, fn) {
        if (typeof win.requestAnimationFrame === 'function') {
            win.requestAnimationFrame(function () { fn(); });
        } else {
            win.setTimeout(fn, 16);
        }
    }

    function now(win) {
        if (win.performance && typeof win.performance.now === 'function') {
            return win.performance.now();
        }
        return Date.now();
    }

    /**
     * Driver. `win` is a window (or a test double exposing the same subset:
     * visualViewport, innerHeight, scrollX/Y, scrollTo, setTimeout,
     * clearTimeout, setInterval, requestAnimationFrame, performance,
     * addEventListener, document{activeElement, visibilityState,
     * addEventListener}).
     *
     * @param {object} win
     * @param {object} probe  element whose getBoundingClientRect() is the fixed layer
     */
    function createViewportHealer(win, probe) {
        const stats = {
            checks: 0,
            heals: 0,          // healing strategies executed
            recoveries: 0,     // stuck episodes that ended healthy after healing
            giveUps: 0,        // episodes abandoned after MAX_ATTEMPTS
            lastAssessment: null,
            lastMetrics: null,
        };
        let stuckSince = null;   // time the current mismatch was first seen
        let attempts = 0;        // heals in the current episode
        let healing = false;     // a strategy is mid-flight
        let gaveUp = false;
        let timer = null;

        function measure() {
            const vv = win.visualViewport;
            const rect = probe ? probe.getBoundingClientRect() : null;
            return {
                vvHeight: vv ? vv.height : null,
                vvOffsetTop: vv ? vv.offsetTop : null,
                vvScale: vv ? vv.scale : null,
                innerHeight: win.innerHeight,
                fixedTop: rect ? rect.top : null,
                fixedHeight: rect ? rect.height : null,
                editing: isEditable(win.document && win.document.activeElement),
            };
        }

        // One pending check at a time. A new request never pulls an existing
        // deadline *earlier*: focusout asks for FOCUSOUT_SETTLE_MS and the
        // visualViewport resize that immediately follows must not cut that
        // keyboard-close settle period short.
        let timerAt = null;
        function schedule(ms, force) {
            const at = now(win) + ms;
            if (timer != null) {
                if (!force && timerAt >= at) return;
                win.clearTimeout(timer);
            }
            timerAt = at;
            timer = win.setTimeout(function () {
                timer = null;
                timerAt = null;
                check();
            }, ms);
        }

        /** New trigger (focusout, pageshow, ...): start a fresh episode. */
        function resetEpisode() {
            attempts = 0;
            gaveUp = false;
            stuckSince = null;
        }

        function check() {
            if (healing) return;
            const metrics = measure();
            const result = assessViewport(metrics);
            stats.checks++;
            stats.lastMetrics = metrics;
            stats.lastAssessment = result;

            if (result.state !== 'stuck') {
                if (result.state === 'ok' && attempts > 0) stats.recoveries++;
                if (result.state === 'ok') {
                    attempts = 0;
                    gaveUp = false;
                }
                stuckSince = null;
                return result;
            }

            if (gaveUp) return result;

            const t = now(win);
            if (stuckSince == null) {
                // First sighting: confirm it persists before acting.
                stuckSince = t;
                schedule(CONFIRM_MS);
                return result;
            }
            if (t - stuckSince < CONFIRM_MS) {
                schedule(CONFIRM_MS - (t - stuckSince));
                return result;
            }

            if (attempts >= MAX_ATTEMPTS) {
                gaveUp = true;
                stats.giveUps++;
                return result;
            }

            const strategy = STRATEGIES[attempts % STRATEGIES.length];
            attempts++;
            stats.heals++;
            healing = true;
            strategy(win, function () {
                healing = false;
                // Keep stuckSince: if still stuck, the next check heals again
                // without re-waiting CONFIRM_MS.
                schedule(VERIFY_MS, true);
            });
            return result;
        }

        function onTrigger(ms) {
            // Ignore the scroll/resize events our own healing scrolls cause.
            return function () { if (!healing) schedule(ms); };
        }

        function onFreshTrigger(ms) {
            return function () {
                resetEpisode();
                schedule(ms);
            };
        }

        const vv = win.visualViewport;
        if (vv && typeof vv.addEventListener === 'function') {
            vv.addEventListener('resize', onTrigger(CONFIRM_MS));
            vv.addEventListener('scroll', onTrigger(CONFIRM_MS));
        }
        win.addEventListener('focusout', onFreshTrigger(FOCUSOUT_SETTLE_MS));
        win.addEventListener('pageshow', onFreshTrigger(0));
        win.addEventListener('orientationchange', onFreshTrigger(FOCUSOUT_SETTLE_MS));
        win.addEventListener('scroll', onTrigger(CONFIRM_MS), { passive: true });
        if (win.document && typeof win.document.addEventListener === 'function') {
            win.document.addEventListener('visibilitychange', function () {
                if (win.document.visibilityState === 'visible') onFreshTrigger(0)();
            });
        }
        const poll = win.setInterval(function () {
            if (!win.document || win.document.visibilityState !== 'hidden') check();
        }, POLL_MS);

        return {
            check: check,
            measure: measure,
            stats: stats,
            stop: function () {
                win.clearInterval(poll);
                if (timer != null) win.clearTimeout(timer);
            },
        };
    }

    function createProbe(doc) {
        const probe = doc.createElement('div');
        probe.id = 'viewport-probe';
        probe.setAttribute('aria-hidden', 'true');
        probe.style.cssText = [
            'position: fixed', 'top: 0', 'bottom: 0', 'left: 0', 'width: 0',
            'visibility: hidden', 'pointer-events: none', 'z-index: -1',
        ].join(';');
        doc.body.appendChild(probe);
        return probe;
    }

    function installDebugOverlay(win, healer) {
        const doc = win.document;
        const box = doc.createElement('pre');
        box.id = 'viewport-debug';
        box.style.cssText = [
            'position: fixed', 'top: 50%', 'left: 4px', 'z-index: 99999',
            'margin: 0', 'padding: 6px', 'font: 11px/1.3 monospace',
            'background: rgba(0,0,0,0.85)', 'color: #0f0',
            'border: 1px solid #0f0', 'pointer-events: none', 'white-space: pre',
        ].join(';');
        doc.body.appendChild(box);
        function render() {
            const m = healer.measure();
            const a = assessViewport(m);
            const s = healer.stats;
            box.textContent =
                'vv.h      ' + fmt(m.vvHeight) + '\n' +
                'vv.top    ' + fmt(m.vvOffsetTop) + '\n' +
                'vv.scale  ' + fmt(m.vvScale) + '\n' +
                'innerH    ' + fmt(m.innerHeight) + '\n' +
                'fixed.top ' + fmt(m.fixedTop) + '\n' +
                'fixed.h   ' + fmt(m.fixedHeight) + '\n' +
                'editing   ' + m.editing + '\n' +
                'state     ' + a.state + ' (' + a.reason + ')\n' +
                'heals ' + s.heals + '  rec ' + s.recoveries + '  giveup ' + s.giveUps;
        }
        function fmt(v) { return v == null ? '-' : Math.round(v * 10) / 10; }
        render();
        win.setInterval(render, 500);
    }

    function install(win) {
        const doc = win.document;
        function start() {
            const healer = createViewportHealer(win, createProbe(doc));
            if (/[?&]vpdebug\b/.test(win.location ? win.location.search : '')) {
                installDebugOverlay(win, healer);
            }
            win.viewportHealer = healer;
            healer.check();
            return healer;
        }
        if (doc.body) return start();
        doc.addEventListener('DOMContentLoaded', start);
        return null;
    }

    return {
        assessViewport: assessViewport,
        createViewportHealer: createViewportHealer,
        isEditable: isEditable,
        install: install,
        constants: {
            TOLERANCE_PX: TOLERANCE_PX,
            CONFIRM_MS: CONFIRM_MS,
            VERIFY_MS: VERIFY_MS,
            MAX_ATTEMPTS: MAX_ATTEMPTS,
            POLL_MS: POLL_MS,
            FOCUSOUT_SETTLE_MS: FOCUSOUT_SETTLE_MS,
        },
    };
});
