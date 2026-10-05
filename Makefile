# 확인 명령의 표준 이름. 검사 내용은 scripts/check 한 곳에만 둔다.
# AI 도구·평가 도구가 make check를 확인 명령으로 알아보므로 scripts/check 대신 이걸로 부른다.
.PHONY: check
check:
	scripts/check
