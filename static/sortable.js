/**
 * Sortable — drag-to-reorder for a container of tiles (charts, sensor tiles).
 *
 * Works on touch and mouse via Pointer Events, from a dedicated drag handle
 * (`touch-action: none` on the handle only, so the rest of the page still
 * scrolls normally on a phone, and Plotly's own touch gestures are untouched).
 * HTML5 drag-and-drop is deliberately not used: it is unreliable on iOS.
 *
 * Feel:
 *   - LIFT: on pickup a visual clone (the "ghost") is pinned to <body> with
 *     position:fixed and follows the pointer, raised with a shadow. The real
 *     tile stays in the list as the dashed *placeholder* marking the landing
 *     slot. (A clone on <body> can't be clipped or mis-positioned by a
 *     transformed/overflow-hidden ancestor; Plotly's SVG clones fine.)
 *   - SLIDE: whenever the placeholder moves, every tile whose position changed
 *     animates from where it *was* to where it now is (FLIP), so neighbours
 *     glide out of the way instead of jumping.
 *   - SNAP: on release the ghost glides into the placeholder's slot, then is
 *     removed and the real tile revealed. A cancelled drag (pointercancel /
 *     Escape) slides the placeholder back home and snaps there.
 *
 * Hit-testing uses each tile's *layout* rect (captured right after a DOM move,
 * before animations start, in document coordinates) — not
 * elementFromPoint/getBoundingClientRect — because mid-slide tiles are
 * visually displaced and testing against moving targets makes the drop slot
 * jitter. Every animation also has a timer fallback, so a throttled tab (or a
 * stalled animation clock) can never leave a drag stuck half-finished.
 *
 * Works identically for a single-column list of very different heights
 * (charts: expanded 400px vs collapsed ~50px) and a multi-column grid (sensor
 * tiles). The page auto-scrolls when the pointer nears the top/bottom edge.
 * prefers-reduced-motion turns the animations off.
 *
 * Keyboard: the handle is a <button>; ArrowUp/ArrowLeft and
 * ArrowDown/ArrowRight move the tile one position (with the same slide).
 *
 * Usage:
 *   const s = Sortable.attach(container, {
 *       itemSelector: '.sensor-item',
 *       handleSelector: '.drag-handle',
 *       getId: el => el.dataset.sortId,
 *       onReorder: ids => { ...persist ids... },   // only when order changed
 *       onDragEnd: () => { ...flush deferred re-renders... },
 *   });
 *   s.isDragging()  // true from pickup until the snap finishes: callers must
 *                   // not rebuild the container meanwhile
 *
 * The ordering math is pure (Sortable.utils) and unit-tested under Node
 * (tests/js/sortable.test.js); the DOM driver is exercised in headless
 * Chromium by tests/test_sortable.py.
 */
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.Sortable = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    // px from the viewport edge where auto-scroll kicks in
    const AUTOSCROLL_EDGE_PX = 70;
    // max px scrolled per animation frame at the very edge
    const AUTOSCROLL_MAX_STEP = 18;
    // neighbour slide duration
    const SLIDE_MS = 200;
    // release: ghost glides into its slot
    const SNAP_MS = 220;
    // pickup: ghost grows to its lifted scale
    const LIFT_MS = 120;
    const LIFT_SCALE = 1.03;
    const EASE = 'cubic-bezier(0.2, 0.8, 0.2, 1)';

    // ------------------------------------------------------------ pure utils

    /**
     * Should the dragged tile go *after* `target` given the pointer position?
     *
     * Tiles on the same row (grid neighbours) are compared on x; otherwise on
     * y. Comparing against the target's midpoint is what keeps the drag
     * stable: after a move, the pointer sits on the same side of the
     * (shifted) neighbour's midpoint, so tiles of very different heights
     * don't oscillate back and forth.
     */
    function shouldInsertAfter(targetRect, dragRect, x, y) {
        const sameRow = Math.abs(targetRect.top - dragRect.top) <
            Math.min(targetRect.height, dragRect.height) / 2;
        if (sameRow) return x > targetRect.left + targetRect.width / 2;
        return y > targetRect.top + targetRect.height / 2;
    }

    /**
     * Apply a new order for a *subset* of ids to the full ordered list.
     *
     * The page may render only some items (e.g. charts with no data in the
     * current time range are not drawn). Items not in `visibleOrder` keep
     * their slots; the visible ones are re-dealt into the slots they occupy.
     * Unknown ids in `visibleOrder` are ignored.
     */
    function reorderSubset(fullOrder, visibleOrder) {
        const full = fullOrder.slice();
        const fullSet = new Set(full);
        const visible = visibleOrder.filter(function (id) { return fullSet.has(id); });
        const visibleSet = new Set(visible);
        let next = 0;
        return full.map(function (id) {
            return visibleSet.has(id) ? visible[next++] : id;
        });
    }

    /**
     * New selection, preserving the user's existing order: ids that remain
     * selected keep their position, newly selected ids are appended in the
     * order given, deselected ids drop out.
     */
    function mergeSelectionOrder(previousOrder, selectedIds) {
        const selected = new Set(selectedIds);
        const kept = previousOrder.filter(function (id) { return selected.has(id); });
        const keptSet = new Set(kept);
        const added = [];
        selectedIds.forEach(function (id) {
            if (!keptSet.has(id)) {
                keptSet.add(id);
                added.push(id);
            }
        });
        return kept.concat(added);
    }

    /** Order `items` by their position in `order` (unknown ids go last, stable). */
    function sortByOrder(items, order, getId) {
        const rank = new Map();
        order.forEach(function (id, i) { rank.set(id, i); });
        return items
            .map(function (item, i) { return { item: item, i: i }; })
            .sort(function (a, b) {
                const ra = rank.has(getId(a.item)) ? rank.get(getId(a.item)) : Infinity;
                const rb = rank.has(getId(b.item)) ? rank.get(getId(b.item)) : Infinity;
                return ra === rb ? a.i - b.i : ra - rb;
            })
            .map(function (e) { return e.item; });
    }

    /** Pixels to auto-scroll this frame for a pointer at clientY (+up/-down sign). */
    function autoScrollStep(clientY, viewportHeight) {
        if (clientY < AUTOSCROLL_EDGE_PX) {
            const depth = (AUTOSCROLL_EDGE_PX - Math.max(clientY, 0)) / AUTOSCROLL_EDGE_PX;
            return -Math.ceil(depth * AUTOSCROLL_MAX_STEP);
        }
        if (clientY > viewportHeight - AUTOSCROLL_EDGE_PX) {
            const depth = (clientY - (viewportHeight - AUTOSCROLL_EDGE_PX)) / AUTOSCROLL_EDGE_PX;
            return Math.ceil(Math.min(depth, 1) * AUTOSCROLL_MAX_STEP);
        }
        return 0;
    }

    /**
     * Which rect (if any) contains the point? `rects` is [{key, left, top,
     * width, height}] in the same coordinate space as (x, y).
     */
    function hitTest(rects, x, y) {
        for (let i = 0; i < rects.length; i++) {
            const r = rects[i];
            if (x >= r.left && x < r.left + r.width && y >= r.top && y < r.top + r.height) {
                return r.key;
            }
        }
        return null;
    }

    // ------------------------------------------------------------ DOM driver

    function attach(container, opts) {
        const doc = container.ownerDocument;
        const win = doc.defaultView;
        const itemSelector = opts.itemSelector;
        const handleSelector = opts.handleSelector;
        const getId = opts.getId || function (el) { return el.dataset.sortId; };

        // drag state, from pickup until the snap animation finishes:
        // { item, ghost, pointerId, startOrder, x, y, grabDX, grabDY,
        //   layout: Map(item -> doc rect), raf, settling }
        let drag = null;

        function reducedMotion() {
            return !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
        }

        function items() {
            return Array.prototype.filter.call(container.children, function (el) {
                return el.matches(itemSelector);
            });
        }

        function currentOrder() {
            return items().map(getId);
        }

        function sameOrder(a, b) {
            return a.length === b.length && a.every(function (id, i) { return id === b[i]; });
        }

        // ---- animation helpers (Web Animations API, each with a timer fallback)

        function cancelSlides(els) {
            els.forEach(function (el) {
                if (!el.getAnimations) return;
                el.getAnimations().forEach(function (a) {
                    if (a.id === 'sort-slide') a.cancel();
                });
            });
        }

        /** Run `fn` once, when the animation finishes or after `ms`, whichever is first. */
        function whenDone(anim, ms, fn) {
            let done = false;
            function once() {
                if (done) return;
                done = true;
                fn();
            }
            if (anim && anim.finished) anim.finished.then(once, once);
            win.setTimeout(once, ms + 60);
        }

        /** Document-coordinate layout rects of the current items (no transforms). */
        function measureLayout() {
            const sx = win.scrollX || 0;
            const sy = win.scrollY || 0;
            const map = new Map();
            items().forEach(function (el) {
                const r = el.getBoundingClientRect();
                map.set(el, { left: r.left + sx, top: r.top + sy, width: r.width, height: r.height });
            });
            return map;
        }

        /**
         * FLIP: apply a DOM mutation and slide every tile from where it was
         * (visually — including any in-flight slide) to its new layout spot.
         */
        function moveWithSlide(mutate) {
            const els = items();
            const first = new Map();
            els.forEach(function (el) { first.set(el, el.getBoundingClientRect()); });
            cancelSlides(els);
            mutate();
            const layout = measureLayout();
            if (drag) drag.layout = layout;
            if (reducedMotion()) return;
            const sx = win.scrollX || 0;
            const sy = win.scrollY || 0;
            items().forEach(function (el) {
                const a = first.get(el);
                const b = layout.get(el);
                if (!a || !b || !el.animate) return;
                const dx = a.left - (b.left - sx);
                const dy = a.top - (b.top - sy);
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;
                const anim = el.animate(
                    [{ transform: 'translate(' + dx + 'px,' + dy + 'px)' }, { transform: 'none' }],
                    { duration: SLIDE_MS, easing: EASE });
                anim.id = 'sort-slide';
            });
        }

        // ---- ghost

        function makeGhost(item, rect) {
            const ghost = item.cloneNode(true);
            // No duplicate ids in the document. HTML ids (chart-<id>,
            // chart-plot-<id>, ...) are simply dropped. SVG ids must instead be
            // renamed and their url(#id) references rewritten: Plotly clips its
            // traces with clip-path:url(#id), and a duplicate id resolves to the
            // ORIGINAL's <clipPath> — which sits inside the placeholder, whose
            // content is visibility:hidden, and an invisible clip shape clips
            // everything away (the plot line vanished from the ghost).
            ghost.removeAttribute('id');
            uniquifySvgIds(ghost);
            ghost.classList.remove('sort-dragging', 'sort-placeholder');
            ghost.classList.add('sort-ghost');
            ghost.setAttribute('aria-hidden', 'true');
            const st = ghost.style;
            st.position = 'fixed';
            st.left = '0';
            st.top = '0';
            st.margin = '0';
            st.boxSizing = 'border-box';
            st.width = rect.width + 'px';
            st.height = rect.height + 'px';
            st.zIndex = '10000';
            st.pointerEvents = 'none';
            st.transition = 'none';
            st.transform = 'none';   // drop any hover transform the clone inherited
            doc.body.appendChild(ghost);
            return ghost;
        }

        // Position lives in the individual `translate` property (written on
        // every pointermove); the lift lives in `scale`. Two traps avoided:
        //  - an animation on the position property would override the inline
        //    value while it runs, so the ghost wouldn't follow the finger
        //    during the pickup animation — hence a separate property;
        //  - CSS composes translate -> scale -> transform, so a position in
        //    `transform` would itself get scaled (off by 3% of the distance
        //    from the viewport top). `translate` is outermost: never scaled.
        let ghostSeq = 0;
        const URL_ATTRS = ['clip-path', 'mask', 'filter', 'fill', 'stroke',
            'marker-start', 'marker-mid', 'marker-end', 'style'];

        function uniquifySvgIds(root) {
            const suffix = '--sortghost' + (++ghostSeq);
            const renamed = new Map();
            root.querySelectorAll('[id]').forEach(function (el) {
                if (!el.closest('svg')) {
                    el.removeAttribute('id');
                    return;
                }
                renamed.set(el.id, el.id + suffix);
                el.id = el.id + suffix;
            });
            if (renamed.size === 0) return;
            const rewrite = function (value) {
                return value.replace(/url\((['"]?)#([^'")]+)\1\)/g, function (m, q, id) {
                    return renamed.has(id) ? 'url(' + q + '#' + renamed.get(id) + q + ')' : m;
                });
            };
            root.querySelectorAll('*').forEach(function (el) {
                URL_ATTRS.forEach(function (attr) {
                    const v = el.getAttribute(attr);
                    if (v && v.indexOf('url(') !== -1) el.setAttribute(attr, rewrite(v));
                });
                ['href', 'xlink:href'].forEach(function (attr) {
                    const v = el.getAttribute(attr);
                    if (v && v.charAt(0) === '#' && renamed.has(v.slice(1))) {
                        el.setAttribute(attr, '#' + renamed.get(v.slice(1)));
                    }
                });
            });
        }

        function ghostPos(x, y) {
            return x + 'px ' + y + 'px';
        }

        function placeGhost() {
            drag.ghost.style.translate = ghostPos(drag.x - drag.grabDX, drag.y - drag.grabDY);
        }

        // ---- drag lifecycle

        function reposition() {
            if (!drag || drag.settling) return;
            const sx = win.scrollX || 0;
            const sy = win.scrollY || 0;
            const px = drag.x + sx;
            const py = drag.y + sy;
            const rects = [];
            drag.layout.forEach(function (r, el) {
                if (el !== drag.item) rects.push({ key: el, left: r.left, top: r.top, width: r.width, height: r.height });
            });
            const target = hitTest(rects, px, py);
            if (!target) return;
            const tr = drag.layout.get(target);
            const pr = drag.layout.get(drag.item);
            const after = shouldInsertAfter(tr, pr, px, py);
            if (after && target.nextElementSibling === drag.item) return;
            if (!after && target.previousElementSibling === drag.item) return;
            const item = drag.item;
            moveWithSlide(function () {
                if (after) target.after(item); else target.before(item);
            });
        }

        function autoScrollLoop() {
            if (!drag || drag.settling) return;
            const step = autoScrollStep(drag.y, win.innerHeight);
            if (step !== 0) {
                win.scrollBy(0, step);
                reposition();
            }
            drag.raf = win.requestAnimationFrame(autoScrollLoop);
        }

        function start(e, handle) {
            const item = handle.closest(itemSelector);
            if (!item || item.parentElement !== container) return;
            e.preventDefault();
            const rect = item.getBoundingClientRect();
            drag = {
                item: item,
                ghost: null,
                pointerId: e.pointerId,
                startOrder: currentOrder(),
                x: e.clientX,
                y: e.clientY,
                grabDX: e.clientX - rect.left,
                grabDY: e.clientY - rect.top,
                layout: measureLayout(),
                raf: null,
                settling: false,
            };
            try { handle.setPointerCapture(e.pointerId); } catch (_) { /* synthetic pointer */ }

            drag.ghost = makeGhost(item, rect);
            item.classList.add('sort-dragging', 'sort-placeholder');
            container.classList.add('sort-active');
            doc.body.classList.add('sort-in-progress');

            // lift: grow in place from the tile's exact spot to the raised scale
            drag.ghost.style.translate = ghostPos(rect.left, rect.top);
            drag.ghost.style.scale = String(LIFT_SCALE);
            if (!reducedMotion() && drag.ghost.animate) {
                drag.ghost.animate([{ scale: '1' }, { scale: String(LIFT_SCALE) }],
                    { duration: LIFT_MS, easing: EASE });
            }

            win.addEventListener('pointermove', onMove);
            win.addEventListener('pointerup', onUp);
            win.addEventListener('pointercancel', onCancel);
            win.addEventListener('keydown', onKeyDuringDrag);
            drag.raf = win.requestAnimationFrame(autoScrollLoop);
            if (opts.onDragStart) opts.onDragStart(getId(item));
        }

        function finish(commit) {
            if (!drag || drag.settling) return;
            const d = drag;
            d.settling = true;
            if (d.raf != null) win.cancelAnimationFrame(d.raf);
            win.removeEventListener('pointermove', onMove);
            win.removeEventListener('pointerup', onUp);
            win.removeEventListener('pointercancel', onCancel);
            win.removeEventListener('keydown', onKeyDuringDrag);

            if (!commit) {
                // slide everything back where it started
                moveWithSlide(function () {
                    const byId = new Map(items().map(function (el) { return [getId(el), el]; }));
                    d.startOrder.forEach(function (id) {
                        const el = byId.get(id);
                        if (el) container.appendChild(el);
                    });
                });
            }

            // snap: glide the ghost onto the placeholder's resting spot
            const slot = (d.layout && d.layout.get(d.item)) || null;
            const sx = win.scrollX || 0;
            const sy = win.scrollY || 0;
            const r = slot
                ? { left: slot.left - sx, top: slot.top - sy }
                : d.item.getBoundingClientRect();
            const target = ghostPos(r.left, r.top);
            let anim = null;
            if (!reducedMotion() && d.ghost.animate) {
                d.ghost.getAnimations().forEach(function (a) { a.cancel(); });
                anim = d.ghost.animate(
                    [{ translate: d.ghost.style.translate, scale: d.ghost.style.scale || '1' },
                     { translate: target, scale: '1' }],
                    { duration: SNAP_MS, easing: EASE, fill: 'forwards' });
            }
            d.ghost.style.translate = target;
            d.ghost.style.scale = '1';
            whenDone(anim, anim ? SNAP_MS : 0, function () { settle(d, commit); });
        }

        function settle(d, commit) {
            d.ghost.remove();
            d.item.classList.remove('sort-dragging', 'sort-placeholder');
            container.classList.remove('sort-active');
            doc.body.classList.remove('sort-in-progress');
            drag = null;
            const order = currentOrder();
            if (commit && !sameOrder(order, d.startOrder) && opts.onReorder) {
                opts.onReorder(order);
            }
            if (opts.onDragEnd) opts.onDragEnd();
        }

        function onMove(e) {
            if (!drag || drag.settling || e.pointerId !== drag.pointerId) return;
            e.preventDefault();
            drag.x = e.clientX;
            drag.y = e.clientY;
            placeGhost();
            reposition();
        }

        function onUp(e) {
            if (drag && e.pointerId === drag.pointerId) finish(true);
        }

        function onCancel(e) {
            if (drag && e.pointerId === drag.pointerId) finish(false);
        }

        function onKeyDuringDrag(e) {
            if (e.key === 'Escape') finish(false);
        }

        function onPointerDown(e) {
            if (drag) return;
            if (e.pointerType === 'mouse' && e.button !== 0) return;
            const handle = e.target.closest && e.target.closest(handleSelector);
            if (!handle || !container.contains(handle)) return;
            start(e, handle);
        }

        function onKeyDown(e) {
            if (drag) return;
            const handle = e.target.closest && e.target.closest(handleSelector);
            if (!handle || !container.contains(handle)) return;
            const item = handle.closest(itemSelector);
            if (!item || item.parentElement !== container) return;
            const list = items();
            const i = list.indexOf(item);
            let mutate = null;
            if ((e.key === 'ArrowUp' || e.key === 'ArrowLeft') && i > 0) {
                mutate = function () { list[i - 1].before(item); };
            } else if ((e.key === 'ArrowDown' || e.key === 'ArrowRight') && i < list.length - 1) {
                mutate = function () { list[i + 1].after(item); };
            }
            if (mutate) {
                e.preventDefault();
                moveWithSlide(mutate);
                handle.focus();
                if (opts.onReorder) opts.onReorder(currentOrder());
            }
        }

        container.addEventListener('pointerdown', onPointerDown);
        container.addEventListener('keydown', onKeyDown);

        return {
            isDragging: function () { return drag != null; },
            order: currentOrder,
            cancel: function () { finish(false); },
            destroy: function () {
                finish(false);
                container.removeEventListener('pointerdown', onPointerDown);
                container.removeEventListener('keydown', onKeyDown);
            },
        };
    }

    return {
        attach: attach,
        utils: {
            shouldInsertAfter: shouldInsertAfter,
            reorderSubset: reorderSubset,
            mergeSelectionOrder: mergeSelectionOrder,
            sortByOrder: sortByOrder,
            autoScrollStep: autoScrollStep,
            hitTest: hitTest,
        },
        constants: {
            AUTOSCROLL_EDGE_PX: AUTOSCROLL_EDGE_PX,
            AUTOSCROLL_MAX_STEP: AUTOSCROLL_MAX_STEP,
            SLIDE_MS: SLIDE_MS,
            SNAP_MS: SNAP_MS,
        },
    };
});
