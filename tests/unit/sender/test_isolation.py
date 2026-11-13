import subprocess
import sys
from pathlib import Path

SEND_CODE_DIR = Path(__file__).resolve().parents[3] / "functions" / "send"


def test_sender_imports_without_render_dependencies():
    """The send ZIP only has the standard library and boto3; it must not import more."""
    script = (
        "import sys, sender.app\n"
        "heavy = {'pptcreator', 'pycore', 'pptx', 'pandas', 'pydantic', 'sqlalchemy', 'pyodbc'}\n"
        "print(sorted(heavy & {m.split('.')[0] for m in sys.modules}))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        cwd=SEND_CODE_DIR,  # like the Lambda: only the ZIP content is importable by path
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "[]"
