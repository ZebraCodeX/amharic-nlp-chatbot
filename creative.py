#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
creative.py — offline generative skills for ዘር.

When no LLM is reachable, "write / create / develop / plan" requests still get
REAL output instead of canned chat lines: poems, song lyrics, story openings,
websites (HTML), essays and action plans. Every generator is deterministic and
pure stdlib, tailored to Amharic — they produce printable artifacts, never
boilerplate promises.

Used by chatbot.py as the offline half of the hybrid LLM routing:
    LLM → creative.py → rule fallback.
"""

import re
import html as _html

_TYPE_PATTERNS = [
    ('poem', r'ግጥም|ግጥሚያ|poem|verse'),
    ('song', r'ዘፈን|ዘፋኝ|መዝሙር|song|chorus'),
    ('website', r'ድህረ.?ገጽ|ድረ.?ገጽ|ዌብ.?ሳይት|website|web site|html'),
    ('plan', r'እቅድ|ዕቅድ|ፕላን|plan|መርሐግብር|ጥናት.?እቅድ'),
    ('story', r'ታሪክ.?ጻፍ|ታሪክ.?ፃፍ|ታሪክ.?ስጠኝ|ተረት|story|novel|ልቦለድ'),
    ('essay', r'ድርሰት|essay|ጽሑፍ'),
]

# "ስለ ____" catches are stronger than writing about anything.
_CREATIVE_VERBS = re.compile(
    r'ጻፍ|ፃፍ|ፅፍ|ጻፍልኝ|አዘጋጅ|አዘጋጅልኝ|ፍጠር|ፍጥረት|ሥራ|ስራ|ገንባ|'
    r'ዘርጋ|ዲዛይን|እቅድ|ዕቅድ|ፕላን|write|create|develop|design|make|build|generate|plan',
    re.IGNORECASE)

WORD_RE = re.compile(r'[\u1200-\u135a]+')


def detect(text):
    """Return the skill name ('poem', 'website'…) for a creative request, or None."""
    low = text.lower()
    for kind, pat in _TYPE_PATTERNS:
        if re.search(pat, low):
            return kind
    return None


def _topic(text, fallback='ሕይወት'):
    m = re.search(r'ስለ\s+([\u1200-\u135a0-9\s]{1,24}?)(?:\s+(?:ጻፍ|ፃፍ|አዘጋጅ|ፍጠር|ንገረኝ|ስጠኝ|ዘፍ|write|create|make|plan))?\s*$', text, re.I)
    if m:
        words = WORD_RE.findall(m.group(1))
        if words:
            return words[0]
    m = re.search(r'\babout\s+(?:a\s+|an\s+)?([a-z]{2,22})', text, re.I)
    if m:
        return m.group(1).lower()
    # fall back to the first meaningful Amharic noun-ish token
    words = WORD_RE.findall(text)
    for w in words:
        if w in ('ስለ', 'እባክህ', 'እባክሽ', 'በ', 'ና', 'እና', 'ምን', 'ነው', 'ጻፍ', 'ፃፍ', 'አዘጋጅ', 'ስጠኝ', 'ለ', 'ለት', 'ታሪክ', 'ኮድ', 'ግጥም', 'ዘፈን', 'እቅድ'):
            continue
        if len(w) > 3 and w[0] in 'ለየበከ':
            return w[1:]
        return w
    return fallback


def _wrap(title, body):
    return f'{title}\n{body}'


def poem(text):
    t = _topic(text)
    return _wrap(
        f"ግጥም · ስለ {t}",
        f"{t} እይታ ውስጥ ነህ.? ልዩ ብርሃን {t} ነህ የምታበራ\n"
        f"በምሽት ኮከብ ያህል በቀን ፀሐይ የምትጠለል\n"
        f"ደስታዬና ሀዘኔ በአንድ ልብ ውስጥ የምትይዝ\n"
        f"ቃል ሊገልፅህ ቀሮ ነገር ግን አንተ {t} ብቻ ትበቃለህ።\n"
        f"\n*ሊበራል ቃላቶች አሉ፣ ልክ እንደ ልብህ ቃና — እንደፈለከው ቀይሬ ልስጥህ።*")


def song(text):
    t = _topic(text)
    return _wrap(
        f"ዘፈን · «{t}»",
        f"[ስታንዛ]\n{t} ለኔ ነህ የመጀመሪያው ባህር\n"
        f"እዚህ ባህር ውስጥ መጥለቅ ለምሬያለሁ ሚዛን\n"
        f"{t} ከልቤ የማልለይው ወርቅ\n"
        f"ጊዜ ያልፍ ቦታ ይቀየር ትቀራለህ ልቤ ውስጥ\n"
        f"\n[ቁጥር 1]./ {t} ሲታይ ልቤ ይጡት እንደ ደመና\n"
        f"ሳይናገርከ የሚገባህከ የልብ ቋንቋ\n"
        f"[ቁጥር 2]./ በወጣትነት በእርጅና አንተን ፈልጌ\n"
        f"በጉዞዬ ሁሉ አንተን አግኝቼዋለሁ ደንብ።\n"
        f"\n*ወዳጅ፣ ዘፈኑን የበለጠ ማዳበር ከፈለክ ጥቅሶቹን ንገረኝ።*")


def website(text):
    t = _topic(text)
    t_title = _html.escape(t)
    return _wrap(
        'ድረ-ገጽ (HTML) · ስለ ' + t,
        f"<!doctype html>\n"
        f"<html lang='am'><head><meta charset='utf-8'>\n"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>\n"
        f"<title>{t_title}</title>\n"
        f"<style>\n"
        f"body{{font-family:'Noto Sans Ethiopic',sans-serif;margin:0;background:#f7f3e9;color:#26201a}}\n"
        f"header{{background:#943914;color:#fff;padding:24px;text-align:center}}\n"
        f"nav a{{color:#fff;margin:0 12px;text-decoration:none}}\n"
        f"main{{max-width:760px;margin:24px auto;padding:0 16px}}\n"
        f"section{{background:#fff;border-radius:10px;padding:18px;margin-bottom:14px}}\n"
        f"footer{{text-align:center;padding:16px;background:#26201a;color:#ddd}}\n"
        f"</style></head>\n"
        f"<body>\n"
        f"<header><h1>{t_title}</h1>\n"
        f"<nav><a href=\"#intro\">መግቢያ</a><a href=\"#about\">ስለ እኛ</a><a href=\"#contact\">ያግኙን</a></nav></header>\n"
        f"<main>\n"
        f"<section id=\"intro\"><h2>መግቢያ</h2><p>እንኳን ወደ {t_title} በደህና መጡ! እዚህ ዋና መልእክትህን አስቀምጥ።</p></section>\n"
        f"<section id=\"about\"><h2>ስለ እኛ</h2><p>ስለ {t_title} አጭር መግለጫ እነሆ። ምስሎችንና ማስታወቂያ ማከል ይቻላል።</p></section>\n"
        f"<section id=\"contact\"><h2>ያግኙን</h2><p>ኢሜይል፡- ስም@example.com · ስልክ፡- +251 9xx xxx xxx</p></section>\n"
        f"</main><footer>© 2026 · {t_title} · በዘር የተሰራ</footer>\n"
        f"</body></html>")


def plan(text):
    t = _topic(text)
    return _wrap(
        f"እቅድ · {t}",
        f"ግብ፡- {t} በትክክል ማዳበር/ማከናወን\n"
        f"1. ግቡን ግልጽ አድርግ — «{t}» ሲሳካ ምን ታያለህ? በአንድ ዓረፍተ ነገር ጻፍ።\n"
        f"2. ጊዜ ሰንጠረዥ — 7 ቀናት ቁልፍ እርምጃዎች፦ (ሀ) ማረጋገጥ (ለ) የመጀመሪያ ረቂቅ (ሐ) መገምገም (መ) ማጠናቀቅ።\n"
        f"3. ሀብቶች — ምን አለህ (ጊዜ፣ ቁሳቁስ፣ ሰው)? የጎደለውን ዝርዝር አውጣ።\n"
        f"4. አደጋዎች — ሊያዘገዩ የሚችሉ 2 ነገሮች ጻፍና መፍትሄ አቅድ።\n"
        f"5. እርምጃ 1 — በመጪው ቀን በጣም ትንሽ እርምጃ ምን ነው? ዛሬ አከናውነው።\n"
        f"6. ግምገማ — በየሳምንቱ እድገትህን ለካ፣ «ምን ተሳከ / ምን ቀለል?» በል።\n"
        f"\n*እቅዱን ማጠናቀር ከፈለክ ስለ ርዕሱ የበለጠ ንገረኝ።*")


def story(text):
    t = _topic(text)
    return _wrap(
        f"ታሪክ · {t}",
        f"መክፈቻ፦ በ«{t}» ምሽት ጨዋታ ሲፈፀም፣ ማይክል የተባለ ወጣት ከመንገድ ላይ አንድ ያልተለመደ ደብዳቤ አገኘ…\n"
        f"\nእንዴት ይቀጥል?\n"
        f"- ደብዳቤው የጻፈው ማን ነው? (ፊርማ የሌለው ሰው፣ ወይም ያለፈ ጀግና።)\n"
        f"- በውስጡ የተጻፈው ምስጢር ምንድን ነው? {t}.?\n"
        f"- ማይክል ምን ውሳኔ ያደርጋል? ወደ ደብዳቤው ቦታ መሄድ ይችላል…\n"
        f"\n*ታሪኩን ቀጥሎ እንድጽፍ ከፈለክ «ቀጥል» በል፣ እንደ ፈለከው አቅጣጫ እንወስዳለን።*")


def essay(text):
    t = _topic(text)
    return _wrap(
        f"ድርሰት · ስለ {t}",
        f"መግቢያ፦ እያንዳንዱ {t} በአሁኑ ዘመንም ሆነ በመጪው የማይቀር ትኩረት የሚሻ ርዕስ ነው። በዚህ ድርሰት {t} ዋጋውን፣ ፈተናዎቹንና መፍትሄውን እንመለከታለን።\n"
        f"\nአንቀጽ 1 — ዋጋ/ጠቀሜታ፦ ለምን «{t}» አስፈላጊ ነው? 3 ምክንያቶች ዘርዝር።\n"
        f"አንቀጽ 2 — ፈተና፦ በ«{t}» ዙሪያ የሚታዩ ችግሮችን ግለጽ (ማስረጃ ካለህ ጨምር)።\n"
        f"አንቀጽ 3 — መፍትሄ፦ እነዚህን ፈተናዎች ለማሸነፍ የሚቻሉ ተግባራዊ እርምጃዎች።\n"
        f"ማጠቃለያ፦ በማጠቃለል፣ {t} ችላ ሊባል የማይችል በመሆኑ፣ ሁሉም በትኩረት ሊሰራበት ይገባል።\n"
        f"\n*ለትክክለኛ መረጃ የአንተን ርዕስ በዝርዝር ስጠኝ፣ እንጓደድ።*")


SKILLS = {
    'poem': poem,
    'song': song,
    'website': website,
    'plan': plan,
    'story': story,
    'essay': essay,
    'write': poem,   # plain "ጻፍልኝ" → a short piece
}


def creative_answer(text):
    """Return a full offline artifact for a creative request, or None."""
    kind = detect(text)
    if kind:
        return SKILLS[kind](text)
    if _CREATIVE_VERBS.search(text) and any(w in text.lstrip() for w in ('ጻፍ', 'ፃፍ', 'ፅፍ')):
        return poem(text)
    return None