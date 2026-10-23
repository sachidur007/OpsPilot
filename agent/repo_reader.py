"""Read-only bill of materials for a local directory or a git URL."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "venv",
    ".venv",
    "dist",
    "build",
    "__pycache__",
}
MANIFEST_NAMES = {
    "Dockerfile",
    "composer.json",
    "composer.lock",
    "package.json",
    "go.mod",
    "requirements.txt",
    "pom.xml",
    "Gemfile",
    "php_version.h",
    "configure.ac",
}
_PHP_VERSION = re.compile(r'#\s*define\s+PHP_VERSION\s+"([^"]+)"')
_PHP_MAJOR = re.compile(r'#\s*define\s+PHP_MAJOR_VERSION\s+(\d+)')
_PHP_MINOR = re.compile(r'#\s*define\s+PHP_MINOR_VERSION\s+(\d+)')
_PHP_RELEASE = re.compile(r'#\s*define\s+PHP_RELEASE_VERSION\s+(\d+)')
_MAX_BYTES = 1_000_000
_FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.IGNORECASE)
_VERSION = re.compile(r"(\d+(?:\.\d+){0,2})")
_GEM = re.compile(r"""gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""")
_POM_PAIR = re.compile(
    r"<artifactId>\s*([^<]+?)\s*</artifactId>\s*(?:<scope>[^<]*</scope>\s*)?<version>\s*([^<]+?)\s*</version>",
    re.IGNORECASE,
)


class RepoReadError(Exception):
    """The path or git URL could not be read."""


def read_repository(source: str) -> dict:
    raw = (source or "").strip()
    if not raw:
        raise RepoReadError("Name a directory or a git URL.")
    cleanup: Path | None = None
    try:
        if _is_git_url(raw):
            root = _clone(raw)
            cleanup = root
        else:
            root = Path(raw).expanduser().resolve()
            if not root.is_dir():
                raise RepoReadError("That path is not a directory.")
        return {"source": raw, "bom": _bill_of_materials(root), "docs": _project_docs(root)}
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)


def _is_git_url(source: str) -> bool:
    return source.startswith(("https://", "http://", "ssh://", "git@", "file://"))


def _clone(url: str) -> Path:
    temp = Path(tempfile.mkdtemp(prefix="opspilot-repo-"))
    try:
        subprocess.run(
            [
                "git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                "--config", "core.hooksPath=/dev/null", url, str(temp),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        subprocess.run(
            [
                "git", "-C", str(temp), "sparse-checkout", "set", "--no-cone",
                "**/php_version.h", "**/configure.ac", "**/Dockerfile*",
                "**/composer.json", "**/composer.lock", "**/package.json",
                "**/go.mod", "**/requirements.txt", "**/pom.xml", "**/Gemfile",
                "README.md", "README.rst", "README", "requirements.md", "req.md",
                "AGENTS.md", "CONTRIBUTING.md",
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        shutil.rmtree(temp, ignore_errors=True)
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            detail = exc.stderr.decode(errors="ignore").strip().splitlines()
            detail = detail[-1][:180] if detail else ""
        message = "The repository could not be cloned."
        if detail:
            message = f"{message} {detail}"
        raise RepoReadError(message) from exc
    return temp


def _bill_of_materials(root: Path) -> list[dict]:
    entries: list[dict] = []
    for path in _manifests(root):
        text = _read_text(path)
        if text is None:
            continue
        rel = path.relative_to(root).as_posix()
        name = path.name
        if name == "Dockerfile" or name.startswith("Dockerfile"):
            entries.extend(_dockerfile(rel, text))
        elif name == "composer.json":
            entries.extend(_composer_json(rel, text))
        elif name == "composer.lock":
            entries.extend(_composer_lock(rel, text))
        elif name == "package.json":
            entries.extend(_package_json(rel, text))
        elif name == "go.mod":
            entries.extend(_go_mod(rel, text))
        elif name == "requirements.txt":
            entries.extend(_requirements(rel, text))
        elif name == "pom.xml":
            entries.extend(_pom(rel, text))
        elif name == "Gemfile":
            entries.extend(_gemfile(rel, text))
        elif name == "php_version.h":
            entries.extend(_php_version_header(rel, text))
        elif name == "configure.ac":
            entries.extend(_php_configure(rel, text))
    return entries


def _manifests(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for filename in filenames:
            if filename not in MANIFEST_NAMES and not filename.startswith("Dockerfile"):
                continue
            path = Path(dirpath) / filename
            if path.is_symlink():
                continue
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            found.append(path)
    return found


_DOC_NAMES = {
    "readme",
    "readme.md",
    "readme.rst",
    "readme.txt",
    "requirements.md",
    "req.md",
    "agents.md",
    "contributing.md",
}


def _project_docs(root: Path) -> list[dict]:
    """Project instructions at the root. Dependency files stay in the bill of materials."""
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.is_symlink():
            continue
        lowered = path.name.lower()
        if lowered == "requirements.txt":
            continue
        if lowered not in _DOC_NAMES and "requirement" not in lowered:
            continue
        text = _read_text(path)
        if not text:
            continue
        found.append(_doc(path.name, text))
        if len(found) == 6:
            break
    return found


def _doc(path: str, text: str) -> dict:
    title = ""
    body: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not title and line.startswith("#"):
            title = line.lstrip("#").strip()
            continue
        if not title:
            title = line[:120]
            continue
        body.append(line)
        if sum(len(part) for part in body) > 500:
            break
    return {"path": path, "title": title or path, "excerpt": " ".join(body)[:500]}


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _entry(path: str, ecosystem: str, name: str, version: str | None) -> dict:
    return {
        "path": path,
        "ecosystem": ecosystem,
        "name": name,
        "version": version,
    }


def _concrete(spec: str | None) -> str | None:
    if not spec:
        return None
    match = _VERSION.search(spec)
    if not match:
        return None
    parts = match.group(1).split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def _dockerfile(path: str, text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        found = _FROM.search(line)
        if not found:
            continue
        image = found.group(1)
        if image.lower() == "scratch":
            continue
        name_tag = image.split("@", 1)[0]
        if ":" in name_tag:
            image_name, tag = name_tag.rsplit(":", 1)
        else:
            image_name, tag = name_tag, ""
        short = image_name.rsplit("/", 1)[-1].lower()
        version = _concrete(tag)
        ecosystem = {
            "php": "php",
            "node": "node",
            "python": "python",
            "golang": "go",
            "go": "go",
            "ruby": "ruby",
        }.get(short, "docker")
        name = short if ecosystem != "docker" else short
        entries.append(_entry(path, ecosystem, "php" if short == "php" else name, version))
    return entries


def _composer_json(path: str, text: str) -> list[dict]:
    data = _json(text)
    if not isinstance(data, dict):
        return []
    return _composer_requires(path, data.get("require"), data.get("require-dev"))


def _composer_requires(path: str, *blocks: object) -> list[dict]:
    entries = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for name, spec in block.items():
            if not isinstance(name, str) or not isinstance(spec, str):
                continue
            ecosystem = "php" if name.lower() in {"php", "php-64bit"} else "composer"
            package = "php" if ecosystem == "php" else name
            entries.append(_entry(path, ecosystem, package, _concrete(spec)))
    return entries


def _composer_lock(path: str, text: str) -> list[dict]:
    data = _json(text)
    if not isinstance(data, dict):
        return []
    entries = []
    platform = data.get("platform")
    if isinstance(platform, dict):
        entries.extend(_composer_requires(path, platform))
    for key in ("packages", "packages-dev"):
        packages = data.get(key)
        if not isinstance(packages, list):
            continue
        for package in packages:
            if not isinstance(package, dict):
                continue
            name = package.get("name")
            version = package.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            ecosystem = "php" if name.lower() in {"php", "php-64bit"} else "composer"
            entries.append(_entry(path, ecosystem, "php" if ecosystem == "php" else name, _concrete(version)))
    return entries


def _package_json(path: str, text: str) -> list[dict]:
    data = _json(text)
    if not isinstance(data, dict):
        return []
    entries = []
    engines = data.get("engines")
    if isinstance(engines, dict):
        node = engines.get("node")
        if isinstance(node, str):
            entries.append(_entry(path, "node", "node", _concrete(node)))
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        for name, spec in block.items():
            if isinstance(name, str) and isinstance(spec, str):
                entries.append(_entry(path, "node", name, _concrete(spec)))
    return entries


def _go_mod(path: str, text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("go "):
            entries.append(_entry(path, "go", "go", _concrete(stripped[3:])))
            continue
        if stripped.startswith("require "):
            stripped = stripped[len("require "):].strip()
        parts = stripped.split()
        if len(parts) >= 2 and parts[1].startswith("v"):
            entries.append(_entry(path, "go", parts[0], _concrete(parts[1])))
    return entries


def _requirements(path: str, text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("-"):
            continue
        name, spec = re.split(r"[<>=!~]=?", stripped, maxsplit=1) if re.search(r"[<>=!~]", stripped) else (stripped, "")
        package = name.strip().split("[", 1)[0]
        if package:
            entries.append(_entry(path, "python", package, _concrete(spec or name)))
    return entries


def _pom(path: str, text: str) -> list[dict]:
    entries = []
    for tag in ("java.version", "maven.compiler.release", "maven.compiler.source"):
        found = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", text)
        if not found:
            continue
        version = _concrete(found.group(1))
        if version:
            entries.append(_entry(path, "java", "java", version))
            break
    for name, version in _POM_PAIR.findall(text):
        package = name.strip()
        if package:
            entries.append(_entry(path, "java", package, _concrete(version)))
    return entries


def _php_version_header(path: str, text: str) -> list[dict]:
    found = _PHP_VERSION.search(text)
    if found:
        version = _concrete(found.group(1))
        return [_entry(path, "php", "php", version)] if version else []
    major = _PHP_MAJOR.search(text)
    minor = _PHP_MINOR.search(text)
    release = _PHP_RELEASE.search(text)
    if not (major and minor and release):
        return []
    version = _concrete(f"{major.group(1)}.{minor.group(1)}.{release.group(1)}")
    return [_entry(path, "php", "php", version)] if version else []


_AC_INIT_PHP = re.compile(r"AC_INIT\(\s*\[PHP\]\s*,\s*\[([^\]]+)\]", re.IGNORECASE)


def _php_configure(path: str, text: str) -> list[dict]:
    found = _AC_INIT_PHP.search(text)
    if found:
        version = _concrete(found.group(1))
        return [_entry(path, "php", "php", version)] if version else []
    major = re.search(r"PHP_MAJOR_VERSION\s*,\s*(\d+)", text) or re.search(r"PHP_MAJOR_VERSION=(\d+)", text)
    minor = re.search(r"PHP_MINOR_VERSION\s*,\s*(\d+)", text) or re.search(r"PHP_MINOR_VERSION=(\d+)", text)
    release = re.search(r"PHP_RELEASE_VERSION\s*,\s*(\d+)", text) or re.search(r"PHP_RELEASE_VERSION=(\d+)", text)
    if not (major and minor and release):
        return []
    version = _concrete(f"{major.group(1)}.{minor.group(1)}.{release.group(1)}")
    return [_entry(path, "php", "php", version)] if version else []


def _gemfile(path: str, text: str) -> list[dict]:
    entries = []
    for name, spec in _GEM.findall(text):
        entries.append(_entry(path, "ruby", name, _concrete(spec)))
    return entries


def _json(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
