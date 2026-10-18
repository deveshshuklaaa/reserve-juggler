"""Regenerate the public OpenAPI snapshot from actual FastAPI response models."""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.main import app

if __name__ == "__main__":
    (ROOT / "contracts" / "openapi.yaml").write_text(
        yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True), encoding="utf-8")
