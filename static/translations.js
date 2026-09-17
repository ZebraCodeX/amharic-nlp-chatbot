/*!
 * translations.js — the Amharic ⇄ English review UI.
 *
 * Lists Amharic words with their current English translation and lets users
 * approve (✓) or correct (✎) it. Every correction is persisted server-side
 * through /api/translations/verify and immediately improves the translator,
 * because stored corrections always win in translator.best_translate().
 */
(function () {
    'use strict';

    var state = { q: '', status: 'review', offset: 0, limit: 50, total: 0, loading: false };

    var STATUS = {
        suggested:    { label: 'ማረጋገጫ ይፈልጋል', cls: 'st-review' },
        verified:     { label: '✓ የተረጋገጠ', cls: 'st-verified' },
        corrected:    { label: '✎ የተስተካከለ', cls: 'st-corrected' },
        untranslated: { label: 'ትርጉም የለውም', cls: 'st-none' }
    };

    var FILTERS = [
        ['review', 'ማረጋገጫ'],
        ['untranslated', 'ያልተተረጎሙ'],
        ['verified', 'የተረጋገጡ/የተስተካከሉ'],
        ['all', 'ሁሉም']
    ];

    var listEl, statsEl, moreBtn, searchEl, filtersEl, toastEl;

    function $(id) { return document.getElementById(id); }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"]/g, function (m) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m];
        });
    }

    function toast(msg, ok) {
        if (!toastEl) return;
        toastEl.textContent = msg;
        toastEl.className = 'toast show' + (ok ? ' ok' : ' err');
        clearTimeout(toastEl._t);
        toastEl._t = setTimeout(function () { toastEl.className = 'toast'; }, 2600);
    }

    /* ---------------- stats ---------------- */
    function loadStats() {
        fetch('/api/translations/stats').then(function (r) { return r.json(); }).then(function (d) {
            if (!statsEl) return;
            var cells = [
                ['ጠቅላላ', d.total, ''],
                ['ማረጋገጫ የሚፈልጉ', d.review, 'st-review'],
                ['ያልተተረጎሙ', d.untranslated, 'st-none'],
                ['የተረጋገጡ', d.verified, 'st-verified'],
                ['የተስተካከሉ', d.corrected, 'st-corrected']
            ];
            statsEl.innerHTML = cells.map(function (c) {
                return '<div class="stat ' + c[2] + '"><b>' + (c[1] | 0) + '</b><span>' + c[0] + '</span></div>';
            }).join('');
        }).catch(function () {});
    }

    /* ---------------- list ---------------- */
    function loadList(append) {
        if (state.loading) return;
        state.loading = true;
        if (!append) { state.offset = 0; listEl.innerHTML = '<div class="loading">⏳ በመጫን ላይ…</div>'; }
        var url = '/api/translations?status=' + encodeURIComponent(state.status) +
            '&q=' + encodeURIComponent(state.q) +
            '&limit=' + state.limit + '&offset=' + state.offset;
        fetch(url).then(function (r) { return r.json(); }).then(function (d) {
            state.loading = false;
            state.total = d.total || 0;
            if (!append) listEl.innerHTML = '';
            var items = d.items || [];
            if (!append && !items.length) {
                listEl.innerHTML = '<div class="empty">ምንም አልተገኘም። ሌላ ማጣሪያ ሞክር ወይም ፈልግ።</div>';
            }
            var frag = document.createDocumentFragment();
            items.forEach(function (it) { frag.appendChild(renderRow(it)); });
            listEl.appendChild(frag);
            state.offset += items.length;
            maybeMore();
        }).catch(function () {
            state.loading = false;
            listEl.innerHTML = '<div class="empty">ስህተት። እንደገና ሞክር።</div>';
        });
    }

    function maybeMore() {
        if (!moreBtn) return;
        if (state.offset < state.total) {
            moreBtn.classList.remove('hidden');
            moreBtn.textContent = 'ተጨማሪ አሳይ (' + state.offset + '/' + state.total + ')';
        } else {
            moreBtn.classList.add('hidden');
        }
    }

    function renderRow(it) {
        var row = document.createElement('div');
        row.className = 'row';
        var meta = STATUS[it.status] || STATUS.suggested;

        var am = document.createElement('div');
        am.className = 'am';
        am.textContent = it.am;

        var mid = document.createElement('div');
        mid.className = 'mid';
        var input = document.createElement('input');
        input.className = 'en-input';
        input.type = 'text';
        input.dir = 'ltr';
        input.value = it.en || '';
        input.placeholder = 'English translation…';
        var badge = document.createElement('span');
        badge.className = 'badge ' + meta.cls;
        badge.textContent = meta.label + (it.endorsed ? ' · ' + it.endorsed + '✓' : '');
        mid.appendChild(input);
        mid.appendChild(badge);

        var actions = document.createElement('div');
        actions.className = 'actions';
        var ok = document.createElement('button');
        ok.className = 'btn ok';
        ok.textContent = '✓ ትክክል';
        ok.title = 'Approve the suggested translation';
        var fix = document.createElement('button');
        fix.className = 'btn fix';
        fix.textContent = '✎ አስቀምጥ';
        fix.title = 'Save your corrected translation';

        function save(isCorrection) {
            var value = (input.value || '').trim();
            if (!value) { toast('እባክህ ትርጉም ጻፍ', false); input.focus(); return; }
            var previous = (it.en || '').trim();
            ok.disabled = fix.disabled = true;
            fetch('/api/translations/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: it.am, src: 'am', dst: 'en',
                    translation: previous || value,
                    correct: value
                })
            }).then(function (r) { return r.json(); }).then(function (d) {
                ok.disabled = fix.disabled = false;
                if (d && d.ok) {
                    it.en = d.corrected || value;
                    it.status = (isCorrection && value !== previous) ? 'corrected' : 'verified';
                    it.endorsed = d.endorsed || 0;
                    var m = STATUS[it.status] || STATUS.verified;
                    badge.className = 'badge ' + m.cls;
                    badge.textContent = m.label + (it.endorsed ? ' · ' + it.endorsed + '✓' : '');
                    row.classList.add('saved');
                    toast('✓ ተቀምጧል — የመላው መተግበሪያ ትርጉም ተሻሽሏል', true);
                    loadStats();
                } else {
                    toast('ተቀምጦ አልተቻለም', false);
                }
            }).catch(function () {
                ok.disabled = fix.disabled = false;
                toast('የኔትወርክ ስህተት', false);
            });
        }

        ok.addEventListener('click', function () { save(false); });
        fix.addEventListener('click', function () { save(true); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); save(false); }
        });

        actions.appendChild(ok);
        actions.appendChild(fix);

        row.appendChild(am);
        row.appendChild(mid);
        row.appendChild(actions);
        return row;
    }

    /* ---------------- toolbar ---------------- */
    function buildFilters() {
        if (!filtersEl) return;
        var frag = document.createDocumentFragment();
        FILTERS.forEach(function (f) {
            var b = document.createElement('button');
            b.className = 'filter' + (state.status === f[0] ? ' active' : '');
            b.textContent = f[1];
            b.dataset.status = f[0];
            b.addEventListener('click', function () {
                state.status = f[0];
                Array.prototype.forEach.call(filtersEl.children, function (c) {
                    c.classList.toggle('active', c.dataset.status === state.status);
                });
                loadList(false);
            });
            frag.appendChild(b);
        });
        filtersEl.appendChild(frag);
    }

    function init() {
        listEl = $('list');
        statsEl = $('stats');
        moreBtn = $('moreBtn');
        searchEl = $('search');
        filtersEl = $('filters');
        toastEl = $('toast');

        buildFilters();
        loadStats();
        loadList(false);

        var debounce;
        searchEl.addEventListener('input', function () {
            clearTimeout(debounce);
            debounce = setTimeout(function () {
                state.q = searchEl.value.trim();
                loadList(false);
            }, 250);
        });
        moreBtn.addEventListener('click', function () { loadList(true); });

        var kbd = null;
        var toggle = $('kbdToggle');
        if (toggle && window.AmharicKeyboard) {
            kbd = new window.AmharicKeyboard({
                container: $('kbd'),
                input: searchEl,
                phonetic: true,
                storageKey: 'hisar.phonetic',
                placeholder: 'የአማርኛ ቃል ጻፍ…'
            });
            toggle.addEventListener('click', function () {
                kbd.toggle();
                toggle.classList.toggle('active', kbd.isOpen());
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
