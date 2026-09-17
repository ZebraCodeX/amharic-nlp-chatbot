#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
codegen.py — offline code generation for Zer, in Amharic.

No external model is needed: given a programming request it produces real,
runnable code with **Amharic comments, Amharic identifiers and an Amharic
explanation**. Covers the common asks (sum, sort, loops, functions, classes,
files, JSON, Fibonacci, primes, palindromes, word counts, SQLite, HTML, CSS,
fetch/APIs, Bash, Git …) in Python, JavaScript, HTML, CSS, SQL and Bash.

Used by chatbot.py before any rule/LLM fallback, so `ፓይቶን ኮድ ጻፍልኝ` works with
zero network.
"""

import re

_ETH = re.compile(r'[\u1200-\u137f]')


def _has(text, *words):
    low = text.lower()
    return any(w in text or w in low for w in words)


def _detect_lang(text):
    low = text.lower()
    if _has(text, 'ፓይቶን', 'ፒቶን', 'ፒዮን') or 'python' in low or re.search(r'\bpy\b', low):
        return 'python'
    if _has(text, 'ጃቫስክሪፕት', 'ጄኤስ') or 'javascript' in low or 'node' in low or ' js' in low:
        return 'javascript'
    if _has(text, 'ኤችቲኤምኤል', 'ድረገፅ', 'ድረ-ገፅ', 'ገፅ') or 'html' in low:
        return 'html'
    if _has(text, 'ሲኤስኤስ', 'ቅጥ') or 'css' in low:
        return 'css'
    if _has(text, 'ኤስኪውኤል', 'ጠረጴዛ', 'ዳታቤዝ') or 'sql' in low or 'sqlite' in low:
        return 'sql'
    if _has(text, 'ሼል', 'ስክሪፕት', 'ሊኑክስ', 'ባሽ') or 'bash' in low or 'shell' in low:
        return 'bash'
    if _has(text, 'ጊት') or 'git' in low:
        return 'git'
    return None


# Each recipe: keywords, Amharic title, and per-language sources.
# Amharic identifiers are valid in Python and JavaScript, so they are used to
# show real Amharic coding; comments explain every step.
PY_SUM = """def ድምር(ቁጥሮች):
    # ሁሉንም ቁጥሮች ደምሮ ይመልሳል
    return sum(ቁጥሮች)

ቁጥሮች = [12, 7, 5, 20]
print("ድምሩ፦", ድምር(ቁጥሮች))  # → ድምሩ፦ 44"""

JS_SUM = """// ሁሉንም ቁጥሮች ደምሮ ይመልሳል
function ድምር(ቁጥሮች) {
  return ቁጥሮች.reduce((ጠቅላላ, ቁጥር) => ጠቅላላ + ቁጥር, 0);
}
const ቁጥሮች = [12, 7, 5, 20];
console.log("ድምሩ፦", ድምር(ቁጥሮች));"""

PY_SORT = """def አሰላልሽ(ዝርዝር):
    # ከትንሽ ወደ ትልቅ ያስተካክላል
    return sorted(ዝርዝር)

print(አሰላልሽ([42, 7, 1997, 1]))  # → [1, 7, 42, 1997]"""

JS_SORT = """// ከትንሽ ወደ ትልቅ ያስተካክላል
const አሰላልሽ = (ዝርዝር) => [...ዝርዝር].sort((ሀ, ለ) => ሀ - ለ);
console.log(አሰላልሽ([42, 7, 1997, 1]));"""

PY_LOOP = """# ከ1 እስከ 5 ድረስ ደጋግሞ ያትማል
for ቁጥር in range(1, 6):
    print(ቁጥር, "ሰላም ዓለም")

# በድጋሚ (while)
ቆጣሪ = 0
while ቆጣሪ < 3:      # ቆጣሪው ከ3 ሲያንስ
    print("ዘር!")
    ቆጣሪ += 1"""

JS_LOOP = """// ከ1 እስከ 5 ደጋግሞ ያትማል
for (let ቁጥር = 1; ቁጥር <= 5; ቁጥር++) {
  console.log(ቁጥር, "ሰላም ዓለም");
}"""

PY_FUNC = """def ሰላምታ(ስም):
    # ስምን ተቀብሎ ሰላምታ ይመልሳል
    return f"ሰላም {ስም}!"

print(ሰላምታ("ሰሎሜ"))  # → ሰላም ሰሎሜ!"""

JS_FUNC = """// ስምን ተቀብሎ ሰላምታ ይመልሳል
function ሰላምታ(ስም) {
  return `ሰላም ${ስም}!`;
}
console.log(ሰላምታ("ሰሎሜ"));"""

PY_CLASS = """class ሰው:
    # ሰውን የሚወክል ክፍል
    def __init__(self, ስም, ዕድሜ):
        self.ስም = ስም
        self.ዕድሜ = ዕድሜ

    def ጋራ_ሰላምታ(self):
        return f"ሰላም፣ ስሜ {self.ስም} ነው፤ {self.ዕድሜ} ዓመት ነኝ።"

አበበ = ሰው("አበበ", 30)
print(አበበ.ጋራ_ሰላምታ())"""

PY_FILE = """# ፋይል መጻፍ
with open("ማስታወሻ.txt", "w", encoding="utf-8") as ፋይል:
    ፋይል.write("ሰላም ዓለም")

# ፋይል ማንበብ
with open("ማስታወሻ.txt", encoding="utf-8") as ፋይል:
    print(ፋይል.read())"""

PY_JSON = """import json

መረጃ = {"ስም": "ዘር", "ቋንቋ": "አማርኛ", "ስሪት": 1}
# ወደ JSON መቀየር
print(json.dumps(መረጃ, ensure_ascii=False, indent=2))
# ከJSON መመለስ
መልሶ = json.loads('{"ስም": "ዘር"}')
print(መልሶ["ስም"])"""

JS_FETCH = """// ከኤፒአይ መረጃ ማምጣት
async function መረጃ_አምጣ(አድራሻ) {
  const ምላሽ = await fetch(አድራሻ);
  if (!ምላሽ.ok) throw new Error("ስህተት፦ " + ምላሽ.status);
  return ምላሽ.json();
}
መረጃ_አምጣ("https://api.example.com/items")
  .then((መረጃ) => console.log(መረጃ))
  .catch((ስህተት) => console.error(ስህተት));"""

PY_FIB = """def ፊቦናቺ(ብዛት):
    # የመጀመሪያዎቹን 'ብዛት' ፊቦናቺ ቁጥሮች ይመልሳል
    ተከታታይ = []
    ሀ, ለ = 0, 1
    for _ in range(ብዛት):
        ተከታታይ.append(ሀ)
        ሀ, ለ = ለ, ሀ + ለ
    return ተከታታይ

print(ፊቦናቺ(10))  # → [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]"""

PY_PRIME = """def ፕራይም_ነው(ቁጥር):
    # ቁጥሩ ፕራይም (ጠንካራ) መሆኑን ያረጋግጣል
    if ቁጥር < 2:
        return False
    for አካፋይ in range(2, int(ቁጥር ** 0.5) + 1):
        if ቁጥር % አካፋይ == 0:
            return False
    return True

print([n for n in range(2, 20) if ፕራይም_ነው(n)])  # → [2, 3, 5, 7, 11, 13, 17, 19]"""

PY_PAL = """def ፓሊንድሮም_ነው(ጽሑፍ):
    # ወደ ፊትና ወደ ኋላ ተመሳሳይ መሆኑን ያረጋግጣል
    ጽሑፍ = ጽሑፍ.replace(" ", "").lower()
    return ጽሑፍ == ጽሑፍ[::-1]

print(ፓሊንድሮም_ነው("ሰላም ሰላም"))"""

PY_COUNT = """from collections import Counter

ጽሑፍ = "ቡና ሻይ ቡና ውሃ ቡና"
# የየቃላቱን ብዛት ይቆጥራል
ብዛት = Counter(ጽሑፍ.split())
print(ብዛት.most_common())  # → [('ቡና', 3), ('ሻይ', 1), ('ውሃ', 1)]"""

PY_SQL = """import sqlite3

# የመረጃ ቋት መክፈት (ከሌለ ይፈጠራል)
ዳታቤዝ = sqlite3.connect("ሱቅ.db")
ጠረጴዛ = ዳታቤዝ.cursor()
# ሰንጠረዥ መፍጠር
ጠረጴዛ.execute("CREATE TABLE IF NOT EXISTS ዕቃ (id INTEGER PRIMARY KEY, ስም TEXT, ዋጋ REAL)")
# መረጃ ማስገባት
ጠረጴዛ.execute("INSERT INTO ዕቃ (ስም, ዋጋ) VALUES (?, ?)", ("ቡና", 120.5))
ዳታቤዝ.commit()
# ማንበብ
for ረድፍ in ጠረጴዛ.execute("SELECT * FROM ዕቃ"):
    print(ረድፍ)
ዳታቤዝ.close()"""

HTML_PAGE = """<!doctype html>
<html lang="am">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ሰላም ዓለም</title>
</head>
<body>
  <h1>ሰላም ዓለም!</h1>
  <p id="መልእክት">ዘር እዚህ ነው።</p>
  <button onclick="አሳይ()">ንካኝ</button>
  <script>
    function አሳይ() {
      document.getElementById('መልእክት').textContent = 'ሰላም ከዘር!';
    }
  </script>
</body>
</html>"""

CSS_STYLE = """/* የገጽ ቅጥ */
body {
  font-family: 'Noto Sans Ethiopic', sans-serif;
  background: #f7f3e9;      /* የወረቀት ቀለም */
  color: #241f1a;
  margin: 0;
  padding: 24px;
}
h1 { color: #14532d; }       /* አረንጓዴ */
button {
  background: #fcdd09;        /* ቢጫ */
  border: 1px solid #da121a;  /* ቀይ */
  border-radius: 10px;
  padding: 10px 18px;
  cursor: pointer;
}
button:hover { background: #ffe74d; }"""

BASH_SCRIPT = """#!/usr/bin/env bash
# ቀላል የሼል ስክሪፕት
for ስም in ማርያም አበበ ሰሎሜ; do
  echo "ሰላም $ስም!"     # ለየስሙ ሰላምታ
done

echo "ፋይሎች፦"
ls -la"""

GIT_CMDS = """# የGit መሰረታዊ ትዕዛዞች
git init                       # አዲስ ማከማቻ መፍጠር
git add .                       # ሁሉንም ለውጦች ማዘጋጀት
git commit -m "መጀመሪያ ስሪት"    # መዝግብ
git branch feature              # አዲስ ቅርንጫፍ
git checkout feature            # ወደ ቅርንጫፉ መሄድ
git push origin main            # ወደ ርቀት ማከማቻ መላክ"""


RECIPES = [
    (('ድምር', 'ደምር', 'sum', 'add', 'total', 'ጠቅላላ'), 'የቁጥሮች ድምር', {'python': PY_SUM, 'javascript': JS_SUM}),
    (('አሰላልሽ', 'ደረድር', 'sort', 'order', 'አስተካክል'), 'ዝርዝርን ማሰላለስ', {'python': PY_SORT, 'javascript': JS_SORT}),
    (('loop', 'ሉፕ', 'ድገም', 'መደጋገም', 'for', 'while', 'እስከ'), 'ድግግሞሽ (loop)', {'python': PY_LOOP, 'javascript': JS_LOOP}),
    (('function', 'ተግባር', 'ፋንክሽን', 'greet', 'ሰላምታ'), 'ተግባር (function)', {'python': PY_FUNC, 'javascript': JS_FUNC}),
    (('class', 'ክፍል', 'ክላስ', 'object', 'ኦብጀክት'), 'ክፍል (class)', {'python': PY_CLASS}),
    (('file', 'ፋይል', 'አንብብ', 'ማንበብ', 'መጻፍ'), 'ፋይል ማንበብና መጻፍ', {'python': PY_FILE}),
    (('json', 'ጃሶን'), 'JSON', {'python': PY_JSON}),
    (('fetch', 'api', 'ኤፒአይ', 'http', 'request'), 'ከኤፒአይ መረጃ ማምጣት', {'javascript': JS_FETCH}),
    (('fibonacci', 'ፊቦናቺ', 'ፊቦናች'), 'ፊቦናቺ', {'python': PY_FIB}),
    (('prime', 'ፕራይም', 'ጠንካራ'), 'የፕራይም ቁጥር ማረጋገጥ', {'python': PY_PRIME}),
    (('palindrome', 'ፓሊንድሮም'), 'የፓሊንድሮም ማረጋገጫ', {'python': PY_PAL}),
    (('count', 'ቁጥር ቁጠር', 'word', 'ብዛት', 'ቃላት'), 'የቃላት ብዛት መቁጠር', {'python': PY_COUNT}),
    (('database', 'ዳታቤዝ', 'sqlite', 'sql', 'ጠረጴዛ'), 'SQLite የመረጃ ቋት', {'python': PY_SQL, 'sql': PY_SQL}),
    (('html', 'ድረገፅ', 'ድረ-ገፅ', 'web', 'ገፅ'), 'የድረ-ገፅ HTML', {'html': HTML_PAGE}),
    (('css', 'ቅጥ', 'style', 'ቀለም'), 'CSS ቅጥ', {'css': CSS_STYLE}),
    (('bash', 'ሼል', 'shell', 'ስክሪፕት', 'linux', 'ሊኑክስ'), 'Bash ስክሪፕት', {'bash': BASH_SCRIPT}),
    (('git', 'ጊት'), 'Git ትዕዛዞች', {'git': GIT_CMDS}),
]

_LANG_ARGS = {
    'python': ('ፓይቶን', 'python'),
    'javascript': ('ጃቫስክሪፕት', 'javascript'),
    'html': ('HTML', 'html'),
    'css': ('CSS', 'css'),
    'sql': ('SQL', 'sql'),
    'bash': ('Bash', 'bash'),
    'git': ('Git', 'bash'),
}


def generate(text):
    """Return an Amharic code reply, or None when this isn't a code request."""
    if not text:
        return None

    lang = _detect_lang(text)
    matched = None
    for keys, title, sources in RECIPES:
        if any(k in text or k.lower() in text.lower() for k in keys):
            matched = (title, sources)
            break

    # A code ask needs a programming-language mention or explicit code wording;
    # a task keyword alone (e.g. «ጠቅላላ» = total) must not hijack normal chat.
    asks_code = _has(text, 'ኮድ', 'ጻፍ', 'ፃፍ', 'ፅፍ', 'ስክሪፕት', 'ፕሮግራም',
                    'code', 'write', 'script', 'program', 'function', 'algorithm')
    if not (lang or matched):
        return None
    if not lang and not asks_code:
        return None

    title, sources = matched or ('ምሳሌ', {'python': PY_FUNC})
    if not lang or lang not in sources:
        lang = next(iter(sources))
    code = sources[lang]

    label, fence = _LANG_ARGS.get(lang, ('ፓይቶን', 'python'))
    explanation = {
        'python': 'ለማስኬድ፦ `python3 ፋይል.py`',
        'javascript': 'ለማስኬድ፦ `node ፋይል.js` ወይም በአሳሽ ውስጥ።',
        'html': 'ፋይሉን `index.html` ብለህ አስቀምጠህ በአሳሽ ክፈተው።',
        'css': 'በ `<head>` ውስጥ `<link rel="stylesheet" href="style.css">` ጨምር።',
        'sql': 'በ SQLite ለመፈተን፦ `sqlite3 ሱቅ.db < ፋይል.sql`።',
        'bash': '`chmod +x ፋይል.sh && ./ፋይል.sh` ብለህ አስኪድ።',
        'git': 'በፕሮጀክት አካባቢ በተርሚናል አስኪድ።',
    }.get(lang, '')

    return (f"በ{label} ለ«{title}» የሚሰራ ኮድ እነሆ — "
            f"በአማርኛ አስተያየትና የአማርኛ ስሞች፦\n\n"
            f"```{fence}\n{code}\n```\n\n{explanation}\n"
            f"የተለየ ተግባር ከፈለግህ «በ{label} … ጻፍልኝ» በለኝ።")


if __name__ == '__main__':
    import sys
    print(generate(' '.join(sys.argv[1:]) or 'ፓይቶን ኮድ ጻፍልኝ ድምር'))
