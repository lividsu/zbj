import os
import time
import logging
from pathlib import Path

CACHE_DIRS = ["image_cache", "file_cache"]

def cleanup_old_files(retention_days: int):
    """删除 cache 目录中超过 retention_days 天的文件"""
    if retention_days <= 0:
        return

    cutoff = time.time() - retention_days * 86400
    root = Path(__file__).parent.parent

    for dir_name in CACHE_DIRS:
        cache_dir = root / dir_name
        if not cache_dir.exists():
            continue
        for f in cache_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    logging.info(f"[cleanup] 已删除过期文件: {f.name}")
                except Exception as e:
                    logging.warning(f"[cleanup] 删除失败 {f.name}: {e}")
