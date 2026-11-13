"""Demo bazasi va rasmlarini yopiq HF Dataset'da saqlash (bepul doimiy xotira o'rniga).

HF Space qayta ishga tushganda (yangilanish, 48 soatlik uyqu) diski tozalanadi. Shu skript:
  restore — ishga tushishda Dataset'dan demo.sqlite3 va media/ ni tiklaydi (bo'lsa);
  sync    — har SYNC_SECONDS da o'zgargan bo'lsa yuklaydi; SIGTERM kelganda oxirgi marta yuklaydi.

Faqat Space Secrets'da yozish huquqli HF_TOKEN bo'lsa ishlaydi; aks holda hech narsa qilmaydi.
Dataset: DEMO_PERSIST_REPO yoki "<egasi>/<space>-data" (SPACE_ID'dan), private.
"""

import hashlib
import os
import shutil
import signal
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

DATA = Path(os.environ.get("DEMO_DATA_DIR", "/home/user/data"))
DB = DATA / "demo.sqlite3"
MEDIA = Path(os.environ.get("MEDIA_ROOT", str(DATA / "media")))
SYNC_SECONDS = int(os.environ.get("DEMO_PERSIST_SECONDS", "300"))


def repo_id() -> str | None:
    if os.environ.get("DEMO_PERSIST_REPO"):
        return os.environ["DEMO_PERSIST_REPO"]
    space = os.environ.get("SPACE_ID", "")
    return f"{space.lower()}-data" if "/" in space else None


def api():
    token = os.environ.get("HF_TOKEN")
    if not token or not repo_id():
        return None
    from huggingface_hub import HfApi

    return HfApi(token=token)


def log(msg: str) -> None:
    print(f"PERSIST: {msg}", flush=True)


def restore() -> int:
    """0 — tiklandi; 1 — tiklanadigan narsa yo'q yoki sozlanmagan (yangi demo baza yaratiladi)."""
    hf = api()
    if hf is None:
        log("HF_TOKEN yo'q — ma'lumotlar qayta ishga tushganda tozalanadi.")
        return 1
    repo = repo_id()
    try:
        hf.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
        files = set(hf.list_repo_files(repo, repo_type="dataset"))
    except Exception as exc:  # noqa: BLE001 — tarmoq/huquq xatosi demo'ni to'xtatmasin
        log(f"Dataset ochilmadi ({repo}): {exc}")
        return 1
    if "demo.sqlite3" not in files:
        log(f"{repo}: hali zaxira yo'q — yangi baza.")
        return 1
    from huggingface_hub import snapshot_download

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_download(repo, repo_type="dataset", local_dir=tmp, token=os.environ["HF_TOKEN"])
        DATA.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(tmp) / "demo.sqlite3", DB)
        if (Path(tmp) / "media").is_dir():
            shutil.copytree(Path(tmp) / "media", MEDIA, dirs_exist_ok=True)
    log(f"{repo}: baza va rasmlar tiklandi.")
    return 0


def _snapshot(dst: Path) -> str:
    """Ishlayotgan bazadan izchil nusxa (sqlite backup API) va uning xeshi."""
    src = sqlite3.connect(DB)
    out = sqlite3.connect(dst)
    with out:
        src.backup(out)
    src.close()
    out.close()
    return hashlib.sha256(dst.read_bytes()).hexdigest()


def _media_state() -> dict[str, float]:
    if not MEDIA.is_dir():
        return {}
    return {str(p.relative_to(MEDIA)): p.stat().st_mtime for p in MEDIA.rglob("*") if p.is_file()}


def sync() -> None:
    hf = api()
    if hf is None or not DB.exists():
        return
    repo = repo_id()
    last_db, last_media = None, _media_state() if os.environ.get("DEMO_RESTORED") == "1" else {}
    stop = {"now": False}

    def on_term(*_):
        stop["now"] = True

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    def push(final: bool = False) -> None:
        nonlocal last_db, last_media
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "demo.sqlite3"
            digest = _snapshot(snap)
            media = _media_state()
            changed_media = media != last_media
            if digest == last_db and not changed_media:
                return
            if digest != last_db:
                hf.upload_file(
                    path_or_fileobj=str(snap),
                    path_in_repo="demo.sqlite3",
                    repo_id=repo,
                    repo_type="dataset",
                    commit_message="baza" + (" (oxirgi)" if final else ""),
                )
                last_db = digest
            if changed_media and media:
                hf.upload_folder(folder_path=str(MEDIA), path_in_repo="media", repo_id=repo, repo_type="dataset",
                                 commit_message="rasmlar")
            last_media = media
            log(f"saqlandi ({time.strftime('%H:%M:%S')})")

    # Birinchi holat: tiklangan bo'lsa — uni "yuklangan" deb hisoblaymiz (behuda commit bo'lmasin).
    if os.environ.get("DEMO_RESTORED") == "1":
        with tempfile.TemporaryDirectory() as tmp:
            last_db = _snapshot(Path(tmp) / "x.sqlite3")
    next_at = time.monotonic() + SYNC_SECONDS
    while not stop["now"]:
        time.sleep(2)
        if time.monotonic() >= next_at:
            next_at = time.monotonic() + SYNC_SECONDS
            try:
                push()
            except Exception as exc:  # noqa: BLE001
                log(f"saqlanmadi: {exc}")
    try:
        push(final=True)
    except Exception as exc:  # noqa: BLE001
        log(f"oxirgi saqlash bo'lmadi: {exc}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "restore":
        sys.exit(restore())
    if cmd == "sync":
        sync()
    else:
        print(__doc__)
