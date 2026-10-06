#!/usr/bin/env bash
# PostToolUse(Write|Edit) 훅: 파일이 쓰여진 뒤 자동으로 포맷한다.
# prettier가 처리하는 확장자만 대상으로 하고, 실패해도 Claude의 작업을 막지 않는다.
set -u

file="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')"
[ -z "$file" ] || [ ! -f "$file" ] && exit 0

case "$file" in
  *.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs|*.json|*.css|*.scss|*.md|*.yaml|*.yml|*.html)
    if command -v prettier >/dev/null 2>&1; then
      prettier --write --log-level silent "$file" >/dev/null 2>&1 || true
    elif command -v npx >/dev/null 2>&1; then
      npx --no-install prettier --write --log-level silent "$file" >/dev/null 2>&1 || true
    fi
    ;;
esac

exit 0
