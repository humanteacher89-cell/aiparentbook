"""AI시대 부모백과(aiparentbook.com) 정적 사이트 만들기.

  python build.py import <bundle.json>   연재부 묶음에서 공개해도 되는 글만 data/notes.json으로 가져온다
  python build.py build                  data/notes.json + config.json -> docs/ (Cloudflare Pages에 올리는 폴더)

- 글 문장은 연재부 정본 그대로 쓴다(손으로 옮기지 않는다).
- config.json에서 published가 false인 글은 질문·공개일만 가져온다(본문은 저장소에 넣지 않는다).
- 모든 링크는 상대 경로라 github.io 하위 주소와 aiparentbook.com 루트 양쪽에서 돈다.
- 화면은 시안 C '근거 사전'(2026-10-31 휴먼쌤 선택), 글꼴 · 글씨 크기는 휴먼티처닷컴 가독성을 따름(11-01).
- 첫 화면 검색창 아래는 시안 B '사전처럼'(2026-11-08 휴먼쌤 선택): 오늘의 질문 띠 · 상황 타일 · 질문 번호(접힘) · 답하는 사람.
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "notes.json"
OUT = ROOT / "docs"
ASSETS = ROOT / "assets"
SHORTS = ROOT / "shorts"


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------- import
def cmd_import(bundle_path):
    cfg = load_config()
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    notes = {}
    if DATA.exists():
        notes = json.loads(DATA.read_text(encoding="utf-8"))
    for no, c in cfg["notes"].items():
        b = bundle.get(no)
        if not b:
            print(f"{no}: 묶음에 없음, 건너뜀")
            continue
        n = {"no": no, "question": b["question"], "material": b["material"], "pages": b["pages"]}
        if c.get("published"):
            n["conclusion"] = b["raw2"]
            n["evidence"] = b["raw3"]
            # 실천 자료 안내: 4단계 글에서 구성 목록(- 로 시작하는 줄)만
            n["kit"] = [l[2:].strip() for l in b["raw4"].splitlines() if l.startswith("- ")]
            n["workbook"] = bool(b.get("workbook_line"))
        notes[no] = n
        print(f"{no}: {'본문까지' if c.get('published') else '질문만'}")
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- text
def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"==(.+?)==", r"<mark>\1</mark>", s)  # 네프콘 노란 형광펜
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def plain(s):
    """검색용 글자: 강조 기호를 뺀 소문자."""
    return re.sub(r"[*=]", "", s).lower()


def md_blocks(text):
    """빈 줄로 나눈 덩어리 -> html. 1. 로 시작하는 줄 묶음은 번호 목록."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if all(l.startswith(">") for l in lines):
            out.append(("quote", "<br>".join(inline(l.lstrip("> ").strip()) for l in lines)))
        elif all(re.match(r"\d+\.\s", l) for l in lines):
            out.append("<ol>" + "".join(f"<li>{inline(re.sub(r'^\d+\.\s', '', l))}</li>" for l in lines) + "</ol>")
        else:
            out.append(("today", block) if block.startswith("**오늘 해 볼 한 가지**") else
                       ("unknown", block) if block.startswith("**아직 모르는 것**") else
                       f"<p>{'<br>'.join(inline(l) for l in lines)}</p>")
    return out


def lead_rest(block, head):
    rest = block[len(head):].lstrip(" —-").strip()
    return inline(rest)


def split_conclusion(n):
    """결론 첫 문장(큰 글씨), 나머지 문단들, '오늘 해 볼 한 가지' 문장. 모두 정본 그대로."""
    raw = n["conclusion"].strip()
    m = re.match(r"(.+?[.?!])\s+(.*)$", raw, re.S)
    big, rest = (m.group(1), m.group(2)) if m else (raw, "")
    paras, today = [], ""
    for b in (md_blocks(rest) if rest else []):
        if isinstance(b, tuple) and b[0] == "today":
            today = lead_rest(b[1], "**오늘 해 볼 한 가지**")
        elif isinstance(b, str):
            paras.append(b)
    return big, paras, today


def parse_evidence(n):
    """근거 글을 정본 그대로 나눈다: 근거 묶음(제목, 덩어리들) · 인용 · 아직 모르는 것 · 참고자료 줄 · 묶음 밖 덩어리."""
    groups, quotes, unknown, refs, loose = [], [], [], [], []
    cur = None
    for b in md_blocks(n["evidence"]):
        if isinstance(b, tuple) and b[0] == "unknown":
            cur = None
            unknown.append(lead_rest(b[1], "**아직 모르는 것**"))
        elif isinstance(b, tuple) and b[0] == "quote":
            cur = None
            quotes.append(b[1])
        elif isinstance(b, str):
            head = re.match(r"<p><b>([^<]+)</b>(?:<br>|\s+)?(.*)</p>$", b, re.S)
            if head and head.group(1).strip() == "참고자료":
                cur = None
                refs += [l.strip() for l in head.group(2).split("<br>") if l.strip()]
            elif head:
                cur = (head.group(1), [f"<p>{head.group(2).strip()}</p>"] if head.group(2).strip() else [])
                groups.append(cur)
            elif cur:
                cur[1].append(b)
            else:
                loose.append(b)
    return groups, quotes, unknown, refs, loose


def ref_short(r):
    """'Bastani, H. 외 (2025). …' -> 'Bastani 외 2025' (못 읽으면 앞부분만)."""
    t = html.unescape(re.sub(r"<[^>]+>", "", r))
    m = re.match(r"\s*([^,(]+?)\s*(?:,[^(]*?)?\s*(외)?\s*\((\d{4})\)", t)
    return f"{m.group(1).strip()}{' 외' if m.group(2) else ''} {m.group(3)}" if m else t[:28]


# 선 아이콘(24칸). 상황 id와 같은 이름은 상황별 색인에 쓴다
ICON_PATHS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "back": '<path d="M19 12H5M11 18l-6-6 6-6"/>',
    "down": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "homework": '<path d="M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4"/>',
    "start": '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    "trust": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "wrong": '<path d="M12 3l10 18H2L12 3zM12 10v4M12 17.5v.5"/>',
    "ask": '<path d="M4 5h16v11H9l-5 4V5z"/><path d="M9 10.5h.01M12 10.5h.01M15 10.5h.01"/>',
    "practice": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>',
    "heart": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    "safety": '<path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6l8-3z"/>',
    "school": '<path d="M2 10l10-5 10 5-10 5-10-5z"/><path d="M6 12v5c3.5 2.4 8.5 2.4 12 0v-5"/>',
    "age": '<path d="M5 20v-6M10 20V10M15 20V6M20 20V3"/>',
    "future": '<path d="M12 21v-9M12 12c0-4-3-6.5-7-6.5 0 4 3 6.5 7 6.5zM12 10c0-3 2.5-5.5 6.5-5.5 0 3.5-2.5 5.5-6.5 5.5z"/>',
}


def icon(name):
    return f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">{ICON_PATHS.get(name, "")}</svg>'


# ---------------------------------------------------------------- page shell
def page(prefix, title, desc, body):
    t = html.escape(title)
    d = html.escape(desc)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{t}</title>
<meta name="description" content="{d}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="AI시대 부모백과">
<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1C1A2C" media="(prefers-color-scheme: dark)">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Jua&family=Gowun+Dodum&display=swap">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="bar"><div class="in"><a class="logo" href="{prefix or './'}"><img src="{prefix}humanssaem-mark.png" alt="" width="36" height="36"><span><small>휴먼쌤의</small>AI시대 부모백과</span></a>
<nav class="nav" aria-label="바로 가기"><a class="ico" href="{prefix}#search" aria-label="질문 찾기">{icon("search")}</a><a class="pill" href="{prefix}#questions">질문 목록</a></nav></div></header>
<main>
{body}
</main>
<footer class="foot"><div class="in"><span class="logo"><span><small>휴먼쌤의</small>AI시대 부모백과</span></span><p>질문에 답하는 사람 휴먼쌤 김수현 · <a href="{prefix}about/">소개</a> · <a href="https://human-teacher.com/" rel="noopener">휴먼쌤 사이트</a></p><p>광고 없이 운영합니다. 결론과 근거는 누구나 무료로 읽을 수 있어요.</p></div></footer>
</body>
</html>
"""


# ---------------------------------------------------------------- pieces
def age_label(cfg, c):
    return " · ".join(a["label"] for a in cfg["ages"] if a["id"] in c["ages"])


def sit_of(cfg, c):
    return next(s for s in cfg["situations"] if s["id"] == c["situation"])


def row_html(prefix, cfg, n, c):
    """질문 한 줄. data-text는 첫 화면 찾기 칸이 보는 글자(질문 · 상황 · 나이)."""
    live = c.get("published")
    text = plain(" ".join([n["question"], sit_of(cfg, c)["label"], age_label(cfg, c)]))
    return (f'<a class="row{" live" if live else ""}" href="{prefix}q/{n["no"]}/" data-ages="{" ".join(c["ages"])}" '
            f'data-text="{html.escape(text)}"><span class="no">{n["no"]}</span><b>{inline(n["question"])}</b>'
            f'<span class="st">{"읽기" if live else "정리 중"}</span></a>')


def build_latest(cfg, n, c):
    """가장 최근에 공개한 글 한 장: 결론 첫 문단과 참고자료 이름."""
    big, paras, _ = split_conclusion(n)
    groups, _, _, refs, _ = parse_evidence(n)
    first = re.sub(r"^<p>|</p>$", "", paras[0]) if paras else ""
    ev = (f'<div class="refs-s">{"".join(f"<span>{html.escape(ref_short(r))}</span>" for r in refs)}</div>'
          if refs else f"근거 {len(groups)}가지")
    href = f"q/{n['no']}/"
    return f"""<section aria-labelledby="latest-h"><h2 id="latest-h">최근 정리된 질문</h2>
<article class="card latest"><p class="mt"><span class="tag">{age_label(cfg, c)} · {html.escape(sit_of(cfg, c)["label"])}</span><span class="qno">질문 {n['no']}</span></p>
<h3><a href="{href}">{inline(n['question'])}</a></h3>
<dl><div><dt>결론</dt><dd><b>{html.escape(big)}</b> {first}</dd></div><div><dt>근거</dt><dd>{ev}</dd></div></dl>
<a class="more" href="{href}">결론 · 근거 · 실천 읽기{icon("arrow")}</a></article></section>"""


HOME_JS = """<script>
(function(){var KEY='apb-age',box=document.getElementById('rows'),rows=[].slice.call(box.querySelectorAll('.row')),btns=[].slice.call(document.querySelectorAll('#ages button')),
empty=document.getElementById('empty'),q=document.getElementById('q'),hint=document.getElementById('hint'),hintT=document.getElementById('hint-t'),list=document.getElementById('questions'),
more=document.getElementById('more'),LIMIT=12,open=false,
age='elementary',EMPTY_AGE=empty.textContent,EMPTY_Q='찾는 질문이 아직 없어요. 다른 말로 찾아보세요.';
function show(){var term=q.value.trim().toLowerCase(),words=term?term.split(/\\s+/):[],shown=0;
btns.forEach(function(b){b.setAttribute('aria-pressed',!words.length&&b.dataset.age===age?'true':'false')});
rows.forEach(function(t){var ok=words.length?words.every(function(w){return t.dataset.text.indexOf(w)>-1}):(!btns.length||(' '+t.dataset.ages+' ').indexOf(' '+age+' ')>-1);if(ok)shown++;t.hidden=!ok||(!words.length&&!open&&shown>LIMIT)});
box.hidden=!shown;empty.hidden=!!shown;empty.textContent=words.length?EMPTY_Q:EMPTY_AGE;hint.hidden=!words.length;if(words.length)hintT.textContent='"'+q.value.trim()+'" 찾은 질문 '+shown+'개';
more.hidden=!!words.length||open||shown<=LIMIT;more.textContent='질문 '+(shown-LIMIT)+'개 더 보기';}
var fold=document.getElementById('qfold');
function unfold(){if(fold&&!fold.open)fold.open=true}
function go(){unfold();show();list.scrollIntoView({behavior:'smooth',block:'start'})}
function byHash(){if(location.hash==='#questions'){unfold();list.scrollIntoView({block:'start'})}}
window.addEventListener('hashchange',byHash);
btns.forEach(function(b){b.addEventListener('click',function(){age=b.dataset.age;q.value='';open=false;try{localStorage.setItem(KEY,age)}catch(e){}show()})});
more.addEventListener('click',function(){open=true;show()});
document.getElementById('search').addEventListener('submit',function(e){e.preventDefault();go()});
q.addEventListener('input',function(){if(q.value.trim())unfold();show()});
[].slice.call(document.querySelectorAll('.chips button')).forEach(function(b){b.addEventListener('click',function(){q.value=b.dataset.q;go()})});
document.getElementById('clear').addEventListener('click',function(){q.value='';show();q.focus()});
try{age=localStorage.getItem(KEY)||age}catch(e){}show();byHash();})();
(function(){var bs=[].slice.call(document.querySelectorAll('.kwb')),cur=null;
function set(b){cur=b;bs.forEach(function(x){var on=x===b;x.setAttribute('aria-expanded',on?'true':'false');document.getElementById('kp-'+x.dataset.sit).hidden=!on});
if(b){var p=document.getElementById('kp-'+b.dataset.sit),r=p.getBoundingClientRect();if(r.top>innerHeight-120)p.scrollIntoView({behavior:'smooth',block:'start'})}}
bs.forEach(function(b){b.addEventListener('click',function(e){e.preventDefault();set(cur===b?null:b)})});})();
</script>"""


# ---------------------------------------------------------------- pages
def build_index(cfg, notes):
    have = [no for no in sorted(cfg["notes"]) if no in notes]
    live = sorted([no for no in have if cfg["notes"][no].get("published")],
                  key=lambda k: cfg["notes"][k]["release"], reverse=True)
    total = len(have)
    # 시안 B '사전처럼'(2026-11-08 휴먼쌤 선택): 오늘의 질문 띠 → 상황 타일 → 질문 번호(접힘) → 답하는 사람
    today = ""
    if live:
        tn = notes[live[0]]
        today = (f'<section aria-label="최근에 올라온 글"><a class="todaystrip" href="q/{tn["no"]}/"><span><small>최근에 올라온 글 · 질문 {tn["no"]}</small>'
                 f'<b>{inline(tn["question"])}</b></span><span class="arrow">{icon("arrow")}</span></a></section>')
    # 대표 키워드 6개(11-08 휴먼쌤 "번호나 질문 00개 다 빼고 딱 키워드만, 위아래 폭 줄이고, 대표 6개만, 검색창 바로 아래"):
    # config 상황 중 home: true. 누르면 키워드 쪽 s/<id>/. 나머지 상황 쪽은 그대로 있고 전체 질문 · 검색으로 닿는다
    # 11-08 휴먼쌤 "키워드 누르면 아까처럼 키워드 영역 바로 아래에 질문들이 나오도록": 단추를 누르면 6개 단추 바로 아래에
    # 그 키워드의 질문 카드가 펼쳐진다(다시 누르면 닫힘). 처음에는 아무것도 펼치지 않고, 단추는 모두 같은 모양.
    # 자바스크립트가 없으면 단추는 키워드 쪽 s/<id>/로 간다
    tiles, panels = [], []
    for s in [s for s in cfg["situations"] if s.get("home") and any(cfg["notes"][no]["situation"] == s["id"] for no in have)]:
        nos = [no for no in have if cfg["notes"][no]["situation"] == s["id"]]
        n_live = sum(1 for no in nos if cfg["notes"][no].get("published"))
        tiles.append(f'<a class="kwb" href="s/{s["id"]}/" data-sit="{s["id"]}" aria-expanded="false" aria-controls="kp-{s["id"]}">'
                     f'{html.escape(s.get("kw") or s["label"])}</a>')
        cards = "".join(q_card("", cfg, notes[no], cfg["notes"][no]) for no in nos)
        panels.append(f'<div class="kpanel" id="kp-{s["id"]}" hidden><p class="kt"><b>{html.escape(s["label"])}</b>'
                      f'<span>질문 {len(nos)}개 · 읽기 {n_live}편</span></p><ul class="qcs">{cards}</ul></div>')
    # 분류는 상황 하나로 통일(11-08 휴먼쌤 "그냥 상황으로만 통일할게"): 나이 버튼은 두지 않는다. 나이는 config에 그대로 두고 검색 글자에만 쓴다
    rows = "".join(row_html("", cfg, notes[no], cfg["notes"][no]) for no in have)
    # '자주 찾는 말' 칩은 키워드 카드와 같은 일이라 뺐다(11-08). 첫 문장 아래 설명 한 줄 대신 '한 편은 이렇게 정리해요' 4단계(휴먼티처닷컴 블록 차용)
    steps = """<section class="howto" aria-labelledby="how-h"><h2 id="how-h">한 편은 이렇게 정리해요</h2>
<ol class="hsteps">
<li><i>1</i><div><b>질문</b><p>부모님이 실제로 묻는 말 그대로 시작해요. "숙제할 때 챗GPT 써도 되나요?"처럼요.</p></div></li>
<li><i>2</i><div><b>결론</b><p>답을 먼저 한 줄로 말해요. 되는지 안 되는지, 그리고 그보다 중요한 것이 무엇인지.</p></div></li>
<li><i>3</i><div><b>근거</b><p>연구를 셋 안팎 골라 누가 누구를 어떻게 살폈는지 적고, 그 연구가 말해 주지 못하는 것(한계)도 함께 적어요.</p></div></li>
<li><i>4</i><div><b>오늘 해 볼 한 가지</b><p>집에서 바로 해 볼 한 가지를 질문하기 · 확인하기 · 실천하기 세 걸음(휴먼쌤 ACT)으로 정리해요.</p>
<span class="actchips"><span class="a">A 질문하기</span><span class="c">C 확인하기</span><span class="t">T 실천하기</span></span></div></li>
</ol></section>"""
    body = f"""<section class="top"><div class="hero">
<h1>아이가 쓰는 AI,<br>근거로 확인하세요</h1>
<form class="search" id="search" role="search"><label class="sr" for="q">질문 찾기</label><input id="q" type="search" placeholder="무엇이 궁금하세요?" autocomplete="off"><button type="submit" aria-label="찾기">{icon("search")}</button></form>
<section class="kwarea" id="situations" aria-labelledby="kw-h"><h2 id="kw-h">키워드로 찾기</h2>
<nav class="kwbs" aria-labelledby="kw-h">{"".join(tiles)}</nav>
{"".join(panels)}</section>
</div></section>
<div class="wrap">
{steps}
{today}
<section id="questions" aria-labelledby="all-h">
<details class="card fold" id="qfold"><summary>전체 질문 살펴보기 <span class="cnt">{total}개</span></summary>
<div class="inner">
<p class="hint" id="hint" hidden><span id="hint-t"></span><button type="button" id="clear">지우기</button></p>
<div class="card rows" id="rows">{rows}</div>
<button type="button" class="more-btn" id="more" hidden>더 보기</button>
<p class="empty" id="empty" hidden>이 나이에 맞는 질문은 아직 없어요. 지금은 초등 자녀를 둔 부모님 질문부터 답하고 있어요.</p>
</div></details></section>
<section aria-label="답하는 사람"><article class="card whoam">
<img src="humanssaem-mark.png" alt="" width="52" height="52">
<p><b>휴먼쌤, 생각주도력 키우는 교사아빠</b>공립 초등교사 14년차 · 딸 둘 아빠</p>
<a class="btn ghost" href="https://human-teacher.com/" rel="noopener">휴먼쌤 소개 페이지 바로 가기</a>
<a class="btn brand" href="https://contents.premium.naver.com/humanteacher/humanteacher89" rel="noopener">무료 학습 자료 받으러 가기</a>
</article></section>
</div>
{HOME_JS}"""
    return page("", "AI시대 부모백과 — 부모의 질문에 답하는 AI 교육 가이드",
                "숙제, 첫 사용, 계정, AI 답 믿기까지. 아이와 AI 사이에서 부모님이 실제로 묻는 질문에 결론과 근거로 답합니다.", body)


def ev_group_html(title, parts):
    """근거 한 묶음을 카드로(접지 않는다). 형광펜 문단은 강조 상자, '(단, …)' 줄은 작은 글씨로 뗀다(문장은 그대로)."""
    m = re.match(r"(근거\s*\S+)\s*[-–—]\s*(.+)$", title)
    key, text = (m.group(1), m.group(2)) if m else ("", title)
    body = []
    for p in parts:
        if "<mark>" in p and p.startswith("<p>"):
            lines = re.sub(r"^<p>|</p>$", "", p).split("<br>")
            take = [l for l in lines if not l.startswith("(단")]
            note = [l for l in lines if l.startswith("(단")]
            body.append(f'<div class="take"><p>{"<br>".join(take)}</p></div>')
            body += [f'<p class="note">{l}</p>' for l in note]
        else:
            body.append(p)
    k = f'<span class="k">{html.escape(key)}</span>' if key else ""
    return f'<article class="card ev"><h3>{k}{html.escape(text)}</h3><div class="body">{"".join(body)}</div></article>'


def kit_item(k):
    """'**A (Ask) 질문하기** — …' 한 줄을 글자 · 이름 · 설명으로 나눠 보여 준다."""
    m = re.match(r"\*\*([A-Z]) \((\w+)\) (.+?)\*\*\s*[—-]\s*(.*)$", k)
    if m:
        return (f'<li><span class="L">{m.group(1)}</span><div><b>{html.escape(m.group(3))}<small>{m.group(2)}</small></b>'
                f'<p>{inline(m.group(4))}</p></div></li>')
    return f'<li><span class="L"></span><div><p>{inline(k)}</p></div></li>'


def build_note(cfg, n, c):
    prefix = "../../"
    meta = (f'<p class="mt"><span class="tag">{age_label(cfg, c)} · {html.escape(sit_of(cfg, c)["label"])}</span>'
            f'<span class="qno">질문 {n["no"]}</span></p>')
    back = f'<a class="back" href="{prefix}">다른 질문 보기{icon("arrow")}</a>'
    if not c.get("published"):
        # 공개 날짜는 쓰지 않는다(10-31 질문002~050 공개 보류 — 정해지면 그때 공개로 바꾼다)
        body = f"""{prev_link(prefix)}<section class="top"><div class="in head">{meta}<h1 class="title">{inline(n['question'])}</h1>
<div class="status"><b>정리 중</b><p>휴먼쌤이 결론과 근거를 정리하고 있어요. 공개되면 이 주소에서 바로 읽으실 수 있어요.</p></div></div></section>
<div class="wrap">{back}</div>"""
        return page(prefix, f"{n['question']} — AI시대 부모백과", "준비 중", body)

    big, concl_html, today = split_conclusion(n)
    today = f'<div class="today"><b>오늘 해 볼 한 가지</b>{today}</div>' if today else ""
    groups, quotes, unknown, refs, loose = parse_evidence(n)
    ev = [ev_group_html(t, parts) for t, parts in groups]
    ev += [f'<div class="card unk"><b>아직 모르는 것</b><p>{u}</p></div>' for u in unknown]
    ev += [f'<div class="card prose">{b}</div>' for b in loose]
    if quotes:
        # 마지막 인용(한 줄 정리)만 큰 글씨
        ev.append('<div class="wrapup"><p class="lab">정리</p>' + "".join(f"<p>{q}</p>" for q in quotes[:-1])
                  + f'<p class="last">{quotes[-1]}</p></div>')
    # 구성 목록 첫 줄의 「자료 이름」 A4 n쪽. 은 바로 위 제목과 겹치므로 떼어 낸다
    kit_items = [re.sub(r"^「[^」]+」\s*A4\s*\d+쪽\.?\s*", "", k) for k in n.get("kit", [])]
    kit = "".join(kit_item(k) for k in kit_items if k)
    if c.get("nepcon_url"):
        cta = f'<a class="btn" href="{html.escape(c["nepcon_url"])}" rel="noopener">{icon("down")}활동지 받기</a>'
    else:
        cta = '<span class="btn off">활동지 준비 중</span>'
    # 쇼츠(H2)가 확정된 글만: shorts/NNN.mp4 + NNN.jpg(첫 화면)
    shorts = ""
    if c.get("shorts"):
        shorts = (f'<section class="shorts" aria-labelledby="shorts-h"><h2 id="shorts-h">1분 쇼츠로 보기</h2>'
                  f'<video controls playsinline preload="none" poster="{prefix}shorts/{n["no"]}.jpg" width="720" height="1280">'
                  f'<source src="{prefix}shorts/{n["no"]}.mp4" type="video/mp4"></video></section>')
    wb = '<p class="wb">이 실천 자료는 『어린이를 위한 AI시대 생각주도력 워크북(기초편)』에도 묶여 나올 예정이에요.</p>' if n.get("workbook") else ""
    toc = [("conclusion", "결론"), ("evidence", f"근거 · {len(groups)}가지"), ("practice", "실천 · 휴먼쌤 ACT")]
    if refs:
        toc.append(("refs", "참고자료"))
    toc_html = "".join(f'<a href="#{a}"><span>{i}</span>{t}</a>' for i, (a, t) in enumerate(toc, 1))
    byline = f"정리 휴먼쌤 김수현 · 근거 {len(groups)}가지" + (f" · 참고자료 {len(refs)}편" if refs else "")
    refs_html = (f'<section id="refs" aria-labelledby="refs-h"><h2 class="refs-h" id="refs-h">참고자료</h2>'
                 f'<ol class="refs">{"".join(f"<li>{r}</li>" for r in refs)}</ol></section>') if refs else ""
    body = f"""{prev_link(prefix)}<section class="top"><div class="in head" id="conclusion">{meta}<h1 class="title">{inline(n['question'])}</h1>
<p class="byline">{byline}</p>
<div class="summary"><h2 class="lab">결론</h2><p class="big">{html.escape(big)}</p>{''.join(concl_html)}{today}</div>
<nav class="card toc" aria-label="이 글의 차례">{toc_html}</nav></div></section>
<div class="wrap">
{shorts}
<section id="evidence" aria-labelledby="ev-h"><h2 id="ev-h">근거</h2>{''.join(ev)}</section>
<section id="practice" aria-labelledby="pr-h"><h2 id="pr-h">오늘 저녁 바로 해 보려면</h2><p class="sub">휴먼쌤 ACT 3단계</p>
<ol class="card acts">{kit}</ol>
<div class="kit"><div class="nm"><b>{html.escape(n['material'])}</b><span>휴먼쌤 ACT 활동지 · PDF {n['pages']}쪽</span></div>{cta}</div>{wb}</section>
{refs_html}
{back}
</div>"""
    return page(prefix, f"{n['question']} — AI시대 부모백과", big, body)


PREV_JS = ("if(document.referrer&&document.referrer.indexOf(location.host)>-1&&history.length>1)"
           "{history.back();return false}")


def prev_link(href):
    """왼쪽 위 '이전으로'. 이 사이트 안에서 왔으면 뒤로, 바로 들어왔으면 href로."""
    return f'<div class="prevbar"><div class="in"><a class="prev" href="{href}" onclick="{PREV_JS}">{icon("back")}이전으로</a></div></div>'


def q_card(prefix, cfg, n, c):
    """키워드 쪽의 질문 카드 한 장: 번호 · 상태 · 질문(공개 글은 결론 첫 문장까지)."""
    live = c.get("published")
    lead = ""
    if live and n.get("conclusion"):
        big, _, _ = split_conclusion(n)
        lead = f'<p class="ql">{html.escape(big)}</p>'
    st = '<span class="st on">읽기</span>' if live else '<span class="st">정리 중</span>'
    go = f'<span class="go">결론 · 근거 · 실천 읽기{icon("arrow")}</span>' if live else ""
    return (f'<li><a class="card qc{" live" if live else ""}" href="{prefix}q/{n["no"]}/"><span class="qm"><span class="qno">질문 {n["no"]}</span>{st}</span>'
            f'<b>{inline(n["question"])}</b>{lead}{go}</a></li>')


def build_situation(cfg, notes, s, nos):
    prefix = "../../"
    cards = "".join(q_card(prefix, cfg, notes[no], cfg["notes"][no]) for no in nos)
    n_live = sum(1 for no in nos if cfg["notes"][no].get("published"))
    body = f"""{prev_link(prefix)}
<section class="top"><div class="in head"><p class="mt"><span class="tag">키워드</span></p><h1 class="title">{html.escape(s.get("kw") or s["label"])}</h1>
<p class="byline">{html.escape(s["label"])} · 질문 {len(nos)}개 · 읽기 {n_live}편</p></div></section>
<div class="wrap"><section aria-label="이 키워드의 질문"><ul class="qcs">{cards}</ul></section>
<a class="back" href="{prefix}">처음으로{icon("arrow")}</a></div>"""
    return page(prefix, f"{s['label']} — AI시대 부모백과", "이 상황에 맞는 질문과 답", body)


def build_about():
    prefix = "../"
    body = f"""<section class="top"><div class="in head"><p class="mt"><span class="tag">소개</span></p><h1 class="title">AI시대 부모백과</h1></div></section>
<div class="wrap">
<section class="card prose"><h2>부모의 질문에 답하는 AI 교육 가이드</h2>
<p>아이와 AI 사이에서 부모님이 실제로 묻는 질문 하나에 결론과 근거로 답합니다. 결론 끝에는 오늘 해 볼 한 가지를, 근거 끝에는 아직 모르는 것을 함께 적어요.</p>
<p>결론과 근거는 누구나 무료로 읽을 수 있어요. 아이와 바로 해 볼 수 있는 실천 자료는 네이버 프리미엄콘텐츠에서 단품으로 만나실 수 있어요. 광고는 붙이지 않아요.</p></section>
<section class="card prose"><h2>답하는 사람 · 휴먼쌤 김수현</h2><p>현직 초등교사이자 아빠입니다.</p></section>
<a class="back" href="../">처음으로{icon("arrow")}</a>
</div>"""
    return page(prefix, "소개 — AI시대 부모백과", "부모의 질문에 답하는 AI 교육 가이드, AI시대 부모백과 소개", body)


def cmd_build():
    cfg = load_config()
    notes = json.loads(DATA.read_text(encoding="utf-8"))
    if OUT.exists():
        for p in OUT.iterdir():
            if p.name in ("CNAME", ".nojekyll"):
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUT.mkdir(exist_ok=True)
    for a in ASSETS.iterdir():
        shutil.copy(a, OUT / a.name)
    if SHORTS.exists():
        shutil.copytree(SHORTS, OUT / "shorts")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    def write(rel, text):
        p = OUT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    write("index.html", build_index(cfg, notes))
    write("about/index.html", build_about())
    for no, c in cfg["notes"].items():
        if no in notes:
            write(f"q/{no}/index.html", build_note(cfg, notes[no], c))
    for s in cfg["situations"]:
        nos = [no for no, c in cfg["notes"].items() if c["situation"] == s["id"] and no in notes]
        if nos:
            write(f"s/{s['id']}/index.html", build_situation(cfg, notes, s, nos))
    nf = page("/", "찾는 페이지가 없어요 — AI시대 부모백과", "",
              f'<section class="top"><div class="in head"><h1 class="title">찾는 페이지가 없어요</h1></div></section><div class="wrap"><a class="back" href="/">처음으로{icon("arrow")}</a></div>')
    write("404.html", nf)
    print("docs/ 만듦:", sum(1 for _ in OUT.rglob("*.html")), "쪽")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "import":
        cmd_import(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "build":
        cmd_build()
    else:
        print(__doc__)
