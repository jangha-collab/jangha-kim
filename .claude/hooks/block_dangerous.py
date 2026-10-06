#!/usr/bin/env python3
"""PreToolUse(Bash) 훅 본체: 위험한 셸 명령을 실행 전에 차단한다.

block-dangerous.sh 가 이 파일을 실행한다. stdin 으로 훅 입력 JSON 을 받고,
막아야 하면 permissionDecision=deny JSON 을 출력한다. 통과면 아무것도 출력하지 않는다.

명령 문자열을 정규식으로 훑지 않는다. 작은 셸 어휘 분석기(Lexer)로
따옴표·주석·heredoc·명령 치환을 셸과 같은 규칙으로 해석한 뒤,
"명령 위치"에 있는 프로그램과 그 실제 인자만 검사한다.
- 따옴표 안의 글자, 주석, 따옴표 heredoc 본문은 실행되지 않으므로 검사하지 않는다.
- $(...), `...`, <(...), bash -c, eval, su -c, 셸에 넘기는 stdin 은 안쪽까지 검사한다.
- sudo·env·nohup 같은 앞부분, 옵션 순서·축약·묶음, 경로 표기 변형에 속지 않는다.
- 같은 명령 안의 cd 와 변수 대입(T=/)을 따라가 실제 대상을 계산한다.

사고를 막는 안전장치이지 보안 경계가 아니다. 정적으로 알 수 없는 값
(예: $(echo rm) 으로 만든 명령 이름)까지 막지는 못한다.
"""

import json
import os
import posixpath
import re
import subprocess
import sys

MAIN_BRANCHES = {"main", "master"}
SAFE_DEVICE = re.compile(
    r"^/dev/(null|zero|full|random|urandom|stdin|stdout|stderr|tty|console|fd/\d+|pts/\d+|shm(/.*)?|tcp/.+|udp/.+)$"
)
# find 가 지울 대상을 좁히는 조건. 이 중 하나라도 (부정 없이) 있으면 "전체 삭제"로 보지 않는다.
FIND_FILTERS = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex",
                "-lname", "-ilname", "-empty"}
MAX_DEPTH = 8

REASONS = {
    "rm": "차단됨: 루트(/)나 홈(~) 디렉터리를 통째로 지우는 명령은 허용되지 않습니다.",
    "rm_var": "차단됨: 변수가 비어 있으면 루트(/)나 홈을 통째로 지우게 되는 명령입니다. "
    '"${VAR:?}"처럼 비어 있을 때 멈추는 형태로 쓰세요.',
    "push_force": "차단됨: main/master 브랜치로의 강제 푸시는 허용되지 않습니다.",
    "push_delete": "차단됨: 원격 main/master 브랜치를 지우는 푸시는 허용되지 않습니다.",
    "clean": "차단됨: git clean -f 는 추적되지 않은 파일을 되돌릴 수 없게 지웁니다. 먼저 git clean -n 으로 확인하세요.",
    "reset": "차단됨: git reset --hard 는 커밋하지 않은 변경을 잃게 하므로 허용되지 않습니다.",
    "mkfs": "차단됨: 장치(/dev/...)에 파일시스템을 새로 만드는 명령은 허용되지 않습니다.",
    "dd": "차단됨: 장치(/dev/...)에 직접 쓰는 dd 명령은 허용되지 않습니다.",
    "device_write": "차단됨: 장치(/dev/...)에 직접 쓰는 리디렉션이나 tee 는 허용되지 않습니다. "
    "/dev/null, /dev/stderr 같은 안전한 장치만 쓸 수 있습니다.",
    "find": "차단됨: 루트(/)나 홈(~) 전체를 대상으로 파일을 지우는 find 명령은 허용되지 않습니다. "
    "-name 이나 -path 로 대상을 좁히거나 시작 경로를 더 구체적으로 주세요.",
    "unparsable": "차단됨: 명령의 따옴표나 괄호 짝이 맞지 않아 안전한지 판단할 수 없습니다. 명령을 고쳐 다시 실행하세요.",
    "too_deep": "차단됨: 명령이 너무 깊게 중첩되어 안전한지 판단할 수 없습니다.",
    "bad_input": "차단됨: 훅 입력을 읽을 수 없어 안전을 위해 막았습니다.",
    "internal": "차단됨: 훅이 명령을 검사하다 오류가 나서 안전을 위해 막았습니다.",
}

SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash"}
KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "{", "}", "esac"}
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=(.*)$", re.S)
HEREDOC_AT = re.compile(r"<<(-?)[ \t]*(\\?)(['\"]?)([^\s'\"<>;&|()]+)\3")
OPERATOR = re.compile(r";;&|;;|;&|&&|\|\||\|&|[;&|()]")
REDIRECT = re.compile(r"<<<|<<-|<<|<>|<&|>>|>&|>\||<|>")


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


# ======================================================================
# 어휘 분석
# ======================================================================


class Word:
    """셸 단어 하나. value 는 따옴표를 벗긴 글자, 나머지는 해석에 필요한 표시."""

    __slots__ = ("value", "quoted", "expands", "tilde")

    def __init__(self):
        self.value = ""
        self.quoted = False  # 일부라도 따옴표·백슬래시로 감싸였는가
        self.expands = False  # 따옴표 밖이나 큰따옴표 안에 $ 나 ` 가 있는가
        self.tilde = False  # 따옴표 없는 ~ 로 시작하는가 (홈으로 펼쳐지는가)


class Segment:
    """단순 명령 하나. op 는 바로 앞의 제어 연산자, stdin 은 heredoc/here-string 내용,
    writes 는 출력 리디렉션(> >> >| <> &> >&파일)이 쓰는 대상."""

    def __init__(self, op):
        self.op = op
        self.words = []
        self.stdin = []
        self.writes = []


class Lexer:
    def __init__(self, text):
        self.s = text
        self.n = len(text)
        self.subs = []  # 실행되는 명령 치환의 안쪽 문자열
        self.segments = [Segment(None)]
        self.pending = []  # 아직 본문을 읽지 않은 heredoc: (구분자, 탭 허용, 따옴표 여부, Segment)

    # ---- 짝 맞추기 도우미 ------------------------------------------------

    def find_backtick(self, i):
        j = i
        while j < self.n:
            if self.s[j] == "\\":
                j += 2
                continue
            if self.s[j] == "`":
                return j
            j += 1
        raise ValueError("unterminated backtick")

    def skip_single(self, i):
        j = self.s.find("'", i)
        if j < 0:
            raise ValueError("unterminated single quote")
        return j + 1

    def skip_ansi(self, i):
        j = i
        while j < self.n:
            if self.s[j] == "\\":
                j += 2
                continue
            if self.s[j] == "'":
                return j + 1
            j += 1
        raise ValueError("unterminated $'")

    def skip_double(self, i):
        j = i
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                return j + 1
            if c == "$" and self.s.startswith("(", j + 1):
                j = self.match_paren(j + 1) + 1
                continue
            if c == "`":
                j = self.find_backtick(j + 1) + 1
                continue
            j += 1
        raise ValueError("unterminated double quote")

    def skip_heredoc_bodies(self, i, pending, collect=None):
        """i 는 줄의 시작. pending 순서대로 본문 줄을 건너뛰고 다음 위치를 돌려준다."""
        for delim, dash, _quoted, _seg in pending:
            body = []
            while i <= self.n:
                end = self.s.find("\n", i)
                line = self.s[i:] if end < 0 else self.s[i:end]
                i = self.n + 1 if end < 0 else end + 1
                if (line.lstrip("\t") if dash else line) == delim:
                    break
                body.append(line)
            if collect is not None:
                collect.append("\n".join(body))
        return min(i, self.n)

    def match_paren(self, i):
        """s[i] 가 '(' 일 때 짝이 되는 ')' 의 위치. 따옴표·주석·heredoc 안의 괄호는 세지 않는다."""
        depth, j, pending = 0, i, []
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
            elif c == "'":
                j = self.skip_single(j + 1)
            elif c == '"':
                j = self.skip_double(j + 1)
            elif c == "`":
                j = self.find_backtick(j + 1) + 1
            elif c == "#" and (j == 0 or self.s[j - 1] in " \t\n;&|()"):
                end = self.s.find("\n", j)
                j = self.n if end < 0 else end
            elif c == "<" and self.s.startswith("<<", j) and not self.s.startswith("<<<", j):
                m = HEREDOC_AT.match(self.s, j)
                if m:
                    pending.append((m.group(4), m.group(1) == "-", True, None))
                    j = m.end()
                else:
                    j += 2
            elif c == "\n" and pending:
                j = self.skip_heredoc_bodies(j + 1, pending)
                pending = []
            else:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        return j
                j += 1
        raise ValueError("unbalanced parenthesis")

    def match_brace(self, i):
        depth, j = 0, i
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == "'":
                j = self.skip_single(j + 1)
                continue
            if c == '"':
                j = self.skip_double(j + 1)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        raise ValueError("unbalanced brace")

    # ---- $ 처리 (따옴표 밖과 큰따옴표 안에서 공통) -------------------------

    def read_dollar(self, i, word):
        s = self.s
        word.expands = True
        if s.startswith("$((", i):  # 산술 확장: 명령이 아니다
            j = self.match_paren(i + 1)
            word.value += s[i : j + 1]
            return j + 1
        if s.startswith("$(", i):
            j = self.match_paren(i + 1)
            self.subs.append(s[i + 2 : j])
            word.value += s[i : j + 1]
            return j + 1
        if s.startswith("${", i):
            j = self.match_brace(i + 1)
            word.value += s[i : j + 1]
            return j + 1
        word.value += "$"
        return i + 1

    def read_double(self, i, word):
        s = self.s
        word.quoted = True
        while i < self.n:
            c = s[i]
            if c == '"':
                return i + 1
            if c == "\\" and i + 1 < self.n and s[i + 1] in '$`"\\\n':
                if s[i + 1] != "\n":
                    word.value += s[i + 1]
                i += 2
            elif c == "$":
                i = self.read_dollar(i, word)
            elif c == "`":
                j = self.find_backtick(i + 1)
                self.subs.append(s[i + 1 : j].replace("\\`", "`"))
                word.value += s[i : j + 1]
                word.expands = True
                i = j + 1
            else:
                word.value += c
                i += 1
        raise ValueError("unterminated double quote")

    def read_ansi(self, i, word):
        """$'...' : 백슬래시 이스케이프를 푼 글자."""
        j = self.skip_ansi(i)
        raw = self.s[i : j - 1]
        try:
            word.value += raw.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except UnicodeDecodeError:
            word.value += raw
        word.quoted = True
        return j

    # ---- 본체 ------------------------------------------------------------

    def run(self):
        s, n = self.s, self.n
        word = None
        redirect = None  # 다음 단어가 무엇인지: in / out / dup_out / heredoc / heredoc- / herestring

        def ensure():
            nonlocal word
            if word is None:
                word = Word()
            return word

        def finish():
            nonlocal word, redirect
            if word is None:
                return
            seg = self.segments[-1]
            if redirect in ("heredoc", "heredoc-"):
                self.pending.append((word.value, redirect == "heredoc-", word.quoted, seg))
            elif redirect == "herestring":
                seg.stdin.append(word.value)
            elif redirect == "out":
                seg.writes.append(word)
            elif redirect == "dup_out":  # >&2, >&- 는 서술자 복제, >&파일 은 파일에 쓰기
                if not re.fullmatch(r"\d*-?", word.value):
                    seg.writes.append(word)
            elif redirect is None:
                seg.words.append(word)
            redirect = None
            word = None

        i = 0
        while i < n:
            c = s[i]
            nxt = s[i + 1] if i + 1 < n else ""
            if c == "\\":
                if nxt == "\n":  # 줄 이음
                    i += 2
                    continue
                w = ensure()
                w.value += nxt
                w.quoted = True
                i += 2
            elif c == "'":
                w = ensure()
                j = self.skip_single(i + 1)
                w.value += s[i + 1 : j - 1]
                w.quoted = True
                i = j
            elif c == "$" and nxt == "'":
                i = self.read_ansi(i + 2, ensure())
            elif c == '"':
                i = self.read_double(i + 1, ensure())
            elif c == "`":
                j = self.find_backtick(i + 1)
                self.subs.append(s[i + 1 : j].replace("\\`", "`"))
                w = ensure()
                w.value += s[i : j + 1]
                w.expands = True
                i = j + 1
            elif c == "$":
                i = self.read_dollar(i, ensure())
            elif c in " \t":
                finish()
                i += 1
            elif c == "\n":
                finish()
                self.segments.append(Segment(";"))
                i += 1
                if self.pending:
                    bodies = []
                    i = self.skip_heredoc_bodies(i, self.pending, bodies)
                    for (_d, _dash, quoted, seg), body in zip(self.pending, bodies):
                        seg.stdin.append(body)
                        if not quoted:  # 따옴표 없는 heredoc 은 본문의 $(...) 가 실행된다
                            self.subs.extend(Lexer(body).substitutions_only())
                    self.pending = []
            elif c == "#" and word is None:
                end = s.find("\n", i)
                i = n if end < 0 else end
            elif c in "<>":
                if nxt == "(":  # 프로세스 치환 <(...) >(...)
                    j = self.match_paren(i + 1)
                    self.subs.append(s[i + 2 : j])
                    w = ensure()
                    w.value += s[i : j + 1]
                    w.expands = True
                    i = j + 1
                    continue
                if word is not None and word.value.isdigit() and not word.quoted:
                    word = None  # 2>&1 의 2 같은 파일 서술자 번호
                else:
                    finish()
                op = REDIRECT.match(s, i).group(0)
                i += len(op)
                redirect = {
                    "<<<": "herestring",
                    "<<-": "heredoc-",
                    "<<": "heredoc",
                    ">": "out",
                    ">>": "out",
                    ">|": "out",
                    "<>": "out",
                    ">&": "dup_out",
                }.get(op, "in")
            elif c in ";&|()":
                if s.startswith("&>", i):
                    finish()
                    i += 3 if s.startswith("&>>", i) else 2
                    redirect = "out"
                    continue
                if c == "(" and word is not None and not word.quoted and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word.value):
                    j = self.match_paren(i)  # 배열 대입 files=(a b c)
                    word.value += s[i : j + 1]
                    i = j + 1
                    continue
                finish()
                op = OPERATOR.match(s, i).group(0)
                i += len(op)
                self.segments.append(Segment(op))
            else:
                w = ensure()
                if c == "~" and w.value == "" and not w.quoted:
                    w.tilde = True
                w.value += c
                i += 1
        finish()
        return self

    def substitutions_only(self):
        """따옴표 없는 heredoc 본문처럼 따옴표가 의미 없는 글에서 $(...) 와 `...` 만 꺼낸다."""
        found, i = [], 0
        while i < self.n:
            c = self.s[i]
            if c == "\\":
                i += 2
            elif self.s.startswith("$((", i):
                i = self.match_paren(i + 1) + 1
            elif self.s.startswith("$(", i):
                j = self.match_paren(i + 1)
                found.append(self.s[i + 2 : j])
                i = j + 1
            elif c == "`":
                j = self.find_backtick(i + 1)
                found.append(self.s[i + 1 : j])
                i = j + 1
            else:
                i += 1
        return found


# ======================================================================
# 경로 계산
# ======================================================================


def home_dirs():
    homes = set()
    for value in (os.environ.get("HOME"), os.path.expanduser("~")):
        if value and value != "/" and value.startswith("/"):
            homes.add(posixpath.normpath(value))
    return homes


def primary_home():
    return os.environ.get("HOME") or os.path.expanduser("~")


HOME_VAR = re.compile(r"^(\$HOME|\$\{HOME(:[?-][^}]*)?\})(?=/|$)")
LEADING_VAR = re.compile(r"^\$(\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
ANY_VAR = re.compile(r"\$(\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def expand_braces(value, limit=3):
    m = re.match(r"^(.*?)\{([^{}]*,[^{}]*)\}(.*)$", value, re.S)
    if not m or limit == 0:
        return [value]
    out = []
    for alt in m.group(2).split(","):
        out.extend(expand_braces(m.group(1) + alt + m.group(3), limit - 1))
    return out


def substitute_vars(value, variables):
    """같은 명령 안에서 대입된 변수(T=/)만 값으로 바꾼다. HOME 은 따로 다룬다."""

    def repl(m):
        name = m.group(2) or m.group(3)
        return variables[name] if name in variables and name != "HOME" else m.group(0)

    return ANY_VAR.sub(repl, value)


def resolve_path(value, tilde, cwd, strip_glob):
    """단어 값 → 정규화한 절대 경로. 알 수 없으면 None."""
    c = value
    if strip_glob:
        if c.endswith("/.*"):
            c = c[:-3] or "/"
        elif c.endswith("/*"):
            c = c[:-2] or "/"
        elif c in ("*", ".*"):
            c = "."
    if tilde and (c == "~" or c.startswith("~/")):
        c = primary_home() + c[1:]
    m = HOME_VAR.match(c)
    if m:
        c = primary_home() + c[m.end() :]
    if c == "" or "$" in c or "`" in c:
        return None
    if not c.startswith("/"):
        if cwd is None:
            return None
        c = posixpath.join(cwd, c)
    c = re.sub(r"^/+", "/", c)
    return posixpath.normpath(c)


# ======================================================================
# 명령 앞부분 정리
# ======================================================================

SUDO_VALUE_SHORT = set("ugChprtUTD")
SUDO_VALUE_LONG = {"user", "group", "host", "prompt", "chdir", "role", "type", "close-from", "other-user", "command-timeout"}
XARGS_VALUE = {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a", "--arg-file", "--delimiter", "--max-args",
               "--max-procs", "--max-lines", "--max-chars", "--eof"}


def strip_prefixes(words):
    """sudo, env, 셸 키워드, 변수 대입처럼 실제 프로그램 앞에 오는 것을 걷어 낸다.

    (남은 단어들, 안쪽까지 검사할 문자열들, stdin 에서 인자를 받는지) 를 돌려준다.
    """
    words = list(words)
    nested, from_stdin = [], False

    def opts(value_opts=(), value_long=()):
        while words and words[0].value.startswith("-") and words[0].value != "-":
            o = words.pop(0).value
            if o == "--":
                break
            name = o.split("=", 1)[0]
            if "=" not in o and (o in value_opts or name in value_long) and words:
                words.pop(0)

    while words:
        head = words[0]
        v = head.value
        name = posixpath.basename(v)
        if v in KEYWORDS and not head.quoted:
            words.pop(0)
        elif v == "function" and not head.quoted:
            words.pop(0)
            if words:
                words.pop(0)  # 함수 이름
        elif ASSIGN.match(v) and not v.startswith("="):
            words.pop(0)
        elif name in ("sudo", "doas"):
            words.pop(0)
            while words and words[0].value.startswith("-") and words[0].value != "-":
                o = words.pop(0).value
                if o == "--":
                    break
                if o.startswith("--"):
                    if "=" not in o and o[2:] in SUDO_VALUE_LONG and words:
                        words.pop(0)
                elif o[-1] in SUDO_VALUE_SHORT and words:
                    words.pop(0)
        elif name == "su":
            words.pop(0)
            rest = [w.value for w in words]
            for k, a in enumerate(rest):
                if a.startswith("--command="):
                    nested.append(a.split("=", 1)[1])
                elif (a in ("-c", "--command") or (a.startswith("-") and not a.startswith("--") and a.endswith("c"))) and k + 1 < len(rest):
                    nested.append(rest[k + 1])
            return [], nested, from_stdin
        elif name == "env":
            words.pop(0)
            while words and (words[0].value.startswith("-") or ASSIGN.match(words[0].value)):
                o = words.pop(0).value
                if o == "--":
                    break
                if o in ("-S", "--split-string") and words:
                    nested.append(" ".join(w.value for w in words))
                    return [], nested, from_stdin
                if o.startswith("--split-string="):
                    nested.append(" ".join([o.split("=", 1)[1]] + [w.value for w in words]))
                    return [], nested, from_stdin
                if o in ("-u", "--unset", "-C", "--chdir") and words:
                    words.pop(0)
        elif name in ("nohup", "command", "builtin", "setsid", "coproc", "busybox", "stdbuf", "unbuffer"):
            words.pop(0)
            opts()
        elif name == "exec":
            words.pop(0)
            opts({"-a"})
        elif name == "time":
            words.pop(0)
            opts({"-f", "-o"}, {"--format", "--output"})
        elif name == "nice":
            words.pop(0)
            opts({"-n"}, {"--adjustment"})
        elif name == "ionice":
            words.pop(0)
            opts({"-c", "-n", "-p", "-P", "-u"}, {"--class", "--classdata", "--pid", "--pgid", "--uid"})
        elif name == "timeout":
            words.pop(0)
            opts({"-s", "-k"}, {"--signal", "--kill-after"})
            if words:
                words.pop(0)  # 시간 값
        elif name == "xargs":
            words.pop(0)
            opts(XARGS_VALUE, XARGS_VALUE)
            from_stdin = True
        else:
            break
    return words, nested, from_stdin


def short_flags(arg):
    if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
        return set(arg[1:])
    return set()


def long_is(arg, full, min_len):
    """GNU 식 긴 옵션 축약: '--rec' 는 '--recursive' 로 본다."""
    name = arg.split("=", 1)[0]
    return name.startswith("--") and len(name) >= min_len and full.startswith(name)


# ======================================================================
# 명령별 검사
# ======================================================================


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
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def check_rm(words, state):
    recursive, targets, after = False, [], False
    for w in words:
        a = w.value
        if not after and a == "--":
            after = True
        elif not after and a.startswith("--") and len(a) > 2:
            recursive = recursive or long_is(a, "--recursive", 3)
        elif not after and a.startswith("-") and len(a) > 1:
            recursive = recursive or bool(set(a[1:]) & {"r", "R"})
        else:
            targets.append(w)
    if not recursive:
        return None

    danger = {"/"} | home_dirs()
    for w in targets:
        raw = substitute_vars(w.value, state["vars"])
        for cand in expand_braces(raw):
            variants = [(cand, "rm")]
            m = LEADING_VAR.match(cand)
            if m and (m.group(2) or m.group(3)) != "HOME":
                variants.append((cand[m.end() :], "rm_var"))  # 변수가 비었을 때
            for text, reason in variants:
                path = resolve_path(text, w.tilde, state["cwd"], strip_glob=True)
                if path in danger:
                    return REASONS[reason]
    return None


def check_push(args, cwd):
    force = delete = dry = whole = False
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            i += 2
            continue
        if a == "--":
            positional.extend(args[i + 1 :])
            break
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if len(name) > len("--force-") and "--force-if-includes".startswith(name):
                pass  # 단독으로는 강제 푸시가 아니다
            elif len(name) >= 5 and ("--force".startswith(name) or "--force-with-lease".startswith(name)):
                force = True
            elif long_is(a, "--delete", 5):
                delete = True
            elif long_is(a, "--dry-run", 4):
                dry = True
            elif long_is(a, "--mirror", 4):
                force = whole = True
            elif name in ("--all", "--branches"):
                whole = True
        elif short_flags(a):
            for k, ch in enumerate(a[1:]):
                if ch == "o":  # -o 값
                    if k == len(a) - 2:
                        i += 1
                    break
                force = force or ch == "f"
                delete = delete or ch == "d"
                dry = dry or ch == "n"
        else:
            positional.append(a)
        i += 1
    if dry:
        return None

    refspecs = positional[1:]
    for spec in refspecs:
        plus = spec.startswith("+")
        spec = spec[1:] if plus else spec
        src, dst = spec.split(":", 1) if ":" in spec else (spec, spec)
        for prefix in ("refs/heads/", "heads/"):
            dst = dst.removeprefix(prefix)
        if dst in ("HEAD", "@") or "$" in dst or "`" in dst:
            if cwd is None:  # 어느 저장소인지 모르면 강제 푸시는 막는다
                if force or plus:
                    return REASONS["push_force"]
                continue
            dst = current_branch(cwd) or dst
        if "*" in dst and (force or plus):
            return REASONS["push_force"]
        if dst in MAIN_BRANCHES:
            if delete or (":" in spec and src == ""):
                return REASONS["push_delete"]
            if force or plus:
                return REASONS["push_force"]

    if force and not refspecs:
        if whole or cwd is None or current_branch(cwd) in MAIN_BRANCHES:
            return REASONS["push_force"]
    return None


def check_clean(args):
    flags, words = set(), iter(args)
    long_flags = set()
    for a in words:
        if a == "--":
            break
        if a.startswith("--"):
            if long_is(a, "--exclude", 3):
                if "=" not in a:
                    next(words, None)
            elif long_is(a, "--force", 3):
                long_flags.add("f")
            elif long_is(a, "--dry-run", 3):
                long_flags.add("n")
            elif long_is(a, "--interactive", 3):
                long_flags.add("i")
        elif short_flags(a):
            for k, ch in enumerate(a[1:]):
                if ch == "e":  # -e 패턴: 나머지는 값
                    if k == len(a) - 2:
                        next(words, None)
                    break
                flags.add(ch)
    flags |= long_flags
    if "f" in flags and "n" not in flags and "i" not in flags:
        return REASONS["clean"]
    return None


def check_git(args, state, depth):
    cwd = state["cwd"]
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            target = args[i + 1]
            cwd = posixpath.normpath(posixpath.join(cwd, target)) if (cwd or target.startswith("/")) else None
            i += 2
        elif a in ("-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path", "--super-prefix"):
            i += 2
        else:
            i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1 :]

    if sub == "push":
        return check_push(rest, cwd)
    if sub == "reset" and any(a == "--hard" or long_is(a, "--hard", 4) for a in rest):
        return REASONS["reset"]
    if sub == "clean":
        return check_clean(rest)
    if sub == "submodule" and "foreach" in rest:
        script = rest[rest.index("foreach") + 1 :]
        while script and script[0].startswith("-"):
            script = script[1:]
        if script:
            return analyze(" ".join(script), cwd, depth + 1)
    return None


def check_dd(args, cwd):
    for a in args:
        if a.startswith("of="):
            path = resolve_path(a[3:], False, cwd, strip_glob=False)
            if path and path.startswith("/dev/") and not SAFE_DEVICE.match(path):
                return REASONS["dd"]
    return None


def check_mkfs(name, args, cwd):
    if name not in ("mkfs", "mke2fs") and not re.fullmatch(r"mkfs\.[a-z0-9]+", name):
        return None
    if name.split(".")[-1] in ("sh", "py", "pl", "rb", "js"):
        return None
    for a in args:
        path = resolve_path(a, False, cwd, strip_glob=False) if not a.startswith("-") else None
        if path and path.startswith("/dev/"):
            return REASONS["mkfs"]
    return None


def is_device(word, state):
    """단어가 가리키는 경로가 안전 목록에 없는 /dev 장치인가."""
    value = substitute_vars(word.value, state["vars"])
    path = resolve_path(value, word.tilde, state["cwd"], strip_glob=False)
    return bool(path and path.startswith("/dev/") and not SAFE_DEVICE.match(path))


def check_writes(seg, state):
    """> >> >| <> &> >&파일 리디렉션이 장치에 쓰는지 본다."""
    for w in seg.writes:
        if is_device(w, state):
            return REASONS["device_write"]
    return None


def parse_find(words, state):
    """find 인자를 읽어 (루트·홈에서 시작하는가, 지우는 동작이 있는가, 대상을 좁혔는가)를 돌려준다."""
    vals = [w.value for w in words]
    i = 0
    while i < len(vals) and (vals[i] in ("-H", "-L", "-P", "-D") or vals[i].startswith("-O")):
        i += 2 if vals[i] == "-D" else 1
    starts = []
    while i < len(vals) and not (vals[i].startswith("-") or vals[i] in ("(", ")", "!", ",")):
        starts.append(words[i])
        i += 1
    expr = vals[i:]

    danger = {"/"} | home_dirs()
    if starts:
        from_danger = any(
            resolve_path(substitute_vars(w.value, state["vars"]), w.tilde, state["cwd"], strip_glob=False) in danger
            for w in starts
        )
    else:  # 시작 경로가 없으면 현재 폴더
        from_danger = state["cwd"] in danger

    deletes = filtered = False
    k = 0
    while k < len(expr):
        t = expr[k]
        if t == "-delete":
            deletes = True
        elif t in ("-exec", "-execdir", "-ok", "-okdir"):
            command = expr[k + 1] if k + 1 < len(expr) else ""
            if t in ("-exec", "-execdir") and posixpath.basename(command) in ("rm", "unlink", "shred"):
                deletes = True
            while k + 1 < len(expr) and expr[k + 1] not in (";", "+"):
                k += 1
            k += 1  # 종결자 ; 또는 +
        elif t in FIND_FILTERS:
            if not (k > 0 and expr[k - 1] in ("!", "-not")):
                filtered = True
            if t != "-empty":
                k += 1  # 패턴 값
        k += 1
    return from_danger, deletes, filtered


def check_find(arg_words, state):
    from_danger, deletes, filtered = parse_find(arg_words, state)
    if from_danger and deletes and not filtered:
        return REASONS["find"]
    return None


def echo_args(seg):
    """앞 구간이 echo/printf 면 그 인자를 돌려준다 (파이프로 넘어가는 내용)."""
    if seg is None:
        return None
    words, _, _ = strip_prefixes(seg.words)
    if words and posixpath.basename(words[0].value) in ("echo", "printf"):
        return [w.value for w in words[1:] if not (w.value.startswith("-") and len(w.value) <= 3)]
    return None


def check_segment(seg, piped_from, state, depth):
    reason = check_writes(seg, state)
    if reason:
        return reason

    words, nested, from_stdin = strip_prefixes(seg.words)
    for text in nested:
        reason = analyze(text, state["cwd"], depth + 1)
        if reason:
            return reason

    if not words:  # 변수 대입만 있는 구간: T=/ 같은 값을 기억해 둔다
        for w in seg.words:
            m = ASSIGN.match(w.value)
            if m and not w.expands:
                state["vars"][m.group(1)] = m.group(2)
        return None

    if from_stdin:  # echo / | xargs rm -rf
        extra = echo_args(piped_from)
        if extra:
            for value in extra:
                w = Word()
                w.value = value
                words.append(w)

    name = posixpath.basename(words[0].value)
    arg_words = words[1:]
    args = [w.value for w in arg_words]

    if from_stdin and piped_from is not None and name in ("rm", "unlink", "shred"):
        # find / ... | xargs rm : find 가 루트·홈 전체를 넘기면 막는다
        source, _, _ = strip_prefixes(piped_from.words)
        if source and posixpath.basename(source[0].value) == "find":
            from_danger, _, filtered = parse_find(source[1:], state)
            if from_danger and not filtered:
                return REASONS["find"]

    if name == "cd":
        targets = [w for w in arg_words if not (w.value.startswith("-") and w.value != "-")]
        if not targets:
            state["cwd"] = primary_home()
        elif targets[0].value == "-":
            state["cwd"] = None
        else:
            value = substitute_vars(targets[0].value, state["vars"])
            state["cwd"] = resolve_path(value, targets[0].tilde, state["cwd"], strip_glob=False)
        return None

    if name in SHELLS:
        for k, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:] and "o" not in a[1:]:
                script = args[k + 1 :]
                if script and script[0] == "--":
                    script = script[1:]
                return analyze(script[0], state["cwd"], depth + 1) if script else None
        has_script_file = any(not a.startswith("-") for a in args if a not in ("pipefail", "errexit"))
        if not has_script_file:  # 셸이 stdin 에서 명령을 읽는다
            sources = list(seg.stdin)
            piped = echo_args(piped_from)
            if piped:
                sources.append(" ".join(piped))
            for text in sources:
                reason = analyze(text, state["cwd"], depth + 1)
                if reason:
                    return reason
        return None
    if name == "eval":
        return analyze(" ".join(args), state["cwd"], depth + 1)
    if name == "rm":
        return check_rm(arg_words, state)
    if name == "git":
        return check_git(args, state, depth)
    if name == "dd":
        return check_dd(args, state["cwd"])
    if name == "find":
        return check_find(arg_words, state)
    if name == "tee":
        for w in arg_words:
            if not w.value.startswith("-") and is_device(w, state):
                return REASONS["device_write"]
        return None
    return check_mkfs(name, args, state["cwd"])


def analyze(command, cwd, depth=0):
    """명령 문자열을 검사해 막을 이유를 돌려준다. 통과면 None."""
    if depth > MAX_DEPTH:
        return REASONS["too_deep"]
    try:
        lexer = Lexer(command).run()
    except ValueError:
        return REASONS["unparsable"]

    for inner in lexer.subs:
        reason = analyze(inner, cwd, depth + 1)
        if reason:
            return reason

    state = {"cwd": cwd, "vars": {}}
    previous = None
    for seg in lexer.segments:
        if not seg.words and not seg.stdin and not seg.writes:
            continue
        piped_from = previous if seg.op in ("|", "|&") else None
        reason = check_segment(seg, piped_from, state, depth)
        if reason:
            return reason
        previous = seg
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

    cwd = data.get("cwd")
    try:
        reason = analyze(command, cwd if isinstance(cwd, str) and cwd else os.getcwd())
    except Exception:  # 검사기 자체의 오류로 위험한 명령이 통과하지 않도록 막는다
        reason = REASONS["internal"]
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
