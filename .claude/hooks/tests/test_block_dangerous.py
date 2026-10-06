#!/usr/bin/env python3
"""차단 훅(block-dangerous.sh) 시험.

실행:  python3 .claude/hooks/tests/test_block_dangerous.py
다른 대상을 시험하려면 HOOK 환경변수에 실행 파일 경로를 준다.

위험한 명령 문자열은 모두 이 파일과 block-dangerous.cases 안에만 있다.
이 저장소의 차단 훅은 Bash 명령 문자열을 검사하므로, 시험 명령을 터미널에 직접 치면
그 Bash 호출 자체가 막힌다. 반드시 이 스크립트로 시험한다.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("HOOK") or os.path.join(HERE, "..", "block-dangerous.sh")
CASES = os.path.join(HERE, "block-dangerous.cases")

# 한 줄 목록 파일에 넣기 어려운 경우들: (기대값, 명령, 설명)
MULTILINE = [
    ("deny", "ls\nrm -rf /", "두 번째 줄의 위험 명령"),
    ("deny", "rm -rf \\\n  /", "줄 이음(\\) 뒤의 대상"),
    ("allow", "git commit -F - <<'EOF'\nfix: rm -rf / 우회 차단\ngit reset --hard 설명\nEOF", "따옴표 heredoc 본문은 글자일 뿐"),
    ("allow", "cat <<EOF\nrm -rf /\nEOF", "따옴표 없는 heredoc이라도 본문 자체는 실행되지 않음"),
    ("deny", "cat <<EOF\n$(rm -rf ~)\nEOF", "따옴표 없는 heredoc 안의 $(...)는 실행됨"),
    ("deny", "cat <<'EOF'\nhello\nEOF\nrm -rf /", "heredoc이 끝난 뒤의 위험 명령"),
    ("allow", "python3 - <<'PY'\nimport os\nprint('git clean -fd')\nPY", "따옴표 heredoc 안의 파이썬 코드"),
]


def run_hook(payload):
    proc = subprocess.run([HOOK] if os.access(HOOK, os.X_OK) and HOOK.endswith(".sh") else [sys.executable, "-I", HOOK],
                          input=payload, capture_output=True, text=True, timeout=10)
    out = proc.stdout.strip()
    if not out:
        return "allow", proc.returncode, ""
    try:
        spec = json.loads(out).get("hookSpecificOutput", {})
        return spec.get("permissionDecision", "allow"), proc.returncode, spec.get("permissionDecisionReason", "")
    except ValueError:
        return "invalid-output", proc.returncode, out


def check(expect, command, label, cwd=None):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd or os.getcwd()})
    got, rc, reason = run_hook(payload)
    ok = got == expect and rc == 0
    return ok, f"{'ok  ' if ok else 'FAIL'} expect={expect:<5} got={got:<5} rc={rc}  {label}" + ("" if ok else f"\n      reason={reason!r}")


def load_cases():
    with open(CASES, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            expect, command = line.split("\t", 1)
            yield expect, command, command


def branch_cases():
    """git push -f 처럼 refspec이 없어 현재 브랜치로 판단하는 경우."""
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for branch, expect in (("main", "deny"), ("feature/x", "allow")):
            repo = os.path.join(tmp, branch.replace("/", "_"))
            subprocess.run(["git", "init", "-q", "-b", branch, repo], check=True)
            for cmd in ("git push -f", "git push --force origin", "git push -f origin HEAD"):
                results.append(check(expect, cmd, f"[현재 브랜치 {branch}] {cmd}", cwd=repo))
    return results


def input_cases():
    """훅 입력 자체가 이상한 경우."""
    results = []
    for payload, expect, label in (
        ("not json", "deny", "JSON이 아닌 입력"),
        ("[]", "deny", "객체가 아닌 JSON"),
        (json.dumps({"tool_name": "Bash", "tool_input": {"command": ""}}), "allow", "빈 명령"),
        (json.dumps({"tool_name": "Bash", "tool_input": {}}), "allow", "command 필드 없음"),
    ):
        got, rc, _ = run_hook(payload)
        ok = got == expect and rc == 0
        results.append((ok, f"{'ok  ' if ok else 'FAIL'} expect={expect:<5} got={got:<5} rc={rc}  [입력] {label}"))
    return results


def main():
    results = [check(e, c, label) for e, c, label in load_cases()]
    results += [check(e, c, f"[여러 줄] {label}") for e, c, label in MULTILINE]
    results += branch_cases()
    results += input_cases()

    verbose = "-v" in sys.argv
    for ok, line in results:
        if verbose or not ok:
            print(line)
    failed = sum(1 for ok, _ in results if not ok)
    deny_total = sum(1 for _, line in results if "expect=deny" in line)
    print(f"\n대상: {os.path.relpath(HOOK)}")
    print(f"전체 {len(results)}개 (막아야 함 {deny_total}, 통과해야 함 {len(results) - deny_total}) 중 실패 {failed}개")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
