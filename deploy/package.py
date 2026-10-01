import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
excluded = {
    ".git",
    ".pat",
    ".docs",
    "prompts",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}
target = root / ".pat/deployment.tar.gz"
with tarfile.open(target, "w:gz") as archive:
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and not excluded.intersection(relative.parts)
            and not path.name.startswith(".env")
            and path.suffix not in (".key", ".pem", ".log", ".gz")
        ):
            archive.add(path, arcname=str(relative).replace("\\", "/"))
print("Source archive created; private inputs and environment secrets excluded.")
