# -*- coding: utf-8 -*-
"""
3중 소스 동기화 빌드 스크립트.

문제: persistence_coach_demo.html은 브라우저에서 바로 열리는 정적 파일이라
Python(dialogue_layer.py)을 import할 수 없다 — 그래서 프롬프트 텍스트를
JS 문자열로 손으로 복제해왔고, 이게 코퍼스/파이썬/HTML 3중 소스 동기화
문제를 만들었다 (예: "지켜보자고" vs "지켜보자며" 처럼 미묘하게 갈라짐).

해결: dialogue_layer.py의 RULES_TEXT / GUARDRAIL_TEXT / parallel_triggers_text()를
정본으로 삼고, 이 스크립트가 HTML의 AUTOGEN 마커 사이 내용을 그걸로 덮어쓴다.

사용법:
    coaching_corpus_v1.md 또는 dialogue_layer.py의 텍스트를 고친 뒤,
    $ python3 build_demo.py
    → persistence_coach_demo.html의 RULES/GUARDRAIL/PARALLEL_TRIGGERS가 갱신됨
    → 그 다음 validate_core.py를 다시 돌려 회귀 테스트 확인
"""
import re
from dialogue_layer import RULES_TEXT, GUARDRAIL_TEXT, parallel_triggers_text

DEMO_PATH = "persistence_coach_demo.html"


def _js_escape(text: str) -> str:
    """JS 템플릿 리터럴(백틱 문자열) 안에 안전하게 넣기 위한 최소 이스케이프."""
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def replace_block(html: str, marker: str, value: str) -> str:
    pattern = re.compile(
        rf"(// AUTOGEN:{marker}:BEGIN\nconst {marker} = `)(.*?)(`;\n// AUTOGEN:{marker}:END)",
        re.S,
    )
    if not pattern.search(html):
        raise RuntimeError(
            f"'{marker}' AUTOGEN 마커를 HTML에서 못 찾음 — 데모 구조가 바뀌었는지 확인 필요"
        )
    escaped = _js_escape(value)
    return pattern.sub(lambda m: m.group(1) + escaped + m.group(3), html)


def main(path: str = DEMO_PATH):
    html = open(path, encoding="utf-8").read()
    before = html
    html = replace_block(html, "RULES", RULES_TEXT)
    html = replace_block(html, "GUARDRAIL", GUARDRAIL_TEXT)
    html = replace_block(html, "PARALLEL_TRIGGERS", parallel_triggers_text())
    changed = html != before
    open(path, "w", encoding="utf-8").write(html)
    print(f"build_demo.py: RULES/GUARDRAIL/PARALLEL_TRIGGERS 갱신 완료"
          f" ({'변경 있음' if changed else '변경 없음 — 이미 동기화된 상태'})")


if __name__ == "__main__":
    main()
