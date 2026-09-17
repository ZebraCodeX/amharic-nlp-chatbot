#!/usr/bin/env node
/*!
 * smoke_test.js — headless DOM-stub test for the AmharicKeyboard web component,
 * focusing on the smart-type-ahead (`suggestUrl`) integration that /api/suggest
 * now powers. No browser needed: a minimal fake DOM + fetch stub let the real
 * component logic run under Node.
 *
 *   node tools/smoke_test.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const JS = fs.readFileSync(path.join(__dirname, '..', 'static', 'amharic-keyboard.js'), 'utf8');
const CSS = fs.readFileSync(path.join(__dirname, '..', 'static', 'amharic-keyboard.css'), 'utf8');

let passed = 0, failed = 0;
function ok(cond, name) {
    if (cond) { passed++; console.log('  ok  ' + name); }
    else { failed++; console.log('  FAIL ' + name); }
}
function assert(cond, name) { if (!cond) { failed++; console.log('  FAIL ' + name); } else { passed++; console.log('  ok  ' + name); } }

/* ---------------- minimal fake DOM ---------------- */

function fakeClassList(el) {
    const set = new Set();
    return {
        add: (...c) => c.forEach(x => set.add(x)),
        remove: (...c) => c.forEach(x => set.delete(x)),
        contains: c => set.has(c),
        toggle: (c, force) => { if (force === undefined) { set.has(c) ? set.delete(c) : set.add(c); } else { force ? set.add(c) : set.delete(c); } },
    };
}

function fakeEl(tag) {
    const el = {
        tagName: (tag || 'div').toUpperCase(),
        children: [], parentElement: null,
        dataset: {},
        className: '', textContent: '',
        style: { position: '' },
        offsetLeft: 0, clientWidth: 400, selectionStart: 0,
        _listeners: {},
        classList: null,
        set innerHTML(v) { this._innerHTML = v; this.children = []; },
        get innerHTML() { return this._innerHTML || ''; },
        set value(v) { this._value = String(v); this.selectionStart = this._value.length; },
        get value() { return this._value || ''; },
        addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
        dispatch(type, ev) { (this._listeners[type] || []).forEach(fn => fn(ev || {})); },
        appendChild(c) { c.parentElement = this; this.children.push(c); return c; },
        removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentElement = null; },
        remove() { if (this.parentElement) this.parentElement.removeChild(this); },
        querySelector(sel) { return this._find(sel, false); },
        querySelectorAll(sel) { return this._find(sel, true); },
        _find(sel, all) {
            // tiny selector support: ".akb-word" / "button.akb-word, .akb-sent"
            const want = sel.split(',').map(s => s.trim());
            const hits = [];
            const walk = node => {
                if (node !== this) {
                    const matches = want.some(spec => {
                        const parts = spec.split('.').filter(Boolean);
                        let i = 0;
                        if (parts[0] === (node.tagName || '').toLowerCase()) i = 1;
                        const cls = node.className.split(/\s+/);
                        return parts.slice(i).every(p => cls.indexOf(p) >= 0);
                    });
                    if (matches) hits.push(node);
                }
                node.children.forEach(walk);
            };
            walk(this);
            return all ? hits : (hits[0] || null);
        },
    };
    el.classList = fakeClassList(el);
    return el;
}

function makeInput() {
    const input = fakeEl('input');
    input.setSelectionRange = function (a, b) { this.selectionStart = a; };
    input.focus = function () {};
    input.removeEventListener = function () {};
    return input;
}

/* ---------------- fake fetch ---------------- */
const requests = [];
function installFetch(responses) {
    global.fetch = (url) => {
        requests.push(String(url));
        const p = url.split('?')[0];
        const body = responses[p];
        if (body === undefined) return Promise.reject(new Error('no stub for ' + p));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) });
    };
}

/* ---------------- the tests ---------------- */

function componentSourceChecks() {
    console.log('# component source wiring');
    assert(JS.includes('suggestUrl'), 'component exposes suggestUrl option');
    assert(JS.includes("type: 'sent'"), 'renders sentence chips (.akb-sent)');
    assert(CSS.includes('.akb-sent'), 'CSS styles .akb-sent');
    assert(JS.includes('compose'), 'component ships the phonetic compose()');
    assert(JS.includes('_phoneticType'), 'component supports phonetic typing');
    assert(CSS.includes('.akb-mode-toggle'), 'CSS styles the phonetic toggle');
}

function phoneticFlow() {
    console.log('# phonetic typing (Werket-style Latin -> Ge\'ez)');
    const root = global.window = {};
    global.document = { createElement: (t) => fakeEl(t), addEventListener: () => {} };
    eval(JS);
    const AK = root.AmharicKeyboard;
    assert(AK.compose('selam') === 'ሰላም', "compose('selam') === ሰላም");
    assert(AK.compose('buna') === 'ቡና', "compose('buna') === ቡና");
    assert(AK.compose('shi') === 'ሺ', "compose('shi') === ሺ");
    assert(AK.compose('chaw') === 'ቻው', "compose('chaw') === ቻው");
    assert(AK.ordersFor('ሀ').join('') === 'ሀሁሂሃሄህሆ', 'ordersFor() returns 7 vowel orders');
    assert(AK.charFor('ሰ', 4) === 'ሴ', 'charFor() maps vowel order 4');

    const input = makeInput();
    const container = fakeEl('div');
    const kbd = new AK({ container, input, phonetic: true });
    kbd.open();
    ['s', 'e', 'l', 'a', 'm'].forEach(ch => kbd._phoneticType(ch));
    assert(input.value === 'ሰላም', 'typing selam composes to ሰላም with the keyboard open');
    kbd._backspace();
    assert(input.value === 'ሰላ', 'backspace edits the phonetic buffer');
    kbd._commit();
    kbd.setPhonetic(false);
    assert(kbd.phonetic === false, 'phonetic mode can be switched off');
    kbd.destroy();
}

function suggestFlow() {
    console.log('# type-ahead end-to-end (fake DOM + fetch)');
    const input = makeInput();
    const container = fakeEl('div');
    const W = { words: [{ w: 'ሰላም', f: 10 }, { w: 'ሰላምታ', f: 4 }] };
    const N = { unigram: { 'ሰላም': 1 }, bigram: {}, trigram: {}, starters: [] };
    const S = { words: [['ሰላም', 10]], next: [['እንዴት', 3]], sentences: ['ሰላም እንዴት ነህ ዛሬ?', 'ሰላም ለጥያቄህ እናመሰግናለን።'] };
    installFetch({ '/api/words': W, '/api/ngram': N, '/api/suggest': S });

    const root = global.window = {};
    global.document = {
        createElement: (t) => fakeEl(t),
        addEventListener: () => {},
    };
    eval(JS); // defines window.AmharicKeyboard

    const kbd = new root.AmharicKeyboard({
        container, input,
        dictUrl: '/api/words', ngramUrl: '/api/ngram', suggestUrl: '/api/suggest',
    });
    kbd.open();
    // let data fetches resolve (words/ngram are Promise-based in _loadData)
    return Promise.resolve().then(() => new Promise(r => setTimeout(r, 5))).then(() => {
        const tokens = kbd._entries.suggest.children.filter(c => c.className === 'akb-sent');
        assert(tokens.length === 0, 'no sentence chips for empty input');

        // simulate typing a real prefix
        input.value = 'ሰላም';
        kbd._fetchSuggest();
        return Promise.resolve().then(() => kbd._sugTimer && clearTimeout(kbd._sugTimer));
    }).then(() => Promise.resolve()).then(() => {
        // fetch resolved → SUGGEST populated and rendered
        assert(kbd.SUGGEST && kbd.SUGGEST.sentences.length === 2, 'fetch stored sentence suggestions');
        const sent = kbd._entries.suggest.children.filter(c => c.className === 'akb-sent');
        assert(sent.length === 2, 'two sentence chips rendered');
        if (sent[0]) {
            sent[0].dispatch('click');
            assert(input.value === 'ሰላም እንዴት ነህ ዛሬ?', 'clicking a sentence chip fills the input');
        }
        // words still offered as fallback when server returns no sentences
        installFetch({ '/api/suggest': { words: [['እንጀራ', 9]], next: [], sentences: [] } });
        input.value = 'እንጀ';
        kbd._fetchSuggest();
        return Promise.resolve();
    }).then(() => Promise.resolve()).then(() => {
        const words = kbd._entries.suggest.children.filter(c => c.className.indexOf('akb-word') >= 0);
        assert(words.length >= 1, 'closest-word chips fall back when no sentences');
        assert(requests.some(u => u.indexOf('/api/suggest?text=') === 0), 'called /api/suggest with text param');
        kbd.destroy();
    });
}

componentSourceChecks();
suggestFlow().then(phoneticFlow).then(() => {
    console.log('\nRESULT: ' + passed + ' passed, ' + failed + ' failed');
    process.exit(failed ? 1 : 0);
}).catch(e => { console.error('unexpected error:', e); process.exit(2); });