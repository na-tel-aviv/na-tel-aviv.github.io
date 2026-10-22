"""Daily check of the "הודעות חשובות" box on the NA Israel meetings page.

New notices that mention a Tel-Aviv-Yafo meeting are added to the notices list
in community-v5.js; the workflow then opens a pull request for approval.
"""
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

SOURCE = 'https://www.naisrael.org.il/meetings/'
ROOT = Path(__file__).resolve().parents[2]
SEEN = Path(__file__).with_name('seen.json')
SCRIPT = ROOT / 'community-v5.js'
TZ = dt.timezone(dt.timedelta(hours=3))

AREA = ['תל אביב', 'תל-אביב', 'ת"א', 'ת״א', 'יפו', 'גן דבורה', 'ביצרון', 'רוטשילד', 'קלישר',
        'אלנבי', 'דיזנגוף', 'התלמי', 'שכונת התקווה', 'בת עין']
GENERIC_NAMES = {'פגישת NA', 'רק להיום', 'רק ביחד', 'קבוצת הדרך', 'הדרך לחופש', 'קבוצה ברוסית', 'פגישה ברוסית'}


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (na-tel-aviv.github.io notices check)'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')


def group_names():
    s = (ROOT / 'meetings-data.js').read_text(encoding='utf-8')
    meetings = json.loads(s[s.index('['):s.rindex(']') + 1])
    names = {m['name'].replace('(גן דבורה)', '').strip(' ״"') for m in meetings}
    return sorted(n for n in names if len(n) >= 5 and n not in GENERIC_NAMES)


def clean(fragment):
    text = re.sub(r'<(script|style)\b.*?</\1>', ' ', fragment, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def notice_items(page):
    """Every item in the visible "הודעות חשובות" boxes (boxes marked hide-me are old ones)."""
    items = []
    for m in re.finditer(r'<div class="elementor-element ([^"]*)"', page):
        if 'hide-me' in m.group(1):
            continue
        end = page.find('<div class="elementor-element ', m.end())
        block = page[m.end():end if end > 0 else len(page)]
        if 'הודעות חשובות' not in block:
            continue
        nxt = page.find('<div class="elementor-element ', end + 1) if end > 0 else -1
        if re.search(r'<h2[^>]*>\s*הודעות חשובות\s*</h2>\s*</div>', block) and end > 0:
            block = page[end:nxt if nxt > 0 else len(page)]  # heading widget: items sit in the next widget
        body = re.split(r'הודעות חשובות\s*(?:</[^>]+>\s*)*', block, maxsplit=1)[-1]
        for part in re.split(r'<img[^>]*>|</?li[^>]*>|</p>', body):
            text = clean(part)
            if len(text) >= 15 and 'הודעות חשובות' not in text:
                items.append(text)
    return list(dict.fromkeys(items))


def is_local(text, names):
    return any(k in text for k in AREA) or any(n in text for n in names)


def event_date(text, today):
    dates = []
    for d, m, y in re.findall(r'(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)', text):
        try:
            year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
            day = dt.date(year, int(m), int(d))
        except ValueError:
            continue
        if not y and day < today - dt.timedelta(days=60):
            day = day.replace(year=day.year + 1)
        dates.append(day)
    return max(dates) if dates else None


def title_for(text, names):
    for k in ['גן דבורה'] + names + AREA:
        if k in text:
            return f'{k} — הודעה מ-NA ישראל'
    return 'הודעה מ-NA ישראל'


def main():
    today = dt.datetime.now(TZ).date()
    names = group_names()
    seen = json.loads(SEEN.read_text(encoding='utf-8')) if SEEN.exists() else {}
    found = [t for t in notice_items(fetch(SOURCE)) if is_local(t, names)]
    print(f'{len(found)} Tel-Aviv-Yafo notice(s) on the NA Israel meetings page')
    new = []
    for text in found:
        key = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        if key in seen:
            continue
        when = event_date(text, today)
        if when and when < today:
            seen[key] = {'text': text, 'skipped': 'date already passed'}
            continue
        expires = (when + dt.timedelta(days=1)) if when else (today + dt.timedelta(days=14))
        seen[key] = {'text': text, 'added': today.isoformat()}
        new.append({'title': html.escape(title_for(text, names)), 'date': today.isoformat(),
                    'updated': f'עודכן {today:%d.%m.%Y}', 'expires': f'{expires.isoformat()}T00:00:00+03:00',
                    'text': html.escape(text), 'url': SOURCE, '_date_found': bool(when)})
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if new:
        script = SCRIPT.read_text(encoding='utf-8')
        m = re.search(r'^const notices=\[.*\];$', script, flags=re.M)
        if not m:
            sys.exit('notices list not found in community-v5.js')
        entries = ','.join(json.dumps({k: v for k, v in n.items() if not k.startswith('_')}, ensure_ascii=False) for n in new)
        line = m.group(0)
        line = line[:-2] + (',' if line != 'const notices=[];' else '') + entries + '];'
        SCRIPT.write_text(script[:m.start()] + line + script[m.end():], encoding='utf-8')
    lines = []
    for n in new:
        until = n['expires'][:10]
        note = '' if n['_date_found'] else ' (לא נמצא תאריך בהודעה — מוצגת שבועיים)'
        lines.append(f"- **{html.unescape(n['title'])}**\n  {html.unescape(n['text'])}\n  מוצגת עד {until}{note}")
    Path(ROOT / '.github/naisrael/summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'{len(new)} new notice(s)')


if __name__ == '__main__':
    main()
