# -*- coding: utf-8 -*-
"""脱敏扫描器: 真人身份串 / 凭据 / 私人数据路径 检测。

用法:
  python tools/scan_secrets.py                  # 扫描目录全部文件 (迁移前体检)
  python tools/scan_secrets.py --root <dir>     # 扫描任意项目
  python tools/scan_secrets.py --tracked        # 只扫 git 跟踪文件 (CI 用, 有违规 exit 1)
  python tools/scan_secrets.py --staged         # 只扫 git 暂存区 (pre-commit)
  python tools/scan_secrets.py --history        # 扫 git 全部对象(含不可达) —— 泄漏历史体检

模式分两层:
  - 内置通用模式: 凭据/ID/路径/长base64 —— 对所有用户生效
  - 个人模式: tools/scan_patterns.local.txt (gitignored, 不入库!) —— 你自己的化名/地名/人名
    模板见 tools/scan_patterns.example.txt。**不要把真实化名写进任何入库文件。**

扫描纪律:
  - 编码: UTF-8 失败回退 gb18030, 仍失败按 replace 有损解码并**明示告警**——绝不静默跳过文件;
  - 二进制: 按()>=[可打印字符串]扫描(含 UTF-16LE), 不因扩展名豁免; 超大模型权重除外(体积原因)。
"""
import argparse
import re
import sys
from pathlib import Path

BUILTIN = [
    (r"wxid_[a-z0-9_]+", "wechat id"),
    (r"@[a-z]+\.im\.wechat", "wechat owner ref"),
    (r"\b[0-9a-f]{32,64}\b", "hex credential (md5/aeskey/apikey)"),
    (r"C:\\Users\\[A-Za-z]+\\", "personal filesystem path"),
    (r"/Users/[a-z]+/|/e/Workspace|E:\\Workspace", "personal filesystem path"),
    (r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY", "private key"),
    (r"sk-[A-Za-z0-9]{16,}", "api key"),
    (r"\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{20,}\b", "github token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "aws access key"),
    (r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.", "jwt token"),
    (r"(password|passwd|secret|api_key|apikey|token)\s*[=:]\s*['\"][^'\"]{8,}", "credential assignment"),
    (r"[A-Za-z0-9+/]{200,}={0,2}", "long base64 blob"),
]

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "local_llm",
             "media-in", "inbox", "outbox", "sent", "failed", "processed", "login",
             ".pytest_cache", ".ruff_cache"}
# 超大模型权重不扫(体积原因); 其余二进制一律走字符串扫描
SKIP_EXT = {".gguf", ".safetensors", ".ckpt", ".pt", ".pth", ".bin"}
BIN_SCAN_MAX = 30 * 1024 * 1024  # 30MB


def load_personal_patterns(root: Path):
    p = root / "tools" / "scan_patterns.local.txt"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            out.append((line, "personal pattern (local file)"))
    return out


def compile_patterns(root: Path):
    compiled = [(re.compile(pat, re.I), tag) for pat, tag in BUILTIN]
    compiled += [(re.compile(re.escape(pat), re.I), tag) for pat, tag in load_personal_patterns(root)]
    return compiled


def iter_files(root: Path, mode="all"):
    self_path = Path(__file__).resolve()  # 扫描器自身(内含模式字面量)所有模式下都跳过
    if mode in ("tracked", "staged"):
        import subprocess
        cmd = (["git", "ls-files"] if mode == "tracked"
               else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"])
        out = subprocess.run(cmd, cwd=root, capture_output=True, text=True).stdout
        for line in out.splitlines():
            p = root / line
            if p.exists() and p.resolve() != self_path:
                yield p
        return
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.resolve() == self_path:
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield p


def _text_or_binary(p: Path):
    """返回 (text, raw, kind); kind ∈ text/binary/lossy。绝不静默跳过。"""
    raw = p.read_bytes()
    if b"\x00" in raw[:8192]:
        return None, raw, "binary"
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc), None, "text"
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), None, "lossy"


def _binary_strings(raw: bytes):
    """二进制 → 可打印串(ASCII + UTF-16LE), 供模式扫描。"""
    out = [m.decode("ascii", "ignore") for m in re.findall(rb"[\x20-\x7e]{6,}", raw)]
    out += [m.decode("utf-16-le", "ignore")
            for m in re.findall(rb"(?:[\x20-\x7e]\x00){4,}", raw)]
    return out


def _match_lines(lines, compiled, where, hits, verbose):
    for lineno, line in enumerate(lines, 1):
        for pat, tag in compiled:
            if pat.search(line):
                hits.append((where, lineno, tag, line.strip()[:90]))
                if not verbose:
                    break


def scan(root: Path, mode="all", verbose=False):
    compiled = compile_patterns(root)
    hits, nfiles, lossy = [], 0, []
    for f in iter_files(root, mode):
        if f.suffix.lower() in SKIP_EXT or f.stat().st_size > BIN_SCAN_MAX:
            continue
        nfiles += 1
        text, raw, kind = _text_or_binary(f)
        where = str(f.relative_to(root))
        if kind == "binary":
            _match_lines(_binary_strings(raw), compiled, where + "~bin", hits, verbose)
        else:
            if kind == "lossy":
                lossy.append(where)
            _match_lines(text.split("\n"), compiled, where, hits, verbose)
    return nfiles, lossy, hits


def scan_history(root: Path, verbose=False):
    import subprocess
    compiled = compile_patterns(root)
    # 豁免当前扫描器自身的 blob: 其内容就是模式字面量, 历史模式会自匹配
    own = subprocess.run(["git", "hash-object", str(Path(__file__).resolve())],
                         cwd=root, capture_output=True, text=True).stdout.strip()
    check = subprocess.run(
        ["git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        cwd=root, capture_output=True, text=True).stdout
    hits, nblob = [], 0
    for line in check.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[1] != "blob" or int(parts[2]) > BIN_SCAN_MAX:
            continue
        sha = parts[0]
        if sha == own:
            continue
        blob = subprocess.run(["git", "cat-file", "blob", sha],
                              cwd=root, capture_output=True).stdout
        nblob += 1
        if b"\x00" in blob[:8192]:
            _match_lines(_binary_strings(blob), compiled, f"{sha[:12]}~bin", hits, verbose)
        else:
            _match_lines(blob.decode("utf-8", errors="replace").split("\n"),
                         compiled, sha[:12], hits, verbose)
    return nblob, hits


def _report(header, hits, quiet):
    print(header)
    if hits and not quiet:
        by_file = {}
        for f, ln, tag, line in hits:
            by_file.setdefault(f, []).append((ln, tag, line))
        for f, items in sorted(by_file.items()):
            print(f"\n  {f}  ({len(items)} 处)")
            for ln, tag, line in items[:6]:
                print(f"    L{ln} [{tag}] {line}")
            if len(items) > 6:
                print(f"    ... 还有 {len(items)-6} 处")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--tracked", action="store_true", help="只扫 git 跟踪文件 (CI)")
    ap.add_argument("--staged", action="store_true", help="只扫 git 暂存区 (pre-commit)")
    ap.add_argument("--history", action="store_true", help="扫 git 全部对象(含不可达)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    personal = load_personal_patterns(root)

    if a.history:
        nblob, hits = scan_history(root, verbose=a.verbose)
        _report(f"[scan-history] {nblob} 个 blob 对象, {len(hits)} 处违规 "
                f"(通用 {len(BUILTIN)} + 个人 {len(personal)})", hits, a.quiet)
    else:
        mode = "tracked" if a.tracked else ("staged" if a.staged else "all")
        nfiles, lossy, hits = scan(root, mode=mode, verbose=a.verbose)
        _report(f"[scan] {nfiles} 文件, {len(hits)} 处违规 "
                f"(通用 {len(BUILTIN)} + 个人 {len(personal)}; 模式={mode})", hits, a.quiet)
        for w in lossy:
            print(f"[scan] ⚠ 解码有损(已按 replace 扫描): {w}")

    if hits:
        print("\n[scan] FAIL — 存在真人数据/凭据风险 (红线见 docs/ethics.md)")
        sys.exit(1)
    print("\n[scan] PASS — 未发现真人身份串/凭据/私人路径")


if __name__ == "__main__":
    main()
