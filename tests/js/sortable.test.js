// Unit tests for the pure ordering math in static/sortable.js.
// Run with `node --test tests/js/` (also driven by tests/test_sortable.py).
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const S = require(path.join(__dirname, '..', '..', 'static', 'sortable.js'));
const { shouldInsertAfter, reorderSubset, mergeSelectionOrder, sortByOrder, autoScrollStep, hitTest } = S.utils;
const C = S.constants;

const rect = (left, top, width, height) => ({ left, top, width, height });

// ---------------------------------------------------------- shouldInsertAfter

test('list: pointer above target midpoint -> before, below -> after', () => {
    const target = rect(0, 500, 300, 400);   // expanded chart, mid y=700
    const drag = rect(0, 0, 300, 50);        // collapsed chart above it
    assert.equal(shouldInsertAfter(target, drag, 10, 699), false);
    assert.equal(shouldInsertAfter(target, drag, 10, 701), true);
});

test('list: no oscillation when a short tile passes a tall one', () => {
    // [B(50) A(400)] dragging B down into A. Before A's midpoint: stays before.
    const A = rect(0, 70, 300, 400);
    const B = rect(0, 0, 300, 50);
    assert.equal(shouldInsertAfter(A, B, 10, 200), false);
    // Past A's midpoint B goes after A: [A(0..400) B(420..470)].
    assert.equal(shouldInsertAfter(A, B, 10, 300), true);
    // Pointer (y=300) is now over A at its new position; A's midpoint is 200,
    // so the decision is still "after" -> no flip-flop.
    const Anew = rect(0, 0, 300, 400);
    const Bnew = rect(0, 420, 300, 50);
    assert.equal(shouldInsertAfter(Anew, Bnew, 10, 300), true);
});

test('grid: same-row neighbours compare on x', () => {
    const target = rect(220, 0, 200, 70);
    const drag = rect(0, 0, 200, 70);
    assert.equal(shouldInsertAfter(target, drag, 300, 35), false);
    assert.equal(shouldInsertAfter(target, drag, 330, 35), true);
});

test('grid: other-row targets compare on y', () => {
    const target = rect(220, 90, 200, 70);
    const drag = rect(0, 0, 200, 70);
    assert.equal(shouldInsertAfter(target, drag, 400, 100), false);
    assert.equal(shouldInsertAfter(target, drag, 230, 150), true);
});

// ---------------------------------------------------------- reorderSubset

test('reorderSubset: full reorder', () => {
    assert.deepEqual(reorderSubset(['a', 'b', 'c'], ['c', 'a', 'b']), ['c', 'a', 'b']);
});

test('reorderSubset: hidden items (charts with no data) keep their slots', () => {
    // b and d are not on screen; a, c, e reordered to e, a, c
    assert.deepEqual(
        reorderSubset(['a', 'b', 'c', 'd', 'e'], ['e', 'a', 'c']),
        ['e', 'b', 'a', 'd', 'c']);
});

test('reorderSubset: unknown ids ignored, nothing lost or duplicated', () => {
    const out = reorderSubset(['a', 'b', 'c'], ['zzz', 'c', 'a']);
    assert.deepEqual(out, ['c', 'b', 'a']);
    assert.deepEqual([...out].sort(), ['a', 'b', 'c']);
});

test('reorderSubset: empty visible order is a no-op', () => {
    assert.deepEqual(reorderSubset(['a', 'b'], []), ['a', 'b']);
});

// ---------------------------------------------------------- mergeSelectionOrder

test('mergeSelectionOrder: keeps user order, appends new, drops removed', () => {
    // user dragged order: c, a, b. Settings checkboxes (category order): a, b, d
    assert.deepEqual(mergeSelectionOrder(['c', 'a', 'b'], ['a', 'b', 'd']), ['a', 'b', 'd']);
    assert.deepEqual(mergeSelectionOrder(['c', 'a', 'b'], ['a', 'b', 'c', 'd']), ['c', 'a', 'b', 'd']);
    assert.deepEqual(mergeSelectionOrder(['b', 'a'], ['a', 'b']), ['b', 'a'], 'unchanged selection keeps order');
    assert.deepEqual(mergeSelectionOrder([], ['x', 'y']), ['x', 'y']);
    assert.deepEqual(mergeSelectionOrder(['x'], ['y', 'y']), ['y'], 'no duplicates');
});

// ---------------------------------------------------------- sortByOrder

test('sortByOrder: orders by saved order, unknowns last and stable', () => {
    const items = [{ id: 'a' }, { id: 'n1' }, { id: 'b' }, { id: 'n2' }, { id: 'c' }];
    const out = sortByOrder(items, ['c', 'a', 'b'], x => x.id).map(x => x.id);
    assert.deepEqual(out, ['c', 'a', 'b', 'n1', 'n2']);
});

// ---------------------------------------------------------- autoScrollStep

test('autoScrollStep: zero in the middle, up near top, down near bottom, capped', () => {
    assert.equal(autoScrollStep(400, 800), 0);
    assert.ok(autoScrollStep(10, 800) < 0);
    assert.ok(autoScrollStep(790, 800) > 0);
    assert.equal(autoScrollStep(-50, 800), -C.AUTOSCROLL_MAX_STEP);
    assert.equal(autoScrollStep(5000, 800), C.AUTOSCROLL_MAX_STEP);
    assert.ok(Math.abs(autoScrollStep(5, 800)) > Math.abs(autoScrollStep(60, 800)), 'faster nearer the edge');
});

// ---------------------------------------------------------- hitTest

test('hitTest: finds the rect under the point, null in gaps', () => {
    const rects = [
        { key: 'a', left: 0, top: 0, width: 100, height: 50 },
        { key: 'b', left: 0, top: 60, width: 100, height: 400 },
    ];
    assert.equal(hitTest(rects, 10, 10), 'a');
    assert.equal(hitTest(rects, 99, 459), 'b');
    assert.equal(hitTest(rects, 10, 55), null, 'gap between tiles');
    assert.equal(hitTest(rects, 100, 10), null, 'right edge is exclusive');
    assert.equal(hitTest([], 0, 0), null);
});
