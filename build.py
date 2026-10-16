"""AI시대 부모백과(aiparentbook.com) 정적 사이트 만들기.

  python build.py import <bundle.json>   연재부 묶음에서 공개해도 되는 글만 data/notes.json으로 가져온다
  python build.py build                  data/notes.json + config.json -> docs/ (GitHub Pages가 보는 폴더)

- 글 문장은 연재부 정본 그대로 쓴다(손으로 옮기지 않는다).
- config.json에서 published가 false인 글은 질문·공개일만 가져온다(본문은 저장소에 넣지 않는다).
- 모든 링크는 상대 경로라 github.io 하위 주소와 aiparentbook.com 루트 양쪽에서 돈다.
"""
import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "notes.json"
OUT = ROOT / "docs"
ASSETS = ROOT / "assets"
WEEK = "월화수목금토일"


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


def fmt_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}월 {d.day}일({WEEK[d.weekday()]})"


# ---------------------------------------------------------------- page shell
def page(prefix, title, desc, body, canonical=""):
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
<meta name="theme-color" content="#EEF3EE">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="bar"><a class="logo" href="{prefix}">AI시대 <b>부모백과</b></a><a class="by" href="{prefix}about/">휴먼쌤</a></header>
<main class="pad">
{body}
</main>
<footer class="foot"><p>AI시대 부모백과 · 질문에 답하는 사람 휴먼쌤 김수현</p><p>광고 없이 운영합니다. 결론과 근거는 누구나 무료로 읽을 수 있어요.</p></footer>
</body>
</html>
"""


# ---------------------------------------------------------------- pages
def note_card_html(prefix, n, c, cfg):
    href = f"{prefix}q/{n['no']}/"
    if c.get("published"):
        return f'<a class="row" href="{href}"><b>{inline(n["question"])}</b><span>{n["no"]}</span></a>'
    return f'<a class="row soon" href="{href}"><b>{inline(n["question"])}</b><span>준비 중</span></a>'


def build_index(cfg, notes):
    sit = {s["id"]: s for s in cfg["situations"]}
    by_sit = {}
    for no, c in cfg["notes"].items():
        if no in notes:
            by_sit.setdefault(c["situation"], []).append(no)
    age_btns = "".join(
        f'<button type="button" data-age="{a["id"]}" aria-pressed="{"true" if a["id"] == "elementary" else "false"}">{a["label"]}</button>'
        for a in cfg["ages"])
    tiles = []
    for i, s in enumerate(cfg["situations"]):
        nos = by_sit.get(s["id"], [])
        if not nos:
            continue
        ages = sorted({a for no in nos for a in cfg["notes"][no]["ages"]})
        href = f"q/{nos[0]}/" if len(nos) == 1 else f"s/{s['id']}/"
        live = [no for no in nos if cfg["notes"][no].get("published")]
        sub = " · ".join(live) if live else "준비 중"
        tiles.append(f'<a class="tile{" hot" if i == 0 else ""}" href="{href}" data-ages="{" ".join(ages)}"><b>{html.escape(s["label"])}</b><small>{sub}</small></a>')
    order = sorted(cfg["notes"], key=lambda k: cfg["notes"][k]["release"], reverse=True)
    latest = [no for no in order if cfg["notes"][no].get("published") and no in notes][:3]
    upcoming = sorted([no for no in cfg["notes"] if not cfg["notes"][no].get("published") and no in notes],
                      key=lambda k: cfg["notes"][k]["release"])
    rows = "".join(note_card_html("", notes[no], cfg["notes"][no], cfg) for no in (latest or upcoming))
    list_title = "새로 올라온 질문" if latest else "준비 중인 질문"
    body = f"""<h1 class="hello">우리 아이, 지금<br>어떤 상황인가요?</h1>
<section class="pick" aria-label="아이 나이"><h2>아이 나이</h2><div class="seg" id="ages">{age_btns}</div></section>
<section class="tiles" id="tiles">{''.join(tiles)}</section>
<p class="empty" id="empty" hidden>이 나이에 맞는 질문은 아직 없어요. 지금은 초등 자녀를 둔 부모님 질문부터 답하고 있어요.</p>
<section class="pick"><h2>{list_title}</h2><div class="rows">{rows}</div></section>
<script>
(function(){{var KEY='apb-age',btns=[].slice.call(document.querySelectorAll('#ages button')),tiles=[].slice.call(document.querySelectorAll('#tiles .tile')),empty=document.getElementById('empty');
function set(age){{var shown=0;btns.forEach(function(b){{b.setAttribute('aria-pressed',b.dataset.age===age?'true':'false')}});tiles.forEach(function(t){{var ok=(' '+t.dataset.ages+' ').indexOf(' '+age+' ')>-1;t.hidden=!ok;if(ok)shown++}});empty.hidden=shown>0;try{{localStorage.setItem(KEY,age)}}catch(e){{}}}}
btns.forEach(function(b){{b.addEventListener('click',function(){{set(b.dataset.age)}})}});var saved=null;try{{saved=localStorage.getItem(KEY)}}catch(e){{}}set(saved||'elementary');}})();
</script>"""
    return page("", "AI시대 부모백과 — 부모의 질문에 답하는 AI 교육 가이드",
                "숙제, 첫 사용, 계정, AI 답 믿기까지. 아이와 AI 사이에서 부모님이 실제로 묻는 질문에 결론과 근거로 답합니다.", body)


def build_note(cfg, n, c):
    prefix = "../../"
    sit = next(s for s in cfg["situations"] if s["id"] == c["situation"])
    ages = " · ".join(a["label"] for a in cfg["ages"] if a["id"] in c["ages"])
    crumb = f'<p class="crumb">{ages} · {html.escape(sit["label"])} · {n["no"]}</p>'
    if not c.get("published"):
        body = f"""{crumb}<h1 class="q">{inline(n['question'])}</h1>
<div class="ans soon-box"><div class="big">준비 중이에요</div><p>휴먼쌤이 결론과 근거를 정리하고 있어요. 공개되면 이 주소에서 바로 읽으실 수 있어요.</p></div>
<p><a class="back" href="{prefix}">다른 질문 보기</a></p>"""
        return page(prefix, f"{n['question']} — AI시대 부모백과", "준비 중", body)

    # 결론 첫 문장을 큰 글씨로 떼어 내고, 나머지는 정본 그대로 잇는다
    raw = n["conclusion"].strip()
    m = re.match(r"(.+?[.?!])\s+(.*)$", raw, re.S)
    big, rest = (m.group(1), m.group(2)) if m else (raw, "")
    concl = md_blocks(rest) if rest else []
    concl_html = []
    today = ""
    for b in concl:
        if isinstance(b, tuple) and b[0] == "today":
            today = f'<div class="today"><b>오늘 해 볼 한 가지</b>{lead_rest(b[1], "**오늘 해 볼 한 가지**")}</div>'
        elif isinstance(b, str):
            concl_html.append(b)
    # 굵은 제목 덩어리(<b>…</b>만 있는 줄)부터 다음 제목·인용구 전까지를 한 접이 칸으로 묶는다
    ev_html, group = [], None

    def close():
        nonlocal group
        if group:
            title, parts = group
            ev_html.append(f'<details{" open" if len(ev_html) == 0 else ""}><summary>{title}</summary>{"".join(parts)}</details>')
        group = None
    for b in md_blocks(n["evidence"]):
        if isinstance(b, tuple) and b[0] == "unknown":
            close()
            ev_html.append(f'<details open><summary>아직 모르는 것</summary><p>{lead_rest(b[1], "**아직 모르는 것**")}</p></details>')
        elif isinstance(b, tuple) and b[0] == "quote":
            close()
            ev_html.append(f'<blockquote class="sum">{b[1]}</blockquote>')
        elif isinstance(b, str):
            head = re.match(r"<p><b>([^<]+)</b>(?:<br>|\s+)?(.*)</p>$", b, re.S)
            if head:
                close()
                group = (head.group(1), [f"<p>{head.group(2).strip()}</p>"] if head.group(2).strip() else [])
            elif group:
                group[1].append(b)
            else:
                ev_html.append(b)
    close()
    # 구성 목록 첫 줄의 「자료 이름」 A4 n쪽. 은 바로 위 제목과 겹치므로 떼어 낸다
    kit_items = [re.sub(r"^「[^」]+」\s*A4\s*\d+쪽\.?\s*", "", k) for k in n.get("kit", [])]
    kit = "".join(f'<li>{inline(k)}</li>' for k in kit_items if k)
    if c.get("nepcon_url"):
        cta = f'<a class="btn" href="{html.escape(c["nepcon_url"])}" rel="noopener">네이버 프리미엄콘텐츠에서 활동지 받기</a>'
    else:
        cta = '<p class="btn off">네이버 프리미엄콘텐츠 단품 · 링크 준비 중</p>'
    wb = '<p class="wb">이 실천 자료는 『어린이를 위한 AI시대 생각주도력 워크북(기초편)』에도 묶여 나올 예정이에요.</p>' if n.get("workbook") else ""
    body = f"""{crumb}<h1 class="q">{inline(n['question'])}</h1>
<nav class="tabs" aria-label="이 글의 차례"><a href="#conclusion">결론</a><a href="#evidence">근거</a><a href="#practice">실천</a></nav>
<section class="ans" id="conclusion"><h2 class="sr">결론</h2><div class="big">{html.escape(big)}</div>{''.join(concl_html)}</section>
{today}
<section class="evs" id="evidence"><h2>근거</h2>{''.join(ev_html)}</section>
<section class="paid" id="practice"><h2>오늘 저녁 바로 해 보려면</h2><p class="kitname">휴먼쌤 ACT 3단계 · 활동지 「{html.escape(n['material'])}」 PDF {n['pages']}쪽</p><ul>{kit}</ul>{cta}{wb}</section>
<p><a class="back" href="{prefix}">다른 질문 보기</a></p>"""
    return page(prefix, f"{n['question']} — AI시대 부모백과", big, body)


def build_situation(cfg, notes, s, nos):
    prefix = "../../"
    rows = "".join(note_card_html(prefix, notes[no], cfg["notes"][no], cfg) for no in nos)
    body = f'<p class="crumb">상황</p><h1 class="q">{html.escape(s["label"])}</h1><section class="pick"><div class="rows">{rows}</div></section><p><a class="back" href="{prefix}">처음으로</a></p>'
    return page(prefix, f"{s['label']} — AI시대 부모백과", "이 상황에 맞는 질문과 답", body)


def build_about():
    prefix = "../"
    body = """<p class="crumb">소개</p><h1 class="q">AI시대 부모백과</h1>
<section class="ans"><div class="big">부모의 질문에 답하는 AI 교육 가이드</div>
<p>아이와 AI 사이에서 부모님이 실제로 묻는 질문 하나에 결론과 근거로 답합니다. 결론 끝에는 오늘 해 볼 한 가지를, 근거 끝에는 아직 모르는 것을 함께 적어요.</p>
<p>결론과 근거는 누구나 무료로 읽을 수 있어요. 아이와 바로 해 볼 수 있는 실천 자료는 네이버 프리미엄콘텐츠에서 단품으로 만나실 수 있어요. 광고는 붙이지 않아요.</p></section>
<section class="ans"><div class="big">답하는 사람 · 휴먼쌤 김수현</div><p>현직 초등교사이자 아빠입니다.</p></section>
<p><a class="back" href="../">처음으로</a></p>"""
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
        if len(nos) > 1:
            write(f"s/{s['id']}/index.html", build_situation(cfg, notes, s, nos))
    nf = page("/", "찾는 페이지가 없어요 — AI시대 부모백과", "", '<h1 class="q">찾는 페이지가 없어요</h1><p><a class="back" href="./">처음으로</a></p>')
    write("404.html", nf)
    print("docs/ 만듦:", sum(1 for _ in OUT.rglob("*.html")), "쪽")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "import":
        cmd_import(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "build":
        cmd_build()
    else:
        print(__doc__)
