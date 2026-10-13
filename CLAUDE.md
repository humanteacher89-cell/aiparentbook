# AI시대 부모사전 (aiparentbook.com)

부모의 질문에 답하는 AI 교육 가이드. 정적 사이트, GitHub Pages(main 브랜치 `/docs`)로 공개한다.

## 구조
- `config.json` — 나이·상황 목록, 글마다 공개 여부(`published`)·공개일·나이·상황·네프콘 링크
- `data/notes.json` — 글 문장. 공개된 글만 본문이 들어 있다(공개 전 글은 질문·공개일만)
- `build.py` — `python build.py build`로 `docs/`를 다시 만든다. `docs/`를 손으로 고치지 않는다
- `assets/` — style.css, favicon.svg (build 때 docs로 복사)

## 규칙
- 글 문장은 정본 그대로. 고칠 문장이 있으면 정본을 고친 뒤 다시 가져온다.
- 개인정보를 받는 기능(회원가입·댓글·분석 도구)과 광고는 넣지 않는다.
- 모든 링크는 상대 경로(github.io 하위 주소와 도메인 루트 양쪽에서 돌게).

## 지금 상태와 남은 일 (2026-10-13)
- 첫 화면(나이 고르기 + 상황 타일)·글 화면(결론·근거·실천)·상황별 목록·소개 완성. 글 001~005는 아직 공개 전이라 '공개 예정'으로만 보인다.
- 글을 공개할 때: config.json의 그 글 `published`를 true로 바꾸고, 본문 가져오기 → build → 커밋.
- 남은 것: 네프콘 글 주소(`nepcon_url`), 도메인 연결(CNAME), AI 도움 표시 문구.
