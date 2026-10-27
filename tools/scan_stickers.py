"""扫描 stickers/ 里新增的图片，逐张分析并打印进度。

用法：
    python tools/scan_stickers.py
"""
from __future__ import annotations

import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config import Config  # noqa: E402
from bot.llm import DeepSeekClient  # noqa: E402
from bot.stickers import IMAGE_EXTS, StickerLibrary  # noqa: E402
from bot.util import now_iso  # noqa: E402


def main() -> int:
    cfg = Config.load(ROOT)
    lib = StickerLibrary(ROOT, DeepSeekClient(cfg), cfg.timezone)
    files = sorted(
        path for path in lib.dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )
    pending = []
    for path in files:
        digest = hashlib.md5(path.read_bytes()).hexdigest().upper()
        if digest not in lib.items:
            pending.append((path, digest))

    print(f"共 {len(files)} 张图片，待分析 {len(pending)} 张", flush=True)
    ok = 0
    failed = 0

    def work(item):
        path, digest = item
        return path, digest, lib.analyze_file(path)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(work, item) for item in pending]
        for index, future in enumerate(as_completed(futures), 1):
            path, digest, meta = future.result()
            if meta is None:
                failed += 1
                print(f"[{index}/{len(pending)}] FAIL {path.name}", flush=True)
                continue
            lib.items[digest] = {
                "file": path.name,
                "md5": digest,
                **meta,
                "source": "local",
                "url": "",
                "res_id": "",
                "added_at": now_iso(cfg.timezone),
            }
            lib._save()
            ok += 1
            print(
                f"[{index}/{len(pending)}] {path.name} -> {meta['emotion']} "
                f"meme={meta['is_meme']} safe={meta['safe']} | {meta['description']}",
                flush=True,
            )
    print(f"完成：成功 {ok}，失败 {failed}，可用 {len(lib.usable_items())}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
