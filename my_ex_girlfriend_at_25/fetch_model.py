# -*- coding: utf-8 -*-
"""模型自愈下载器: hf_transfer 多线程 + sha256 校验 + 收尾看门狗。

用法:
  python -m my_ex_girlfriend_at_25.fetch_model REPO_ID FILENAME DEST_DIR SHA256 EXPECT_SIZE
  SHA256 传全零 / EXPECT_SIZE 传 0 = 不校验, 下载后自动打印实际 sha256 与大小
  (首次获取某模型时用; 把打印值记下来, 以后重下可用它们复检)
环境:
  HF_ENDPOINT 默认 https://hf-mirror.com (国内); 海外可设 https://huggingface.co
教训沉淀: hf_hub 收尾挂起=常态(看门狗 7 分钟接管); >20G 对象 hf-mirror 可能坏缓存
(必须 sha256 终检); hf_transfer 不支持断点续传。
"""
import os
import sys
import glob
import time
import hashlib
import threading
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

WATCHDOG_S = 420  # 满大小 7 分钟未收尾 → 交手动校验


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path: Path, expect: str) -> bool:
    return sha256_of(path) == expect


def fetch(repo_id: str, filename: str, dest_dir: str, sha256: str, expect_size: int):
    from huggingface_hub import hf_hub_download
    verify = expect_size > 0 and sha256 and set(sha256.strip()) != {"0"}
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    cache = dest / ".cache" / "huggingface" / "download"

    done = {"ok": False}
    def watch():
        if not verify:
            return
        full_since = None
        while not done["ok"]:
            cands = glob.glob(str(cache / "*" + sha256[:16] + "*.incomplete"))
            if cands:
                sz = os.path.getsize(cands[0])
                print(f"[fetch] {filename[:44]} {sz/1e9:.2f}/{expect_size/1e9:.1f}GB", flush=True)
                if sz >= expect_size:
                    full_since = full_since or time.time()
                    if time.time() - full_since > WATCHDOG_S:
                        print("[fetch] 满大小未收尾 → 退出交手动校验", flush=True)
                        os._exit(2)
            time.sleep(45)
    threading.Thread(target=watch, daemon=True).start()

    p = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=dest)
    done["ok"] = True
    got = os.path.getsize(p)
    if not verify:
        print(f"[fetch] OK (未提供校验参数) → {p}")
        print(f"[fetch] size = {got} bytes")
        print(f"[fetch] sha256 = {sha256_of(Path(p))}")
        print("[fetch] 建议记录以上两值; 之后重新下载可用 --size/--sha256 复检")
        return
    if got != expect_size:
        raise SystemExit(f"[fetch] 大小不符 {got} != {expect_size}")
    if not _sha256(p, sha256):
        raise SystemExit("[fetch] sha256 校验失败 — 删除后重试或换镜像")
    print(f"[fetch] OK sha256 通过 → {p}")


def resume_finalize(dest_dir: str, sha256: str, expect_size: int, final_name: str):
    """看门狗触发后的手动收尾: 校验 .incomplete 并原子落位。"""
    cache = Path(dest_dir) / ".cache" / "huggingface" / "download"
    cands = glob.glob(str(cache / "*" + sha256 + "*.incomplete"))
    if not cands:
        print("[finalize] 无 incomplete"); return False
    src = Path(cands[0])
    if src.stat().st_size != expect_size:
        print(f"[finalize] 大小不符"); return False
    if not _sha256(src, sha256):
        print("[finalize] sha256 不符 — 文件损坏, 删除重下"); src.unlink(); return False
    dst = Path(dest_dir) / final_name
    os.replace(src, dst)
    print(f"[finalize] OK → {dst}")
    return True


if __name__ == "__main__":
    if sys.argv[1] == "resume":
        resume_finalize(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5])
    else:
        fetch(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
