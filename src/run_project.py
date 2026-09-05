import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ROOT / "src" / "generate_data.py",
    ROOT / "src" / "validate_data.py",
    ROOT / "src" / "build_database.py",
    ROOT / "src" / "metrics.py",
    ROOT / "src" / "ab_test.py",
    ROOT / "src" / "validate_outputs.py",
    ROOT / "demo" / "validate_demo.py",
]


def clean_generated_files() -> None:
    generated_directories = [
        ROOT / "data" / "raw", ROOT / "data" / "processed",
        ROOT / "outputs" / "charts", ROOT / "outputs" / "tables",
    ]
    for directory in generated_directories:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            resolved = path.resolve()
            if path.is_file() and ROOT.resolve() in resolved.parents:
                path.unlink()


def main() -> None:
    clean_generated_files()
    print("Cleaned previously generated data and outputs.", flush=True)
    for script in STEPS:
        print(f"\n=== Running {script.name} ===", flush=True)
        subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)
    print("\nProject pipeline completed successfully.")


if __name__ == "__main__":
    main()
