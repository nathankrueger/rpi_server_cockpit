// Unit tests for static/viewport-heal.js — run with `node --test tests/js/`
// (also driven by tests/test_viewport_heal.py under pytest).
//
// The driver is exercised against FakeWebKit: a deterministic model of a
// phone browser with the iOS 26 bug — after the keyboard closes, the fixed
// layer stays at the keyboard-up height until a scroll forces a viewport
// recompute. A manual clock makes every timer/frame deterministic.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const VH = require(path.join(__dirname, '..', '..', 'static', 'viewport-heal.js'));
const { assessViewport, createViewportHealer, isEditable, constants: C } = VH;

const SCREEN_H = 956;     // iPhone visual viewport height (pt)
const KEYBOARD_H = 346;   // keyboard height (pt) — matches the bug screenshots

// ---------------------------------------------------------------- fake clock

class Clock {
    constructor() { this.t = 0; this.seq = 0; this.timers = new Map(); }
    setTimeout(fn, ms) {
        const id = ++this.seq;
        this.timers.set(id, { at: this.t + Math.max(0, ms || 0), fn, every: null });
        return id;
    }
    setInterval(fn, ms) {
        const id = ++this.seq;
        this.timers.set(id, { at: this.t + ms, fn, every: ms });
        return id;
    }
    clear(id) { this.timers.delete(id); }
    advance(ms) {
        const end = this.t + ms;
        for (;;) {
            let nextId = null, next = null;
            for (const [id, tm] of this.timers) {
                if (tm.at <= end && (next == null || tm.at < next.at)) { next = tm; nextId = id; }
            }
            if (!next) break;
            this.t = next.at;
            if (next.every) next.at += next.every; else this.timers.delete(nextId);
            next.fn();
        }
        this.t = end;
    }
}

// ------------------------------------------------------- simulated WebKit

class FakeWebKit {
    /**
     * @param {object} opts
     *   bug:             fixed layer stays shrunk after keyboard close
     *   healsAfterScrolls: how many scrollTo() calls it takes to recompute
     *                      (1 = any scroll fixes it; Infinity = never)
     *   scrollMax:        maximum scrollY
     */
    constructor(opts = {}) {
        this.clock = new Clock();
        this.bug = opts.bug !== false;
        this.healsAfterScrolls = opts.healsAfterScrolls ?? 1;
        this.scrollMax = opts.scrollMax ?? 3000;
        this.scrollCalls = [];
        this.listeners = {};
        this.docListeners = {};
        this.vvListeners = {};

        this.innerHeight = SCREEN_H;
        this.scrollX = 0;
        this.scrollY = opts.scrollY ?? 0;
        this.fixedHeight = SCREEN_H;     // what WebKit gives position:fixed
        this.fixedTop = 0;
        this.stuckScrollsSeen = 0;

        const self = this;
        this.visualViewport = {
            height: SCREEN_H, offsetTop: 0, scale: 1,
            addEventListener(type, fn) { (self.vvListeners[type] ||= []).push(fn); },
        };
        this.document = {
            activeElement: null,
            visibilityState: 'visible',
            addEventListener(type, fn) { (self.docListeners[type] ||= []).push(fn); },
        };
        this.performance = { now: () => this.clock.t };
        this.probe = { getBoundingClientRect: () => ({ top: self.fixedTop, height: self.fixedHeight }) };
    }

    // window API used by the healer
    setTimeout(fn, ms) { return this.clock.setTimeout(fn, ms); }
    clearTimeout(id) { this.clock.clear(id); }
    setInterval(fn, ms) { return this.clock.setInterval(fn, ms); }
    clearInterval(id) { this.clock.clear(id); }
    requestAnimationFrame(fn) { return this.clock.setTimeout(fn, 16); }
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }

    scrollTo(x, y) {
        y = Math.max(0, Math.min(this.scrollMax, y));
        const moved = y !== this.scrollY;
        this.scrollCalls.push(y);
        this.scrollX = x;
        this.scrollY = y;
        // A scroll that actually moves makes WebKit recompute its viewport.
        if (moved && this.isStuck()) {
            this.stuckScrollsSeen++;
            if (this.stuckScrollsSeen >= this.healsAfterScrolls) this.unstick();
        }
        this.fire(this.listeners, 'scroll');
    }

    fire(map, type) { (map[type] || []).forEach((fn) => fn({ type })); }

    isStuck() { return this.fixedHeight !== this.visualViewport.height || this.fixedTop !== 0; }
    unstick() { this.fixedHeight = this.visualViewport.height; this.fixedTop = 0; }

    // ---- user actions
    focusInput() {
        this.document.activeElement = { tagName: 'INPUT', type: 'text' };
        this.visualViewport.height = SCREEN_H - KEYBOARD_H;
        this.innerHeight = SCREEN_H - KEYBOARD_H;
        this.fixedHeight = SCREEN_H - KEYBOARD_H;
        this.fire(this.vvListeners, 'resize');
    }
    dismissKeyboard() {
        this.document.activeElement = null;
        this.visualViewport.height = SCREEN_H;
        this.innerHeight = SCREEN_H;
        // THE BUG: the fixed layer is left at the keyboard-up height.
        if (!this.bug) this.fixedHeight = SCREEN_H;
        this.fire(this.listeners, 'focusout');
        this.fire(this.vvListeners, 'resize');
    }
    pinchZoom(scale) {
        this.visualViewport.scale = scale;
        this.visualViewport.height = SCREEN_H / scale;
        this.fire(this.vvListeners, 'resize');
    }
}

function setup(opts) {
    const wk = new FakeWebKit(opts);
    const healer = createViewportHealer(wk, wk.probe);
    return { wk, healer };
}

// ------------------------------------------------- assessViewport (pure)

const HEALTHY = {
    vvHeight: 956, vvOffsetTop: 0, vvScale: 1, innerHeight: 956,
    fixedTop: 0, fixedHeight: 956, editing: false,
};

test('assess: consistent viewport is ok', () => {
    assert.deepEqual(assessViewport(HEALTHY), { state: 'ok', reason: 'consistent' });
});

test('assess: the screenshot state (fixed layer one keyboard short) is stuck', () => {
    const r = assessViewport({ ...HEALTHY, fixedHeight: 956 - KEYBOARD_H });
    assert.equal(r.state, 'stuck');
    assert.equal(r.reason, 'fixed-layer-height');
});

test('assess: lingering visualViewport.offsetTop is stuck', () => {
    assert.equal(assessViewport({ ...HEALTHY, vvOffsetTop: 24 }).reason, 'visual-viewport-offset');
});

test('assess: innerHeight vs visualViewport mismatch is stuck', () => {
    assert.equal(assessViewport({ ...HEALTHY, vvHeight: 932, fixedHeight: 932 }).reason,
        'inner-vs-visual-height');
});

test('assess: offset fixed layer is stuck', () => {
    assert.equal(assessViewport({ ...HEALTHY, fixedTop: -40 }).reason, 'fixed-layer-offset');
});

test('assess: sub-tolerance rounding is ok', () => {
    const r = assessViewport({ ...HEALTHY, fixedHeight: 956 + C.TOLERANCE_PX, vvOffsetTop: 0.5 });
    assert.equal(r.state, 'ok');
});

test('assess: keyboard up (editing) is never judged', () => {
    const r = assessViewport({ ...HEALTHY, vvHeight: 610, innerHeight: 610, fixedHeight: 956, editing: true });
    assert.deepEqual(r, { state: 'skip', reason: 'editing' });
});

test('assess: pinch zoom is never judged', () => {
    const r = assessViewport({ ...HEALTHY, vvScale: 2, vvHeight: 478, vvOffsetTop: 300 });
    assert.deepEqual(r, { state: 'skip', reason: 'zoomed' });
});

test('assess: no visualViewport API is skipped', () => {
    assert.equal(assessViewport({ ...HEALTHY, vvHeight: null }).state, 'skip');
});

test('isEditable: text fields raise the keyboard, buttons/checkboxes do not', () => {
    assert.equal(isEditable({ tagName: 'INPUT', type: 'text' }), true);
    assert.equal(isEditable({ tagName: 'INPUT', type: 'number' }), true);
    assert.equal(isEditable({ tagName: 'INPUT' }), true);
    assert.equal(isEditable({ tagName: 'TEXTAREA' }), true);
    assert.equal(isEditable({ tagName: 'DIV', isContentEditable: true }), true);
    assert.equal(isEditable({ tagName: 'INPUT', type: 'checkbox' }), false);
    assert.equal(isEditable({ tagName: 'INPUT', type: 'color' }), false);
    assert.equal(isEditable({ tagName: 'BUTTON' }), false);
    assert.equal(isEditable(null), false);
});

// ------------------------------------------------- driver vs buggy WebKit

test('reproduces the bug: without the healer the page stays broken', () => {
    const wk = new FakeWebKit({ scrollY: 1200 });
    wk.focusInput();
    wk.dismissKeyboard();
    wk.clock.advance(60_000);
    assert.equal(wk.fixedHeight, SCREEN_H - KEYBOARD_H, 'fixed layer should remain shrunk');
});

test('heals the stuck fixed layer after the keyboard is dismissed', () => {
    const { wk, healer } = setup({ scrollY: 1200 });
    wk.focusInput();
    wk.clock.advance(1000);
    assert.equal(healer.stats.heals, 0, 'must not act while the keyboard is up');

    wk.dismissKeyboard();
    assert.equal(wk.fixedHeight, SCREEN_H - KEYBOARD_H, 'bug present right after dismissal');
    wk.clock.advance(2000);

    assert.equal(wk.fixedHeight, SCREEN_H, 'fixed layer restored to full height');
    assert.equal(healer.stats.heals, 1);
    assert.equal(healer.stats.recoveries, 1);
    assert.equal(wk.scrollY, 1200, 'scroll position restored exactly');
    assert.equal(healer.stats.lastAssessment.state, 'ok');
});

test('waits CONFIRM_MS before acting (rides out keyboard/toolbar animation)', () => {
    const { wk, healer } = setup({ scrollY: 500 });
    wk.focusInput();
    wk.dismissKeyboard();
    // focusout settle + first sighting, but not yet confirmed
    wk.clock.advance(C.FOCUSOUT_SETTLE_MS + C.CONFIRM_MS - 1);
    assert.equal(healer.stats.heals, 0);
    // transient mismatch resolves on its own -> no heal ever happens
    wk.unstick();
    wk.clock.advance(5000);
    assert.equal(healer.stats.heals, 0);
    assert.deepEqual(wk.scrollCalls, []);
});

test('nudge works at the very top of the page (not clamped to a no-op)', () => {
    const { wk, healer } = setup({ scrollY: 0 });
    wk.focusInput();
    wk.dismissKeyboard();
    wk.clock.advance(2000);
    assert.equal(wk.fixedHeight, SCREEN_H);
    assert.equal(wk.scrollY, 0);
    assert.equal(healer.stats.recoveries, 1);
});

test('nudge works at the very bottom of the page (where the video was)', () => {
    const { wk, healer } = setup({ scrollY: 3000, scrollMax: 3000 });
    wk.focusInput();
    wk.dismissKeyboard();
    wk.clock.advance(2000);
    assert.equal(wk.fixedHeight, SCREEN_H);
    assert.equal(wk.scrollY, 3000);
    assert.equal(healer.stats.recoveries, 1);
});

test('escalates when a 1px nudge does not take', () => {
    const { wk, healer } = setup({ scrollY: 800, healsAfterScrolls: 3 });
    wk.focusInput();
    wk.dismissKeyboard();
    wk.clock.advance(5000);
    assert.equal(wk.fixedHeight, SCREEN_H);
    assert.ok(healer.stats.heals >= 2, 'needed more than one attempt');
    assert.equal(healer.stats.giveUps, 0);
    assert.equal(wk.scrollY, 800);
});

test('gives up after MAX_ATTEMPTS instead of scroll-jittering forever', () => {
    const { wk, healer } = setup({ scrollY: 800, healsAfterScrolls: Infinity });
    wk.focusInput();
    wk.dismissKeyboard();
    wk.clock.advance(60_000);
    assert.equal(healer.stats.heals, C.MAX_ATTEMPTS);
    assert.equal(healer.stats.giveUps, 1);
    assert.equal(wk.scrollY, 800, 'page left where the user had it');
});

test('a fresh trigger after giving up starts a new episode', () => {
    const { wk, healer } = setup({ scrollY: 800, healsAfterScrolls: Infinity });
    wk.focusInput();
    wk.dismissKeyboard();
    wk.clock.advance(60_000);
    assert.equal(healer.stats.heals, C.MAX_ATTEMPTS);
    wk.healsAfterScrolls = 1;
    wk.stuckScrollsSeen = 0;
    wk.fire(wk.listeners, 'pageshow');
    wk.clock.advance(2000);
    assert.equal(wk.fixedHeight, SCREEN_H);
    assert.equal(healer.stats.recoveries, 1);
});

test('the safety-net poll heals a stuck state no event announced', () => {
    const { wk, healer } = setup({ scrollY: 400 });
    // Stuck with no focusout/resize event at all (e.g. arose while backgrounded)
    wk.fixedHeight = SCREEN_H - KEYBOARD_H;
    wk.clock.advance(C.POLL_MS * 3);
    assert.equal(wk.fixedHeight, SCREEN_H);
    assert.equal(healer.stats.recoveries, 1);
});

test('returning to the tab heals immediately', () => {
    const { wk, healer } = setup({ scrollY: 400 });
    wk.fixedHeight = SCREEN_H - KEYBOARD_H;
    wk.document.visibilityState = 'visible';
    wk.fire(wk.docListeners, 'visibilitychange');
    wk.clock.advance(C.CONFIRM_MS + C.VERIFY_MS + 100);
    assert.equal(wk.fixedHeight, SCREEN_H);
    assert.equal(healer.stats.recoveries, 1);
});

test('healthy browser: no scrolls ever, through keyboard cycles and zoom', () => {
    const { wk, healer } = setup({ scrollY: 700, bug: false });
    for (let i = 0; i < 5; i++) {
        wk.focusInput();
        wk.clock.advance(800);
        wk.dismissKeyboard();
        wk.clock.advance(800);
    }
    wk.pinchZoom(2);
    wk.clock.advance(10_000);
    wk.pinchZoom(1);
    wk.clock.advance(10_000);
    assert.equal(healer.stats.heals, 0);
    assert.deepEqual(wk.scrollCalls, []);
    assert.ok(healer.stats.checks > 0);
});

test('never acts while a field keeps focus with the keyboard up', () => {
    const { wk, healer } = setup({ scrollY: 700 });
    wk.focusInput();
    wk.fixedHeight = SCREEN_H; // any mismatch while typing is legitimate
    wk.clock.advance(30_000);
    assert.equal(healer.stats.heals, 0);
    assert.deepEqual(wk.scrollCalls, []);
});

test('pauses polling while the tab is hidden', () => {
    const { wk, healer } = setup();
    wk.document.visibilityState = 'hidden';
    wk.clock.advance(C.POLL_MS * 5);
    assert.equal(healer.stats.checks, 0);
});

test('stop() cancels all timers', () => {
    const { wk, healer } = setup();
    healer.stop();
    wk.fixedHeight = 100;
    wk.clock.advance(60_000);
    assert.equal(healer.stats.checks, 0);
});
