"""Install, update, inspect or remove the resumir-video skill as a standalone skill.

Targets (duplicates are merged, so Codex and Copilot share one copy):
  scope user:    Claude Code  -> $CLAUDE_CONFIG_DIR/skills or ~/.claude/skills
                 Codex        -> ~/.agents/skills
                 Copilot      -> ~/.agents/skills, or $COPILOT_HOME/skills when set
  scope project: Claude Code  -> <project>/.claude/skills
                 Codex/Copilot-> <project>/.agents/skills
"""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

NAME = "resumir-video"
SOURCE = Path(__file__).resolve().parent.parent / "plugins" / NAME / "skills" / NAME
AGENTS = ("claude", "codex", "copilot")
IGNORED = ("__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini")
# Windows reparse tags for symlinks and junctions (stat.IO_REPARSE_TAG_* only exist on Windows).
LINK_TAGS = (0xA000000C, 0xA0000003)
INVOCATION = {"claude": f'/{NAME} "ruta/video.mp4"', "codex": f'${NAME} "ruta/video.mp4"',
              "copilot": f'/{NAME} "ruta/video.mp4"'}


def skills_dir(agent, scope, project):
    if scope == "project":
        return project / (".claude" if agent == "claude" else ".agents") / "skills"
    if agent == "claude":
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "skills"
    if agent == "copilot" and os.environ.get("COPILOT_HOME"):
        # With a custom COPILOT_HOME the Copilot CLI only reads $COPILOT_HOME/skills.
        return Path(os.environ["COPILOT_HOME"]) / "skills"
    return Path.home() / ".agents" / "skills"


def targets(agents, scope, project):
    found = {}
    for agent in agents:
        found.setdefault(skills_dir(agent, scope, project) / NAME, []).append(agent)
    return found


def files(folder):
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if path.is_file() and not any(part in IGNORED or part.endswith(".pyc") for part in relative.parts):
            yield relative


def digest(folder):
    total = hashlib.sha256()
    for relative in files(folder):
        total.update(relative.as_posix().encode("utf-8") + b"\0")
        total.update(hashlib.sha256((folder / relative).read_bytes()).digest())
    return total.hexdigest()


def is_link(path):
    # Covers symlinks and Windows junctions (e.g. created by other skill installers), even dangling ones.
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    if path.is_symlink() or getattr(info, "st_reparse_tag", 0) in LINK_TAGS:
        return True
    expected = os.path.join(os.path.realpath(path.parent), path.name)
    return path.exists() and os.path.normcase(os.path.realpath(path)) != os.path.normcase(expected)


def is_ours(path):
    manifest = path / "SKILL.md"
    if not manifest.is_file():
        return False
    head = manifest.read_text(encoding="utf-8", errors="replace").split("\n---", 1)[0]
    names = {f"name: {NAME}", f'name: "{NAME}"', f"name: '{NAME}'"}
    return any(line.strip() in names for line in head.splitlines())


def status(dest):
    if is_link(dest):
        return "enlace"
    if not dest.exists():
        return "ausente"
    if not is_ours(dest):
        return "ajena"
    return "actualizada" if digest(dest) == digest(SOURCE) else "desactualizada"


def make_writable(path):
    os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IWRITE)


def retry_writable(func, path, _error):
    # Read-only files (Windows) or folders (POSIX) block deletion: clear the flag and retry.
    for target in (os.path.dirname(path), path):
        if os.path.lexists(target) and not os.path.islink(target):
            make_writable(target)
    func(path)


def remove_tree(path):
    handler = {"onexc" if sys.version_info >= (3, 12) else "onerror": retry_writable}
    shutil.rmtree(path, **handler)


def copy(dest):
    # copyfile does not carry a read-only mode from the source, so the copy can be updated or removed.
    shutil.copytree(SOURCE, dest, ignore=shutil.ignore_patterns(*IGNORED, "*.pyc"),
                    copy_function=shutil.copyfile)
    for root, dirs, _ in os.walk(dest):
        for name in dirs:
            make_writable(os.path.join(root, name))
    make_writable(dest)


def clean_leftovers(dest):
    # Leftovers of an interrupted run; a client would still list those hidden folders as skills.
    for leftover in (dest.with_name(f".{NAME}.nuevo"), dest.with_name(f".{NAME}.anterior")):
        if is_link(leftover):
            remove_link(leftover)
        elif leftover.exists():
            remove_tree(leftover)


def install(dest, force, dry_run):
    state = status(dest)
    if state == "ajena":
        raise ValueError(f"{dest} existe y no es esta skill; no se modifica.")
    if state == "actualizada":
        if not dry_run:
            clean_leftovers(dest)
        return "ya instalada y actualizada"
    if state in ("enlace", "desactualizada") and not force:
        raise ValueError(f"{dest} existe ({state}); usa --force para reemplazarla.")
    if dry_run:
        return f"se instalaría ({state})"
    dest.parent.mkdir(parents=True, exist_ok=True)
    staged, old = dest.with_name(f".{NAME}.nuevo"), dest.with_name(f".{NAME}.anterior")
    clean_leftovers(dest)
    if state == "enlace":
        remove_link(dest)
    elif state == "desactualizada":
        copy(staged)
        dest.rename(old)
        staged.rename(dest)
        remove_tree(old)
        return "actualizada"
    # Staged like the update: an interrupted copy must never leave a half-written skill folder.
    copy(staged)
    staged.rename(dest)
    return "instalada" if state == "ausente" else "reemplazado el enlace por una copia"


def remove_link(path):
    # rmdir removes a Windows junction without touching its target; unlink handles symlinks.
    try:
        path.unlink()
    except (IsADirectoryError, PermissionError):
        os.rmdir(path)


def uninstall(dest, force, dry_run):
    state = status(dest)
    if state == "ajena":
        raise ValueError(f"{dest} no es esta skill; no se elimina.")
    if state == "desactualizada" and not force:
        raise ValueError(f"{dest} tiene otro contenido ({state}); usa --force para eliminarla.")
    if dry_run:
        return "no estaba instalada" if state == "ausente" else f"se eliminaría ({state})"
    clean_leftovers(dest)
    if state == "ausente":
        return "no estaba instalada"
    if state == "enlace":
        remove_link(dest)
        return "enlace eliminado (el destino no se toca)"
    # Move aside first: a deletion that fails halfway would leave a skill the client still lists.
    old = dest.with_name(f".{NAME}.anterior")
    try:
        dest.rename(old)
    except OSError as exc:
        raise ValueError(f"{dest} está en uso y no se puede eliminar ({exc.strerror}); "
                         "cierra los programas que la usen y reinténtalo.") from exc
    remove_tree(old)
    return "eliminada"


def check(dest):
    result = subprocess.run([sys.executable, "-B", str(dest / "scripts" / "video.py"), "check"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        print("Aviso: faltan requisitos para usar la skill (salida de video.py check):")
        print(result.stdout or result.stderr)
    else:
        print("Requisitos comprobados: Python, FFmpeg, libx264 y AAC disponibles.")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Instala, actualiza, consulta o elimina la skill resumir-video como skill independiente "
                    "en las carpetas de skills de Claude Code, Codex y GitHub Copilot. Codex y Copilot "
                    "comparten copia, así que los destinos repetidos se unifican.")
    parser.add_argument("--agent", action="append", choices=(*AGENTS, "all"),
                        help="Agente destino; repetible (por defecto all).")
    parser.add_argument("--scope", choices=("user", "project"), default="user",
                        help="Instalación personal o del proyecto (por defecto user).")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(),
                        help="Raíz de un proyecto existente para --scope project (por defecto, el directorio actual).")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="Muestra el estado sin cambiar nada.")
    action.add_argument("--uninstall", action="store_true", help="Elimina la skill de los destinos.")
    parser.add_argument("--force", action="store_true",
                        help="Reemplaza o elimina una versión distinta de esta skill, o un enlace.")
    parser.add_argument("--dry-run", action="store_true", help="Indica lo que haría sin modificar nada.")
    parser.add_argument("--skip-check", action="store_true", help="No ejecuta video.py check al instalar.")
    args = parser.parse_args()
    agents = AGENTS if not args.agent or "all" in args.agent else tuple(dict.fromkeys(args.agent))
    if not (SOURCE / "SKILL.md").is_file():
        print(f"Error: no se encuentra la skill en {SOURCE}", file=sys.stderr)
        return 1
    project = args.project_dir.resolve()
    if args.scope == "project" and not project.is_dir():
        print(f"Error: no existe la carpeta del proyecto {project}", file=sys.stderr)
        return 1
    failed = False
    for dest, owners in targets(agents, args.scope, project).items():
        label = f"{', '.join(owners)} -> {dest}"
        try:
            if args.status:
                message = status(dest)
            elif args.uninstall:
                message = uninstall(dest, args.force, args.dry_run)
            else:
                message = install(dest, args.force, args.dry_run)
        except (ValueError, OSError) as exc:
            print(f"Error [{label}]: {exc}", file=sys.stderr)
            failed = True
            continue
        print(f"[{label}] {message}")
    if failed or args.status or args.uninstall or args.dry_run:
        return 1 if failed else 0
    if not args.skip_check:
        check(next(iter(targets(agents, args.scope, project))))
    print("Abre una sesión nueva del agente (o recarga las skills) y usa:")
    for agent in agents:
        print(f"  {agent}: {INVOCATION[agent]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
