/*!
 * amharic-keyboard.js — self-contained Amharic on-screen keyboard
 * with spelling-invariant word prediction.
 *
 * Standalone, dependency-free web component. It owns everything typing-related:
 *   - a Google Keyboard (Gboard) style layout: 31 base letters, tap a key to
 *     reveal all 7 vowel orders (ሀ ሁ ሂ ሃ ሄ ህ ሆ …), symbols + Amharic-numeral page,
 *     backspace (long-press = clear), space, Enter;
 *   - word prediction strip: as you type letters it keeps searching a spelling-
 *     dictionary and suggests correctly-spelled words; when a word ends it offers
 *     Bible-trained *next-word* hints (2-gram/3-gram) for the sentence;
 *   - optional server-side type-ahead (`suggestUrl → /api/suggest`): full
 *     sentence completions from the trained sentence bank, then closest words
 *     and next-word hints for everything — the "smart type-ahead" mode;
 *   - a fold() matcher that is vowel-order and homophone insensitive
 *     (ሀ/ሐ/ኀ→ሀ, ሠ→ሰ, ኣ→አ, ፀ→ጸ), so this classically-correct Amharic still matches.
 *
 * Usage:
 *   <link rel="stylesheet" href="amharic-keyboard.css">
 *   <script src="amharic-keyboard.js"></script>
 *
 *   const kbd = new AmharicKeyboard({
 *       container: document.getElementById('kbd'),
 *       input:     document.getElementById('textField'),
 *       dictUrl:   '/api/words',     // optional {words:[{w,n}]}
 *       ngramUrl:  '/api/ngram',     // optional {bigram,trigram,...}
 *       suggestUrl:'/api/suggest',   // optional type-ahead {words,next,sentences}
 *       onSubmit:  (text) => { ... },
 *       translate: { enabled: () => bool, fetch: (text) => Promise<string> },
 *   });
 *   kbd.toggle();            // open/close
 *   kbd.refresh();           // re-render after external input changes
 *   kbd.destroy();           // teardown
 *
 * The keyboard is a reusable app: give it any input element and dictionary
 * endpoint and other applications can use exact the same typing experience.
 */
(function (root) {
    'use strict';

    /* ---------- Amharic letters (Ethiopian alphabet order) ---------- */
    var LETTERS = ['ሀ','ለ','ሐ','መ','ሠ','ረ','ሰ','ሸ','ቀ','በ','ተ','ቸ','ኀ','ነ','ኘ','አ','ከ','ኸ','ወ','ዐ','ዘ','ዠ','የ','ደ','ጀ','ገ','ጠ','ጨ','ጰ','ጸ','ፀ'];
    var ORDER_LABELS = ['e','u','i','a','ie','','o'];
    var SYMS = ['፩','፪','፫','፬','፭','፮','፯','፰','፱','፲','1','2','3','4','5','6','7','8','9','0','@','#','$','%','&','*','+','-','=','/','\\',':',';','"',"'",',','.','[',']','{','}'];
    var TOK_RE = /[\s\u1362\u1363\u1365\u1361]+/;

    /* ---------- Werket-style phonetic composition (Latin → Ge'ez) ----------
       Ported from the Werket editor's Fidel keyboard: type `selam` and get
       `ሰላም`. Consonant families are composed with e,u,i,a,ie,silent,o while
       uppercase keys select the emphatic families (GFF/Keyman convention). */
    var PHONETIC = {
        h:'ሀ', H:'ሐ', l:'ለ', m:'መ', s:'ሰ', r:'ረ', S:'ሠ',
        b:'በ', t:'ተ', c:'ቸ', C:'ጨ', q:'ቀ', k:'ከ', x:'ኀ',
        n:'ነ', N:'ኘ', a:'አ', w:'ወ', z:'ዘ', Z:'ዠ', y:'የ',
        d:'ደ', j:'ጀ', g:'ገ', T:'ጠ', p:'ፐ', f:'ፈ', v:'ቨ',
        D:'ፀ', K:'ኸ', E:'ዐ', P:'ጰ', F:'ፈ', V:'ቨ'
    };
    var DIGRAPHS = { sh:'ሸ', ch:'ቸ', nh:'ኘ', ts:'ጸ', ph:'ፈ' };
    var VOWELS = { e:0, u:1, i:2, a:3, ie:4, ee:4, '':5, silent:5, o:6 };
    var QWERTY = [
        ['q','w','e','r','t','y','u','i','o','p'],
        ['a','s','d','f','g','h','j','k','l'],
        ['z','x','c','v','b','n','m']
    ];

    var charFor = function (letter, order) {
        var base = letter.codePointAt(0);
        var o = (order === undefined || order === null) ? 0 : parseInt(order, 10);
        if (isNaN(o)) o = 0;
        return String.fromCodePoint(base + Math.max(0, Math.min(6, o)));
    };

    var ordersFor = function (letter) {
        var base = letter.codePointAt(0), out = [];
        for (var o = 0; o < 7; o++) out.push(String.fromCodePoint(base + o));
        return out;
    };

    /* Compose a raw Latin string into Ethiopic (the Werket `compose()`). */
    var compose = function (raw) {
        var out = '', i = 0, len = (raw || '').length;
        while (i < len) {
            var family = null, pair = raw.slice(i, i + 2).toLowerCase();
            if (pair in DIGRAPHS) { family = DIGRAPHS[pair]; i += 2; }
            else if (raw[i] in PHONETIC) { family = PHONETIC[raw[i]]; i++; }
            if (!family) { out += raw[i]; i++; continue; }
            var next = '', two = raw.slice(i, i + 2).toLowerCase(), one = (raw[i] || '').toLowerCase();
            if (two === 'ie' || two === 'ee') { next = two; i += 2; }
            else if (one in VOWELS) { next = one; i += 1; }
            out += charFor(family, VOWELS[next]);
        }
        return out;
    };

    function isLatin(ch) {
        return ch.length === 1 && /[a-zA-Z]/.test(ch);
    }

    /* fold(): spelling-invariant key — collapses vowel orders to their base
       letter and maps homophones, mirroring the classic AmharicNormalizer. */
    var FOLD = (function () {
        var m = {};
        for (var i = 0; i < LETTERS.length; i++) {
            var L = LETTERS[i], base = L.codePointAt(0);
            for (var o = 0; o < 7; o++) m[String.fromCodePoint(base + o)] = L;
        }
        var ho = {
            'ሐ':'ሀ','ሑ':'ሁ','ሒ':'ሂ','ሓ':'ሃ','ሔ':'ሄ','ሕ':'ህ','ሖ':'ሆ',
            'ኀ':'ሀ','ኁ':'ሁ','ኂ':'ሂ','ኃ':'ሃ','ኄ':'ሄ','ኅ':'ህ','ኆ':'ሆ',
            'ሠ':'ሰ','ሡ':'ሱ','ሢ':'ሲ','ሣ':'ሳ','ሤ':'ሴ','ሥ':'ስ','ሦ':'ሶ',
            'ኣ':'አ','ፀ':'ጸ','ፁ':'ጹ','ፂ':'ጺ','ፃ':'ጻ','ፄ':'ጼ','ፅ':'ጽ','ፆ':'ጾ'
        };
        for (var k in ho) m[k] = ho[k];
        return m;
    })();

    function fold(s) {
        var out = '';
        for (var i = 0; i < s.length; i++) out += (FOLD[s[i]] || s[i]);
        return out;
    }

    function AmharicKeyboard(options) {
        options = options || {};
        if (!options.container || !options.input) {
            throw new Error('AmharicKeyboard: `container` and `input` are required.');
        }
        this.container = options.container;
        this.input = options.input;
        this.dictUrl = options.dictUrl || null;
        this.ngramUrl = options.ngramUrl || null;
        this.suggestUrl = options.suggestUrl || null;
        this.miniWords = options.miniWords ||
            ['ሰላም','እንዴት','ነህ','አመሰግናለሁ','እባክህ','ምንድን','ነው','ፍቅር','ደስታ','ቡና','ቴክኖሎጂ','አስታውስ'];
        this.onSubmit = options.onSubmit || null;
        this.onInput = options.onInput || null;
        this.translate = options.translate || null;
        this.placeholder = options.placeholder || 'አስተካክል ጠቃሚ ቃላት…';

        this.DICT = options.words || null;
        this.NGRAM = null;
        this.SUGGEST = null;        // last /api/suggest response
        this._dictFailed = false;
        this._ngramFailed = false;
        this._suggestFailed = false;
        this.showSymbols = false;
        this._host = null;          // static DOM (rebuilt only if needed)
        this._entries = {};         // {suggest:, translateBar:}
        this._loadedData = false;

        // Werket-style phonetic typing: Latin keys compose to Ge'ez.
        this.phonetic = !!options.phonetic;
        this.storageKey = options.storageKey || null;
        if (this.storageKey && !options.phonetic) {
            try {
                var saved = root.localStorage && root.localStorage.getItem(this.storageKey);
                if (saved !== null) this.phonetic = saved === '1';
            } catch (e) { /* no storage — keep the option default */ }
        }
        this._buf = '';             // pending Latin buffer
        this._composed = '';        // what the buffer currently renders to in the input

        this._bindEvents();
        if (this.DICT || this._loadData()) { /* data paths below */ }
        this._build();
    }

    /* ============================ public API ============================ */
    AmharicKeyboard.prototype.isOpen = function () {
        return this._host && !this._host.classList.contains('akb-hidden');
    };
    AmharicKeyboard.prototype.open = function () {
        this._build();
        if (this._host) this._host.classList.remove('akb-hidden');
        this._suggestTick();
        this.input.focus();
        return this;
    };
    AmharicKeyboard.prototype.close = function () {
        if (this._host) this._host.classList.add('akb-hidden');
        return this;
    };
    AmharicKeyboard.prototype.toggle = function () {
        return this.isOpen() ? this.close() : this.open();
    };
    AmharicKeyboard.prototype.refresh = function () {
        if (this.isOpen()) this._render();
        return this;
    };
    AmharicKeyboard.prototype.destroy = function () {
        if (this._host) { this.container.removeChild(this._host); }
        this._host = null;
        this.input.removeEventListener('input', this._onInputBound || null);
        return this;
    };
    AmharicKeyboard.prototype.setWords = function (list) { this.DICT = list; this.refresh(); };
    AmharicKeyboard.prototype.setNgram = function (model) { this.NGRAM = model; this.refresh(); };
    AmharicKeyboard.prototype.value = function () { return this.input.value || ''; };

    /* ============================ internals ============================ */
    AmharicKeyboard.prototype._bindEvents = function () {
        var self = this;
        this._onInputBound = function () { self.refresh(); self._translateTick(); self._suggestTick(); };
        this.input.addEventListener('input', this._onInputBound);
        this._docDown = function (e) {
            if (!e.target.closest('.akb-pop') && !e.target.closest('.akb-key.char')) self._hideOrders();
        };
        document.addEventListener('pointerdown', this._docDown);
        document.addEventListener('click', this._docDown);
        this._phoneticKeyHandler = function (e) { self._onPhoneticKey(e); };
        this.input.addEventListener('keydown', this._phoneticKeyHandler);
    };

    /* ---------- phonetic typing: physical + on-screen Latin keys ---------- */
    AmharicKeyboard.prototype.setPhonetic = function (on) {
        this.phonetic = !!on;
        if (!this.phonetic) this._commit();
        if (this.storageKey) {
            try { root.localStorage && root.localStorage.setItem(this.storageKey, this.phonetic ? '1' : '0'); }
            catch (e) { /* ignore */ }
        }
        if (this._host) this._host.dataset.page = '';   // force a full rebuild
        this._render();
        if (this.phonetic) this.input.focus();
        return this;
    };
    AmharicKeyboard.prototype.togglePhonetic = function () {
        return this.setPhonetic(!this.phonetic);
    };

    AmharicKeyboard.prototype._onPhoneticKey = function (e) {
        if (!this.phonetic) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        var k = e.key;
        if (k === 'Backspace') {
            if (this._buf) { e.preventDefault(); this._buf = this._buf.slice(0, -1); this._recompose(); }
            return;
        }
        if (k === ' ' || k === 'Enter' || k === 'Tab') { this._commit(); return; }
        if (isLatin(k)) { e.preventDefault(); this._phoneticType(k); }
    };

    /* Insert a Latin letter (from QWERTY tap or physical key), buffer it and
       keep the composed Ge'ez preview in the input. */
    AmharicKeyboard.prototype._phoneticType = function (ch) {
        if (!this.phonetic) { this._insert(ch); return; }
        this._buf += ch;
        this._recompose();
        this._suggestTick();
    };

    /* Replace the previously-composed region with compose(current buffer). */
    AmharicKeyboard.prototype._recompose = function () {
        var v = this._value();
        var caret = (typeof this.input.selectionStart === 'number')
            ? this.input.selectionStart : v.length;
        var back = this._composed.length;
        var start = Math.max(0, caret - back);
        var next = compose(this._buf);
        this.input.value = v.slice(0, start) + next + v.slice(caret);
        var newCaret = start + next.length;
        if (this.input.setSelectionRange) this.input.setSelectionRange(newCaret, newCaret);
        this._composed = next;
        this.onInput && this.onInput(this._value(), 'phonetic');
        this.refresh();
        this._translateTick();
    };

    /* Keep what is on screen, forget the raw buffer. */
    AmharicKeyboard.prototype._commit = function () {
        this._buf = '';
        this._composed = '';
    };

    AmharicKeyboard.prototype._loadData = function () {
        var self = this, pending = 0;
        function done() {
            pending--;
            if (pending === 0) { self._loadedData = true; self.refresh(); }
        }
        if (this.dictUrl && !this.DICT && !this._dictFailed) {
            pending++;
            fetch(this.dictUrl).then(function (r) { return r.json(); }).then(function (d) {
                self.DICT = Array.isArray(d.words) ? d.words : [];
                done();
            }).catch(function () { self._dictFailed = true; done(); });
        }
        if (this.ngramUrl && !this.NGRAM && !this._ngramFailed) {
            pending++;
            fetch(this.ngramUrl).then(function (r) { return r.json(); }).then(function (d) {
                self.NGRAM = d;
                done();
            }).catch(function () { self._ngramFailed = true; done(); });
        }
        if (pending === 0) this._loadedData = true;
        return pending > 0;
    };

    AmharicKeyboard.prototype._value = function () { return this.input.value || ''; };

    AmharicKeyboard.prototype._setValue = function (v) {
        this._commit();
        this.input.value = v;
        this.input.focus();
        this.onInput && this.onInput(v, 'edit');
        this._render();
        this._translateTick();
    };

    AmharicKeyboard.prototype._insert = function (ch) {
        if (this.phonetic && this._buf) this._commit();
        var pos = this.input.selectionStart || this._value().length;
        var v = this._value();
        this.input.value = v.slice(0, pos) + ch + v.slice(pos);
        this.input.focus();
        this.input.setSelectionRange(pos + ch.length, pos + ch.length);
        this.onInput && this.onInput(this._value(), 'key');
        this._render();
        this._translateTick();
    };

    AmharicKeyboard.prototype._backspace = function () {
        if (this.phonetic && this._buf) {
            this._buf = this._buf.slice(0, -1);
            this._recompose();
            return;
        }
        var pos = this.input.selectionStart || this._value().length;
        if (pos > 0) {
            var v = this._value();
            this.input.value = v.slice(0, pos - 1) + v.slice(pos);
            this.input.setSelectionRange(pos - 1, pos - 1);
        }
        this._render();
        this._translateTick();
    };

    AmharicKeyboard.prototype._clear = function () {
        this._commit();
        this.input.value = '';
        this.input.focus();
        this._render();
        this._translateTick();
    };

    /* ----- server-side type-ahead (sentence completion + closest words) ----- */
    AmharicKeyboard.prototype._suggestTick = function () {
        if (!this.suggestUrl || this._suggestFailed) return;
        var self = this;
        clearTimeout(this._sugTimer);
        this._sugTimer = setTimeout(function () { self._fetchSuggest(); }, 200);
    };

    AmharicKeyboard.prototype._fetchSuggest = function () {
        if (!this.suggestUrl) return;
        var self = this, q = encodeURIComponent((this._value() || '').trim());
        fetch(this.suggestUrl + '?text=' + q).then(function (r) { return r.json(); }).then(function (d) {
            self.SUGGEST = d || null;
            if (self.isOpen()) self._renderSuggest();
        }).catch(function () { self._suggestFailed = true; self.SUGGEST = null; });
    };

    AmharicKeyboard.prototype._suggestChips = function () {
        // sentence completions take priority (fun, trained), words/next fill in
        var S = this.SUGGEST, out = [];
        if (S && Array.isArray(S.sentences)) {
            S.sentences.slice(0, 2).forEach(function (t) { out.push({ w: t, type: 'sent' }); });
        }
        var room = 4 - out.length;
        var sl = out.length;
        if (room > 0 && S && Array.isArray(S.next) && S.next.length && !this._currentToken()) {
            S.next.slice(0, room).forEach(function (w) { out.push({ w: w[0], type: 'next' }); });
        }
        room = 4 - out.length;
        if (room > 0 && S && Array.isArray(S.words)) {
            S.words.slice(0, room).forEach(function (w) { out.push({ w: w[0], type: 'word' }); });
            room = 4 - out.length;
        }
        if (room > 0) {
            this._dictSuggest(room).forEach(function (c) { out.push({ w: c.w, type: 'word' }); });
        }
        return out.slice(0, 4);
    };

    /* ----- word prediction ----- */
    AmharicKeyboard.prototype._currentToken = function () {
        return this._value().split(TOK_RE).pop() || '';
    };

    AmharicKeyboard.prototype._dictSuggest = function (n) {
        var cur = this._currentToken();
        if (!cur) return [];
        var fc = fold(cur);
        if (!fc || !this.DICT) return [];
        var out = [];
        this.DICT.forEach(function (e) {
            var fw = fold(e.w);
            if (fw.length > fc.length && fw.indexOf(fc) === 0) out.push({w: e.w, n: e.n || 1, len: e.w.length});
        });
        out.sort(function (a, b) { return (a.len - b.len) || (b.n - a.n); });
        return out.slice(0, n);
    };

    AmharicKeyboard.prototype._nextWords = function (n) {
        var val = this._value().trim();
        if (!val || !this.NGRAM) return [];
        var toks = val.split(TOK_RE).filter(Boolean);
        var w2 = toks[toks.length - 1], w1 = toks.length > 1 ? toks[toks.length - 2] : '';
        if (!w2) return [];
        var tri = (this.NGRAM.trigram || {})[w2 + '|' + w1];
        var bi = (this.NGRAM.bigram || {})[w2] || {};
        var cnt = {};
        if (tri) for (var w in tri) cnt[w] = (cnt[w] || 0) + tri[w] * 3;
        for (var x in bi) cnt[x] = (cnt[x] || 0) + bi[x];
        return Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; }).slice(0, n);
    };

    /* ----- build/refresh the DOM ----- */
    AmharicKeyboard.prototype._build = function () {
        if (this._host) return;               // static shell already present
        var host = document.createElement('div');
        host.className = 'akb akb-hidden';
        this._host = host;
        this.container.appendChild(host);
        this._render();
    };

    AmharicKeyboard.prototype._render = function () {
        var host = this._host;
        if (!host) return;
        var sym = this.showSymbols;
        if (host.dataset.page === (sym ? 'S' : 'L')) { this._renderSuggest(); this._translateTick(); return; }
        host.dataset.page = sym ? 'S' : 'L';
        host.innerHTML = '';

        var entries = this._entries = {};

        if (this.translate) {
            var bar = document.createElement('div');
            bar.className = 'akb-tr-bar hidden';
            host.appendChild(bar);
            entries.translateBar = bar;
        }

        var sug = document.createElement('div');
        sug.className = 'akb-suggest';
        var sp = document.createElement('span');
        sp.className = 'akb-sp';
        sp.textContent = this.placeholder;
        sug.appendChild(sp);
        host.appendChild(sug);
        entries.suggest = sug;

        var rows = document.createElement('div');
        rows.className = 'akb-rows';

        var self = this;
        if (sym) {
            for (var i = 0; i < SYMS.length; i += 9) {
                var srow = document.createElement('div'); srow.className = 'akb-row';
                SYMS.slice(i, i + 9).forEach(function (c) {
                    var b = document.createElement('button');
                    b.className = 'akb-key sym'; b.textContent = c;
                    b.addEventListener('click', function () { self._insert(c); });
                    b.addEventListener('touchstart', function (e) { e.preventDefault(); });
                    srow.appendChild(b);
                });
                rows.appendChild(srow);
            }
            rows.appendChild(this._fnRow([
                { label: 'ABC', delta: function () { self.showSymbols = false; self._render(); } },
                { label: 'SPACE', cls: 'space', tap: function () { self._insert(' '); } },
                { label: '⌫', cls: 'fn clear', backspace: true },
                { label: '⏎', enter: true, delta: null }
            ]));
        } else if (this.phonetic) {
            // Werket-style phonetic page: tap Latin keys, they compose to Ge'ez.
            QWERTY.forEach(function (group) {
                var row = document.createElement('div'); row.className = 'akb-row';
                group.forEach(function (c) {
                    var b = document.createElement('button');
                    b.className = 'akb-key latin';
                    b.textContent = c;
                    b.title = charFor(PHONETIC[c] || PHONETIC[c.toUpperCase()] || 'ሀ', 0);
                    b.addEventListener('click', function () { self._phoneticType(c); });
                    row.appendChild(b);
                });
                rows.appendChild(row);
            });
            rows.appendChild(this._fnRow([
                { label: '?123', delta: function () { self.showSymbols = true; self._commit(); self._render(); } },
                { label: 'SPACE', cls: 'space', tap: function () { self._commit(); self._insert(' '); } },
                { label: '⌫', cls: 'fn clear', backspace: true },
                { label: '⏎', enter: true, delta: null }
            ]));
        } else {
            var lrow = [LETTERS.slice(0, 10), LETTERS.slice(10, 20), LETTERS.slice(20)];
            lrow.forEach(function (group) {
                var row = document.createElement('div'); row.className = 'akb-row';
                group.forEach(function (letter) {
                    var b = document.createElement('button');
                    b.className = 'akb-key char';
                    b.textContent = charFor(letter, 0);
                    b.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); self._showOrders(b, letter); });
                    row.appendChild(b);
                });
                rows.appendChild(row);
            });
            rows.appendChild(this._fnRow([
                { label: '?123', delta: function () { self.showSymbols = true; self._hideOrders(); self._render(); } },
                { label: '፣', delta: null, tap: function () { self._insert('፣'); } },
                { label: 'SPACE', cls: 'space', tap: function () { self._insert(' '); } },
                { label: '።', delta: null, tap: function () { self._insert('።'); } },
                { label: '⌫', cls: 'fn clear', backspace: true },
                { label: '⏎', enter: true, delta: null }
            ]));
        }
        host.appendChild(rows);
        host.appendChild(this._modeBar());
        this._renderSuggest();
        this._translateTick();
    };

    /* Phonetic mode switch (Latin → Ge'ez), reachable from every page. */
    AmharicKeyboard.prototype._modeBar = function () {
        var self = this;
        var bar = document.createElement('div');
        bar.className = 'akb-mode-bar';
        var b = document.createElement('button');
        b.className = 'akb-mode-toggle' + (this.phonetic ? ' on' : '');
        b.textContent = (this.phonetic ? '✓ ' : '') + 'ላቲን → ግዕዝ · Phonetic ' +
            (this.phonetic ? 'ON' : 'OFF');
        b.title = "Type Latin like 'selam' and it becomes ሰላም";
        b.addEventListener('click', function () { self.togglePhonetic(); });
        bar.appendChild(b);
        return bar;
    };

    AmharicKeyboard.prototype._fnRow = function (spec) {
        var self = this, row = document.createElement('div');
        row.className = 'akb-row';
        spec.forEach(function (s) {
            var b = document.createElement('button');
            b.className = 'akb-key fn' + (s.cls ? ' ' + s.cls : '');
            b.textContent = s.label;
            if (s.delta && !s.tap) {
                b.addEventListener('click', s.delta);
            } else if (s.tap) {
                b.addEventListener('click', s.tap);
            }
            if (s.enter) {
                b.addEventListener('click', function () {
                    self._commit();
                    self._translateTick();
                    self.onSubmit && self.onSubmit(self._value());
                });
            }
            if (s.backspace) {
                b.addEventListener('pointerdown', function (e) {
                    e.preventDefault();
                    clearTimeout(b._t);
                    b._t = setTimeout(function () { self._clear(); }, 450);
                });
                b.addEventListener('pointerup', function (e) {
                    e.preventDefault();
                    clearTimeout(b._t);
                    setTimeout(function () { self._backspace(); }, 0);
                });
            }
            row.appendChild(b);
        });
        return row;
    };

    /* Gboard-style: tapping a base letter opens all 7 vowel children */
    AmharicKeyboard.prototype._showOrders = function (btn, letter) {
        var self = this;
        var host = this._host;
        if (!host || this.showSymbols) return;
        var pop = document.createElement('div');
        pop.className = 'akb-pop';
        for (var o = 0; o < 7; o++) {
            (function (o) {
                var b = document.createElement('button');
                b.textContent = charFor(letter, o);
                if (o === 0) b.className = 'base';
                b.setAttribute('aria-label', letter + (ORDER_LABELS[o] === '1' ? ' (base)' : ' (' + ORDER_LABELS[o] + ')'));
                b.addEventListener('click', function (e) { e.stopPropagation(); self._insert(charFor(letter, o)); self._hideOrders(); });
                pop.appendChild(b);
            })(o);
        }
        var row = btn.parentElement;
        row.style.position = 'relative';
        var popW = 7 * 44 + 6 * 3 + 12 - 2;
        pop.style.top = '-68px';
        pop.style.left = Math.max(2, Math.min(btn.offsetLeft - (popW - 56) / 2, row.clientWidth - popW)) + 'px';
        this._hideOrders();
        row.appendChild(pop);
    };

    AmharicKeyboard.prototype._hideOrders = function () {
        if (this._host) { var pops = this._host.querySelectorAll('.akb-pop'); for (var i = 0; i < pops.length; i++) pops[i].remove(); }
    };

    AmharicKeyboard.prototype._renderSuggest = function () {
        var sug = this._entries.suggest;
        if (!sug) return;
        var self = this, val = this._value();
        var chips = this.suggestUrl && this.SUGGEST ? this._suggestChips() : [];
        var cur = val.split(TOK_RE).pop() || '';

        if (!chips.length && this.suggestUrl && this.SUGGEST) {
            this.SUGGEST = null;  // nothing useful → let local prediction answer
        }
        if (!chips.length) {
            if (!cur) {
                chips = chips.concat(this._nextWords(2).map(function (w) { return {w: w, type: 'next'}; }));
            }
            if (this.DICT) {
                chips = chips.concat(this._dictSuggest(3 - chips.length).map(function (c) { return {w: c.w, type: 'word'}; }));
            } else {
                var hits = cur ? this.miniWords.filter(function (w) { return w.indexOf(cur) === 0 && w !== cur; }).slice(0, 3 - chips.length)
                               : this.miniWords.slice(0, 3 - chips.length);
                chips = chips.concat(hits.map(function (w) { return {w: w, type: 'word'}; }));
            }
            chips = chips.slice(0, 3);
        }

        var old = sug.querySelectorAll('.akb-word, .akb-sent');
        for (var i = 0; i < old.length; i++) old[i].remove();
        var sp = sug.querySelector('.akb-sp');
        if (!chips.length) { sp.textContent = cur ? '—' : this.placeholder; }
        else { sp.textContent = ''; }

        chips.forEach(function (c) {
            var b = document.createElement('button');
            if (c.type === 'sent') { b.className = 'akb-sent'; }
            else { b.className = 'akb-word' + (c.type === 'next' ? ' nextword' : ''); }
            b.textContent = c.w;
            b.addEventListener('click', function () {
                if (c.type === 'sent') {
                    self.input.value = c.w;
                    self.input.setSelectionRange(c.w.length, c.w.length);
                } else if (c.type === 'next') {
                    var base = (self._value() || '').replace(/[\s\u1362\u1363\u1365\u1361]+$/, '');
                    self.input.value = base + ' ' + c.w + ' ';
                } else {
                    var tokens = (self._value() || '').split(TOK_RE);
                    tokens[tokens.length - 1] = c.w;
                    self.input.value = tokens.join(' ') + ' ';
                }
                self.input.focus();
                self.onInput && self.onInput(self._value(), 'suggest');
                self._render();
                self._translateTick();
                self._suggestTick();
            });
            sug.appendChild(b);
        });
    };

    /* optional live hint/translation bar (app provided) */
    AmharicKeyboard.prototype._translateTick = function () {
        var bar = this._entries.translateBar;
        if (!bar || !this.translate) return;
        var on = this.translate.enabled ? this.translate.enabled() : true;
        var txt = this._value().trim();
        if (!on || !txt) { bar.classList.add('hidden'); bar.textContent = ''; return; }
        bar.classList.remove('hidden');
        bar.textContent = '…';
        var self = this;
        clearTimeout(this._trsTimer);
        this._trsTimer = setTimeout(function () {
            try {
                Promise.resolve(self.translate.fetch(txt)).then(function (s) {
                    if (bar.isConnected) { bar.innerHTML = '<b>EN:</b> ' + escapeHtml(s || '—'); }
                }).catch(function () { bar.textContent = '—'; });
            } catch (e) { bar.textContent = '—'; }
        }, 400);
    };

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"]/g, function (m) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m];
        });
    }

    /* Fidel helpers shared with other apps (same API as the Werket editor). */
    AmharicKeyboard.compose = compose;
    AmharicKeyboard.charFor = charFor;
    AmharicKeyboard.ordersFor = ordersFor;
    AmharicKeyboard.PHONETIC = PHONETIC;
    AmharicKeyboard.DIGRAPHS = DIGRAPHS;
    AmharicKeyboard.VOWELS = VOWELS;
    AmharicKeyboard.QWERTY = QWERTY;
    AmharicKeyboard.LETTERS = LETTERS;

    root.AmharicKeyboard = AmharicKeyboard;
})(window);