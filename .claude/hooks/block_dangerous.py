#!/usr/bin/env python3
"""PreToolUse(Bash) 훅 본체: 위험한 셸 명령을 실행 전에 차단한다.

block-dangerous.sh 가 이 파일을 실행한다. stdin 으로 훅 입력 JSON 을 받고,
막아야 하면 permissionDecision=deny JSON 을 출력한다. 통과면 아무것도 출력하지 않는다.

정규식으로 명령 문자열 전체를 훑지 않고, 셸처럼 토큰으로 나눈 뒤
"명령 위치"에 있는 프로그램과 그 인자만 검사한다. 그래서
- 따옴표 안의 글자(커밋 메시지, echo 인자)는 오탐하지 않고
- 옵션 순서·대소문자·분리(-r -f, -Rf, --recursive)에도 속지 않는다.
"""

import json
import os
import re
import shlex
import subprocess
import sys

MAIN_BRANCHES = {"main", "master"}
SAFE_DEVICE = re.compile(r"^/dev/(null|zero|full|random|urandom|stdout|stderr|tty|fd/\d+)$")
MAX_DEPTH = 5

REASONS = {
    "rm": "차단됨: 루트(/)나 홈(~) 디렉터리를 통째로 지우는 명령은 허용되지 않습니다.",
    "push_force": "차단됨: main/master 브랜치로의 강제 푸시는 허용되지 않습니다.",
    "push_delete": "차단됨: 원격 main/master 브랜치를 지우는 푸시는 허용되지 않습니다.",
    "clean": "차단됨: git clean -f 는 추적되지 않은 파일을 되돌릴 수 없게 지웁니다. 먼저 git clean -n 으로 확인하세요.",
    "reset": "차단됨: git reset --hard 는 커밋하지 않은 변경을 잃게 하므로 허용되지 않습니다.",
    "mkfs": "차단됨: 파일시스템을 새로 만드는 mkfs 명령은 허용되지 않습니다.",
    "dd": "차단됨: 장치(/dev/...)에 직접 쓰는 dd 명령은 허용되지 않습니다.",
    "unparsable": "차단됨: 명령의 따옴표 짝이 맞지 않아 안전한지 판단할 수 없습니다. 명령을 고쳐 다시 실행하세요.",
    "bad_input": "차단됨: 훅 입력을 읽을 수 없어 안전을 위해 막았습니다.",
}

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "{", "}", "time"}
HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
SUBSTITUTIONS = [
    re.compile(r"\$\(([^()]*)\)"),  # $(...)
    re.compile(r"[<>]\(([^()]*)\)"),  # <(...) >(...)
    re.compile(r"`([^`]*)`"),  # `...`
]


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


# ---------------------------------------------------------------- 전처리


def split_heredocs(text):
    """heredoc 본문을 떼어 낸다. (명령 부분, 따옴표 없는 heredoc 본문 목록)을 돌려준다.

    따옴표 없는 heredoc(<<EOF)은 본문 안의 $(...) 가 실제로 실행되므로 따로 돌려준다.
    따옴표 있는 heredoc(<<'EOF')의 본문은 그냥 글자이므로 버린다.
    """
    command_lines, expanding_bodies = [], []
    pending = []  # (구분자, 탭 허용 여부, 확장 여부, 본문 줄들)
    for line in text.split("\n"):
        if pending:
            delim, dash, expands, body = pending[0]
            if (line.lstrip("\t") if dash else line) == delim:
                if expands:
                    expanding_bodies.append("\n".join(body))
                pending.pop(0)
            else:
                body.append(line)
            continue
        command_lines.append(line)
        for m in HEREDOC.finditer(line):
            pending.append((m.group(3), m.group(1) == "-", m.group(2) == "", []))
    for _, _, expands, body in pending:  # 닫히지 않은 heredoc
        if expands:
            expanding_bodies.append("\n".join(body))
    return "\n".join(command_lines), expanding_bodies


def substitutions(text):
    """$(...), `...`, <(...) 안의 명령을 모두 꺼낸다 (중첩은 안쪽부터)."""
    found = []
    for _ in range(MAX_DEPTH):
        changed = False
        for pattern in SUBSTITUTIONS:
            for m in pattern.finditer(text):
                found.append(m.group(1))
            new = pattern.sub(" ", text)
            changed = changed or new != text
            text = new
        if not changed:
            break
    return found


def segments(text):
    """명령 문자열을 ; && || | & ( ) 기준으로 나눠 단순 명령의 인자 목록들을 돌려준다."""
    text = text.replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)  # 따옴표 짝이 안 맞으면 ValueError

    result, current, skip_next = [], [], False
    for tok in tokens:
        if skip_next:  # 리디렉션 대상(파일 이름)은 인자가 아니다
            skip_next = False
            continue
        if tok and set(tok) <= set("<>&|") and ("<" in tok or ">" in tok):
            if current and current[-1].isdigit():  # 2>&1 의 2
                current.pop()
            skip_next = True
            continue
        if tok and set(tok) <= set(";&|()"):
            if current:
                result.append(current)
            current = []
            continue
        if tok == "$":  # $( 의 $
            continue
        current.append(tok)
    if current:
        result.append(current)
    return result


# ---------------------------------------------------------------- 명령 앞부분 정리


def strip_prefixes(argv):
    """sudo, env, 변수 대입, 셸 키워드처럼 실제 프로그램 앞에 오는 것을 걷어 낸다."""
    argv = list(argv)
    while argv:
        head = argv[0]
        name = os.path.basename(head)
        if head in KEYWORDS:
            argv.pop(0)
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", head):
            argv.pop(0)
        elif name in ("sudo", "doas"):
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                opt = argv.pop(0)
                if opt in ("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T") and argv:
                    argv.pop(0)
        elif name == "env":
            argv.pop(0)
            while argv and (argv[0].startswith("-") or "=" in argv[0]):
                opt = argv.pop(0)
                if opt in ("-u", "-C", "-S") and argv:
                    argv.pop(0)
        elif name in ("nohup", "command", "exec", "builtin", "stdbuf", "ionice"):
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                argv.pop(0)
        elif name == "nice":
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                opt = argv.pop(0)
                if opt == "-n" and argv:
                    argv.pop(0)
        elif name == "timeout":
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                opt = argv.pop(0)
                if opt in ("-s", "-k", "--signal", "--kill-after") and argv:
                    argv.pop(0)
            if argv:
                argv.pop(0)  # 시간 값
        else:
            break
    return argv


def short_flags(arg):
    """'-rf' 같은 짧은 옵션 묶음이면 글자 집합을, 아니면 빈 집합을 돌려준다."""
    if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
        return set(arg[1:])
    return set()


# ---------------------------------------------------------------- 명령별 검사


def home_paths():
    paths = {"~", "$HOME", "${HOME}"}
    for value in (os.environ.get("HOME"), os.path.expanduser("~")):
        if value and value != "/":
            paths.add(value.rstrip("/"))
    return paths


def is_root_or_home(target):
    t = re.sub(r"/+", "/", target.strip())
    if t in ("/", "/*", "/.", "/.*"):
        return True
    for home in home_paths():
        if t in (home, home + "/", home + "/*", home + "/.", home + "/.*"):
            return True
    return False


def check_rm(args):
    recursive, targets, after_dashdash = False, [], False
    for a in args:
        if not after_dashdash and a == "--":
            after_dashdash = True
        elif not after_dashdash and a.startswith("--"):
            recursive = recursive or a == "--recursive"
        elif not after_dashdash and short_flags(a):
            recursive = recursive or bool(short_flags(a) & {"r", "R"})
        else:
            targets.append(a)
    if recursive and any(is_root_or_home(t) for t in targets):
        return REASONS["rm"]
    return None


def current_branch(cwd):
    """현재 브랜치 이름. 커밋이 하나도 없는 저장소에서도 동작하도록 symbolic-ref 를 쓴다."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd or ".", "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def check_git_push(args, cwd):
    force = delete = False
    whole_repo = False
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            i += 2
            continue
        if a in ("--force", "--force-if-includes") or a.startswith("--force-with-lease"):
            force = True
        elif a == "--delete":
            delete = True
        elif a in ("--all", "--mirror", "--branches"):
            whole_repo = True
        elif a.startswith("--"):
            pass
        elif short_flags(a):
            force = force or "f" in short_flags(a)
            delete = delete or "d" in short_flags(a)
        else:
            positional.append(a)
        i += 1

    refspecs = positional[1:]
    for spec in refspecs:
        plus = spec.startswith("+")
        spec = spec.lstrip("+")
        src, dst = spec.split(":", 1) if ":" in spec else (spec, spec)
        dst = dst.removeprefix("refs/heads/")
        if dst == "HEAD":  # git push -f origin HEAD 는 현재 브랜치로 푸시
            dst = current_branch(cwd) or dst
        if dst in MAIN_BRANCHES:
            if delete or (":" in spec and src == ""):
                return REASONS["push_delete"]
            if force or plus:
                return REASONS["push_force"]

    if force and not refspecs:
        if whole_repo or current_branch(cwd) in MAIN_BRANCHES:
            return REASONS["push_force"]
    return None


def check_git(args, cwd):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            cwd = os.path.join(cwd or ".", args[i + 1])
            i += 2
        elif a in ("-c", "--git-dir", "--work-tree", "--namespace", "--config-env"):
            i += 2
        else:
            i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1 :]

    if sub == "push":
        return check_git_push(rest, cwd)
    if sub == "reset" and "--hard" in rest:
        return REASONS["reset"]
    if sub == "clean":
        flags = set().union(*(short_flags(a) for a in rest)) if rest else set()
        dry_run = "n" in flags or "--dry-run" in rest
        interactive = "i" in flags or "--interactive" in rest
        force = "f" in flags or "--force" in rest
        if force and not dry_run and not interactive:
            return REASONS["clean"]
    return None


def check_dd(args):
    for a in args:
        if a.startswith("of="):
            dev = a[3:]
            if dev.startswith("/dev/") and not SAFE_DEVICE.match(dev):
                return REASONS["dd"]
    return None


def check_argv(argv, cwd, depth):
    argv = strip_prefixes(argv)
    if not argv:
        return None
    name, args = os.path.basename(argv[0]), argv[1:]

    if name in SHELLS:  # bash -c "..." 안쪽도 검사
        for idx, a in enumerate(args):
            if short_flags(a) and "c" in short_flags(a) and idx + 1 < len(args):
                return analyze(args[idx + 1], cwd, depth + 1)
        return None
    if name == "eval":
        return analyze(" ".join(args), cwd, depth + 1)
    if name == "rm":
        return check_rm(args)
    if name == "git":
        return check_git(args, cwd)
    if name == "mkfs" or name.startswith("mkfs."):
        return REASONS["mkfs"]
    if name == "dd":
        return check_dd(args)
    return None


def analyze(command, cwd, depth=0):
    if depth > MAX_DEPTH:
        return None
    command, expanding_bodies = split_heredocs(command)

    for inner in substitutions(command) + [s for b in expanding_bodies for s in substitutions(b)]:
        reason = analyze(inner, cwd, depth + 1)
        if reason:
            return reason

    try:
        parts = segments(command)
    except ValueError:
        return REASONS["unparsable"]
    for argv in parts:
        reason = check_argv(argv, cwd, depth)
        if reason:
            return reason
    return None


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (ValueError, UnicodeDecodeError):
        deny(REASONS["bad_input"])
    if not isinstance(data, dict):
        deny(REASONS["bad_input"])

    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        sys.exit(0)

    reason = analyze(command, data.get("cwd") or os.getcwd())
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
