#!/usr/bin/env bash
# PreToolUse(Bash) 훅: 위험한 셸 명령을 실행 전에 차단한다.
# 실제 판단은 같은 폴더의 block_dangerous.py 가 한다.
# 따옴표 안의 글자와 실제 명령을 구분하려면 셸처럼 토큰으로 나눠야 해서 파이썬을 쓴다.
# 시험: python3 .claude/hooks/tests/test_block_dangerous.py

script="${BASH_SOURCE[0]}"
dir="${script%/*}"
[ "$dir" = "$script" ] && dir="."

for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 \
    && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    exec "$py" -I "$dir/block_dangerous.py"
  fi
done

# 파이썬 3.9 이상이 없으면 검사할 수 없다.
# 모든 Bash 호출을 막아 버리지 않도록 통과시키되, 훅이 꺼져 있다는 경고를 띄운다.
printf '%s\n' '{"systemMessage":"경고: Python 3.9 이상을 찾을 수 없어 위험 명령 차단 훅이 동작하지 않습니다."}'
exit 0
