"""Demo'ni Hugging Face Space'ga joylash.

    HF_TOKEN=... HF_SPACE=azizmuksinov/Azentertrade python infra/hf-space/deploy.py
"""

import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SPACE = os.environ.get("HF_SPACE", "azizmuksinov/Azentertrade")
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache", "staticfiles", "*.sqlite3", ".env", "tests", "conftest.py"
)


def main() -> None:
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    if not api.repo_exists(SPACE, repo_type="space"):
        api.create_repo(SPACE, repo_type="space", space_sdk="docker")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        shutil.copytree(ROOT / "backend", stage / "backend", ignore=IGNORE)
        shutil.copytree(ROOT / "web", stage / "web", ignore=shutil.ignore_patterns("node_modules", ".next", "*.tsbuildinfo"))
        for name in ("Dockerfile", "start.sh", "README.md", "nginx.conf", "persist.py"):
            shutil.copy2(HERE / name, stage / name)
        api.upload_folder(
            repo_id=SPACE,
            repo_type="space",
            folder_path=stage,
            commit_message=f"deploy {os.environ.get('GITHUB_SHA', 'manual')[:12]}",
            delete_patterns=["**"],
        )
    print(f"https://huggingface.co/spaces/{SPACE}")


if __name__ == "__main__":
    main()
