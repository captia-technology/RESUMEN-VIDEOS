# Instalación

Guía para instalar la skill `resumir-video` en Claude Code, GitHub Copilot y OpenAI Codex, actualizarla y desinstalarla. Las capacidades se describen en [capacidades.md](capacidades.md).

Estado: versión 0.2.0 (2026-09-18). Las órdenes de catálogo se comprobaron con una copia local del repositorio (por ruta y como copia Git que sustituía a `captia-technology/RESUMEN-VIDEOS`); los clientes, sus versiones y los resultados figuran en [plan.md](plan.md#validación-2026-09-17). La instalación desde GitHub (incluidos VS Code, el bloque de equipo y los instaladores de terceros) está pendiente de evidencia hasta publicar el repositorio. Los sistemas de plugins cambian con frecuencia: si una orden no existe en tu versión, actualiza el cliente o usa la [instalación como skill independiente](#5-skill-independiente-sin-plugins).

## Resumen

El repositorio es a la vez un **catálogo de plugins** (marketplace) llamado `resumen-videos` y el origen de la skill:

| Cliente | Método recomendado | Invocación |
| --- | --- | --- |
| Claude Code | Plugin: `claude plugin marketplace add captia-technology/RESUMEN-VIDEOS` y `claude plugin install resumir-video@resumen-videos` | `/resumir-video "ruta/video.mp4"` |
| GitHub Copilot CLI | Plugin: `copilot plugin marketplace add captia-technology/RESUMEN-VIDEOS` y `copilot plugin install resumir-video@resumen-videos` | `/resumir-video "ruta/video.mp4"` |
| VS Code (Copilot Chat) | Plugin: **Chat: Install Plugin from Source** → `captia-technology/RESUMEN-VIDEOS` | `/resumir-video "ruta/video.mp4"` |
| Codex CLI 0.131+ y app | Plugin: `codex plugin marketplace add captia-technology/RESUMEN-VIDEOS` y `codex plugin add resumir-video@resumen-videos` | `$resumir-video:resumir-video "ruta/video.mp4"` |
| Codex en el IDE, clientes sin plugins | Skill independiente: `python3 scripts/install.py` | `$resumir-video` o `/resumir-video` |

Instala cada skill por **un solo canal** en cada entorno. Si el plugin convive con otra copia de `resumir-video` en una carpeta de skills, del proyecto (`.github/skills`, `.agents/skills`, `.claude/skills`) o personal (`~/.agents/skills`, `~/.copilot/skills` o `$COPILOT_HOME/skills`), Copilot usa esa copia y oculta el plugin, y Codex muestra las dos (`resumir-video` y `resumir-video:resumir-video`). `scripts/install.py` instala en `~/.agents/skills`, que comparten Codex y Copilot: si usas el plugin en Copilot, no instales ahí la skill independiente para Codex.

## 1. Requisitos previos

| Requisito | Windows | macOS | Linux (Debian/Ubuntu) |
| --- | --- | --- | --- |
| Python 3.10+ (con `venv` para la transcripción) | `winget install Python.Python.3.12` | `brew install python` | `sudo apt install python3 python3-venv` (Ubuntu 22.04+ o Debian 12+) |
| FFmpeg con libx264 y AAC | `winget install Gyan.FFmpeg` o `scoop install ffmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Git (catálogos desde GitHub) | `winget install Git.Git` | `xcode-select --install` | `sudo apt install git` |

Algunas compilaciones de FFmpeg (variantes LGPL, `ffmpeg-free` de Fedora) no incluyen libx264. En Windows, `video.py` necesita los ejecutables `ffmpeg.exe` y `ffprobe.exe` en PATH; un envoltorio `.cmd` o `.bat` no sirve. El agente debe poder inspeccionar imágenes. `faster-whisper` es opcional y se instala solo si hace falta transcribir; véase la [referencia de operación](../plugins/resumir-video/skills/resumir-video/references/operacion.md#transcripción-opcional).

**Opcionales.** Pandoc, `python-docx` y Pillow no son obligatorios; sin ellos la skill se degrada en vez de fallar: sin Pandoc ni `python-docx`, el documento se entrega solo en Markdown (sin DOCX); sin Pillow, el timeline del informe queda solo en texto. `check` informa de cada uno en `degraded`, redactado, pero ninguno de los tres cambia su código de salida. En Windows, si `faster-whisper` no encuentra las DLL de CUDA/cuDNN, pasa su carpeta con `--dll-dir` (repetible) a `transcribe`.

Comprueba el entorno con `video.py check`. La ruta depende de la carpeta desde la que lo ejecutes:

```text
python3 plugins/resumir-video/skills/resumir-video/scripts/video.py check   # raíz de una copia del repositorio
python3 skills/resumir-video/scripts/video.py check                         # raíz del plugin instalado (ubicaciones en la sección 6)
python3 scripts/video.py check                                              # carpeta de la skill instalada, p. ej. ~/.agents/skills/resumir-video
```

En Windows usa `python` o `py -3` en lugar de `python3`. `check` imprime siempre un JSON, que termina en `"ok": true` cuando Python 3.10+, `ffmpeg`, `ffprobe`, libx264 y AAC están disponibles, e incluye el espacio libre de la unidad actual (`disk_free_gb`). Las claves se describen en la [referencia de operación](../plugins/resumir-video/skills/resumir-video/references/operacion.md#comprobar-el-entorno).

### Acceso al repositorio

`captia-technology/RESUMEN-VIDEOS` es un repositorio de la organización. Si es privado, cada cliente usa tus credenciales de Git para clonarlo. Comprueba antes que `git ls-remote https://github.com/captia-technology/RESUMEN-VIDEOS.git` funciona; con GitHub CLI basta `gh auth login` seguido de `gh auth setup-git`. Sin acceso a GitHub, obtén una copia del repositorio por otra vía y usa la **ruta local de esa copia de trabajo** en lugar de `captia-technology/RESUMEN-VIDEOS` en las órdenes de catálogo. Las CLI de Claude Code, Copilot y Codex rechazan como catálogo una URL `file://` y un repositorio bare.

## 2. Claude Code

### Plugin

Dentro de una sesión:

```text
/plugin marketplace add captia-technology/RESUMEN-VIDEOS
/plugin install resumir-video@resumen-videos
```

Desde la terminal:

```text
claude plugin marketplace add captia-technology/RESUMEN-VIDEOS
claude plugin install resumir-video@resumen-videos
```

`claude plugin install` acepta `--scope user|project|local` (por defecto `user`). Reinicia la sesión para cargar el plugin y compruébalo con `claude plugin list`. Invoca `/resumir-video "ruta/video.mp4"`; si otra skill usa ese nombre, usa la forma cualificada `/resumir-video:resumir-video`.

| Tarea | Orden |
| --- | --- |
| Actualizar el catálogo | `claude plugin marketplace update resumen-videos` |
| Actualizar el plugin | `claude plugin update resumir-video@resumen-videos` (requiere reiniciar) |
| Aplicar cambios de una copia local | `claude plugin update` solo los aplica si cambia la versión; durante el desarrollo usa `--plugin-dir` |
| Desinstalar | `claude plugin uninstall resumir-video@resumen-videos` |
| Quitar el catálogo | `claude plugin marketplace remove resumen-videos` |
| Probar sin instalar | `claude --plugin-dir plugins/resumir-video` desde una copia del repositorio; si el plugin también está instalado, se cargan las dos copias (desactívalo antes con `claude plugin disable resumir-video@resumen-videos`) |
| Validar | `claude plugin validate plugins/resumir-video --strict` y `claude plugin validate . --strict` |

### Distribución a un equipo

Añade esto al `.claude/settings.json` del proyecto del equipo. Claude Code propone el catálogo y el plugin al abrir el proyecto. La CLI de Copilot también lee este archivo y ofrece el catálogo, pero el plugin se instala con `copilot plugin install resumir-video@resumen-videos`:

```json
{
  "extraKnownMarketplaces": {
    "resumen-videos": {
      "source": { "source": "github", "repo": "captia-technology/RESUMEN-VIDEOS" }
    }
  },
  "enabledPlugins": {
    "resumir-video@resumen-videos": true
  }
}
```

## 3. GitHub Copilot

### Copilot CLI

Instala la CLI si no la tienes (`npm install -g @github/copilot` o `winget install GitHub.Copilot`) y después:

```text
copilot plugin marketplace add captia-technology/RESUMEN-VIDEOS
copilot plugin install resumir-video@resumen-videos
```

Dentro de una sesión existen las mismas órdenes con `/plugin …`. Verifica con `copilot plugin list` y `copilot skill list` o, en la sesión, con `/skills info resumir-video`. En las sesiones interactivas, la CLI solo carga plugins y skills en carpetas de confianza.

| Tarea | Orden |
| --- | --- |
| Actualizar | `copilot plugin marketplace update resumen-videos` y `copilot plugin update resumir-video` |
| Desactivar o activar | `copilot plugin disable resumir-video` / `copilot plugin enable resumir-video` |
| Desinstalar | `copilot plugin uninstall resumir-video` |
| Probar sin instalar | `copilot --plugin-dir ./plugins/resumir-video` |

Con un catálogo de **ruta local**, la CLI no copia el plugin: lo carga en vivo desde `<ruta>/plugins/resumir-video` en cada sesión nueva (`copilot plugin list` lo muestra en «Live Plugins»). Para actualizarlo, actualiza esa copia (por ejemplo, con `git pull`); `copilot plugin update` no hace nada. `copilot plugin uninstall resumir-video` solo lo desactiva: para quitarlo de la lista, ejecuta además `copilot plugin marketplace remove resumen-videos`. No muevas ni borres la copia mientras uses el plugin, porque desaparece sin aviso.

Las instalaciones directas (`copilot plugin install OWNER/REPO:ruta`) están en desuso; usa el catálogo.

### VS Code

Requiere VS Code 1.133 o posterior con GitHub Copilot Chat y la opción `chat.plugins.enabled` activa (lo está por defecto).

1. Abre la paleta de comandos y ejecuta **Chat: Install Plugin from Source** (con la interfaz en español puede aparecer traducida).
2. Escribe `captia-technology/RESUMEN-VIDEOS` (o la ruta de una copia local) y elige `resumir-video`.
3. En el chat en modo agente, escribe `/resumir-video "ruta/video.mp4"`.

Para ofrecer el catálogo de forma permanente, añádelo a `chat.plugins.marketplaces` en la configuración de usuario (es un ajuste experimental). Ese valor sustituye a la lista por defecto, así que conserva sus entradas. También admite una copia local como `file:///ruta/al/repositorio`:

```json
"chat.plugins.marketplaces": [
  "github/copilot-plugins",
  "github/awesome-copilot#marketplace",
  "captia-technology/RESUMEN-VIDEOS"
]
```

Después busca `@agentPlugins` en la vista de extensiones. VS Code también muestra los plugins que la CLI de Copilot instala en `~/.copilot/installed-plugins/` (no los cargados en vivo desde una ruta local).

### Agente en la nube de Copilot

Escenario no comprobado (pendiente de evidencia). El agente en la nube solo usa plugins declarados en el repositorio (`.github/copilot/settings.json`, con el mismo contenido que el bloque de equipo de Claude Code) o skills versionadas en `.github/skills`, `.agents/skills` o `.claude/skills`. Además necesita Python y FFmpeg en `.github/workflows/copilot-setup-steps.yml` y el vídeo dentro del repositorio (Git LFS para archivos grandes). No tiene invocación con `/`: menciona la skill y la ruta en la tarea. Es un escenario posible pero poco práctico para vídeos locales.

## 4. OpenAI Codex

Los plugins, también desde catálogos alojados en GitHub, requieren Codex CLI 0.131 o posterior, o la app de escritorio. Actualiza con `npm install -g @openai/codex@latest` y comprueba la versión con `codex --version`.

```text
codex plugin marketplace add captia-technology/RESUMEN-VIDEOS
codex plugin add resumir-video@resumen-videos
```

Abre una conversación nueva y usa `$resumir-video:resumir-video "ruta/video.mp4"`, o elige la skill con `/skills`. En la app, el plugin aparece en la pestaña de plugins (en versiones recientes de la CLI, también con `/plugins`).

| Tarea | Orden |
| --- | --- |
| Ver estado | `codex plugin list --marketplace resumen-videos` |
| Actualizar | Catálogo de GitHub: `codex plugin marketplace upgrade resumen-videos` (también actualiza el plugin instalado). Copia local: actualiza la copia (por ejemplo, con `git pull`) y repite `codex plugin add resumir-video@resumen-videos`; `marketplace upgrade` solo admite catálogos Git. |
| Desinstalar | `codex plugin remove resumir-video@resumen-videos` |
| Quitar el catálogo | Primero `codex plugin remove resumir-video@resumen-videos` y después `codex plugin marketplace remove resumen-videos`; en el orden inverso, el plugin sigue activo pero deja de aparecer en `codex plugin list` |
| Usar una copia local | `codex plugin marketplace add <ruta-del-repositorio>` (elimina antes cualquier `__pycache__`: Codex copia la carpeta tal cual) |

Codex lee el catálogo nativo `.agents/plugins/marketplace.json`. Desde la 0.146 toma nombre, versión y descripción de `plugin.json` y la interfaz de `.codex-plugin/plugin.json`; de la 0.131 a la 0.145 solo lee `.codex-plugin/plugin.json` (y, si falta, `.claude-plugin/plugin.json`). Por eso los tres manifiestos deben tener los mismos metadatos. La **extensión de Codex para IDE no admite plugins**: en ella instala la skill independiente (sección siguiente) e invócala con `$resumir-video`.

Para desactivar la skill o el plugin sin desinstalarlo, edita `$CODEX_HOME/config.toml` (por defecto `~/.codex/config.toml`). Para la skill independiente, añade un bloque `[[skills.config]]` con `path = "<carpeta de skills>/resumir-video/SKILL.md"` y `enabled = false`; para el plugin, cambia `enabled = true` por `enabled = false` en `[plugins."resumir-video@resumen-videos"]`. Ambas opciones desactivan la skill por completo, incluida la invocación con `$`.

## 5. Skill independiente (sin plugins)

`scripts/install.py` copia la skill en las carpetas que cada cliente examina. Solo usa la biblioteca estándar:

```text
git clone https://github.com/captia-technology/RESUMEN-VIDEOS.git
cd RESUMEN-VIDEOS
python3 scripts/install.py                         # todos los agentes, ámbito personal
python3 scripts/install.py --agent codex           # solo Codex (y Copilot, que comparte carpeta si COPILOT_HOME no está definida)
python3 scripts/install.py --scope project --project-dir ../mi-proyecto
python3 scripts/install.py --status                # estado sin cambiar nada
python3 scripts/install.py --force                 # actualizar una versión anterior
python3 scripts/install.py --uninstall
```

| Opción | Efecto |
| --- | --- |
| `--agent claude\|codex\|copilot\|all` | Destino; repetible. Por defecto `all`. |
| `--scope user\|project` | Carpeta personal o del proyecto. Por defecto `user`. |
| `--project-dir DIR` | Proyecto **existente** para `--scope project` (por defecto, el directorio actual). |
| `--status` | Informa de `ausente`, `actualizada`, `desactualizada`, `enlace` o `ajena`. |
| `--force` | Reemplaza una copia `desactualizada` o un `enlace` (sin tocar su destino); con `--uninstall`, permite eliminar una copia `desactualizada`. |
| `--dry-run` | Muestra lo que haría. |
| `--uninstall` | Elimina la copia instalada o el enlace. |
| `--skip-check` | No ejecuta `video.py check` tras instalar. |

| Ámbito | Claude Code | Codex | GitHub Copilot |
| --- | --- | --- | --- |
| Personal | `$CLAUDE_CONFIG_DIR/skills` o `~/.claude/skills` | `~/.agents/skills` | `~/.agents/skills` (o `$COPILOT_HOME/skills` si está definida) |
| Proyecto | `.claude/skills` | `.agents/skills` | `.agents/skills` |

Con `COPILOT_HOME` definida, la CLI de Copilot puede seguir mostrando como heredada una copia de `~/.agents/skills` si trabajas en una carpeta de tu directorio personal que no es un repositorio Git; instala por un solo destino.

Cómo decide el instalador:

- Reconoce la skill por la línea `name` del frontmatter de `SKILL.md` (`resumir-video`, con o sin comillas). Nunca modifica una carpeta `resumir-video` que declare otro nombre (estado `ajena`).
- Una carpeta con ese nombre y contenido distinto (versión anterior, cambios locales o metadatos añadidos por otro instalador) queda `desactualizada`: reemplazarla o eliminarla requiere `--force`, y se sustituye o elimina entera, incluidos los archivos añadidos.
- Detecta como `enlace` los enlaces simbólicos y las uniones de Windows, también los rotos; los sustituye o elimina sin tocar su destino.
- Los archivos de solo lectura no bloquean `--force` ni `--uninstall`, y las copias instaladas quedan con permiso de escritura. Limpia los restos `.resumir-video.nuevo` y `.resumir-video.anterior` de una ejecución interrumpida.
- Al comparar y copiar ignora `__pycache__`, `*.pyc`, `.DS_Store`, `Thumbs.db` y `desktop.ini`. Tras instalar ejecuta `video.py check`, salvo con `--skip-check`.

Abre una sesión nueva del agente o recarga las skills (`/skills reload` en Copilot CLI) para que aparezca.

Copia manual equivalente, desde la raíz del repositorio. Claude Code usa su propia carpeta (`$CLAUDE_CONFIG_DIR/skills` si está definida); si solo usas uno de los agentes, copia únicamente en su carpeta:

```text
# macOS / Linux / Git Bash
mkdir -p ~/.agents/skills ~/.claude/skills
cp -R plugins/resumir-video/skills/resumir-video ~/.agents/skills/   # Codex y Copilot
cp -R plugins/resumir-video/skills/resumir-video ~/.claude/skills/   # Claude Code
# PowerShell (Codex y Copilot; Claude Code)
foreach ($d in "$HOME\.agents\skills", "$HOME\.claude\skills") {
  New-Item -ItemType Directory -Force $d | Out-Null
  Copy-Item -Recurse -Force plugins\resumir-video\skills\resumir-video $d
}
```

Para actualizar, repite la orden. La copia manual no borra los archivos que una versión nueva ya no incluya; `python3 scripts/install.py --force` reemplaza la copia completa.

### Instaladores de terceros

Estas herramientas instalan solo la carpeta de la skill, no forman parte del proyecto y sus opciones pueden cambiar. Vercel skills guarda una copia y, si instalas para varios agentes, enlaza desde ella las carpetas de los demás (salvo con `--copy`); `gh skill` añade metadatos de origen al `SKILL.md`.

- [Vercel skills](https://github.com/vercel-labs/skills) (Node 22.20+): `npx skills add captia-technology/RESUMEN-VIDEOS --skill resumir-video` (añade `-g` para ámbito personal y `-a claude-code` u otro agente para elegir destino).
- [GitHub CLI](https://cli.github.com/) 2.90+ (`gh skill`, vista previa): `gh skill install captia-technology/RESUMEN-VIDEOS resumir-video --agent claude-code --scope user`. Sin `--agent`, `gh` instala para GitHub Copilot (`~/.copilot/skills`); usa `--agent codex` para `~/.agents/skills` y omite `--scope user` para instalar en el proyecto. Como `gh` modifica el `SKILL.md`, `scripts/install.py --status` muestra esa copia como `desactualizada` (`--force` la sustituye por la del repositorio).
- Codex: `$skill-installer install https://github.com/captia-technology/RESUMEN-VIDEOS/tree/main/plugins/resumir-video/skills/resumir-video`. Copia la skill en `$CODEX_HOME/skills` (por defecto `~/.codex/skills`, carpeta heredada que Codex sigue leyendo), que `scripts/install.py` no gestiona. No sobrescribe una carpeta existente: para actualizar, borra `$CODEX_HOME/skills/resumir-video` y repite la orden. No la combines con el plugin ni con `scripts/install.py` (`~/.agents/skills`): Codex mostraría dos `resumir-video`.

## 6. Verificación

1. `video.py check` devuelve `"ok": true` (sección 1). La ruta de la skill instalada aparece con `/skills info resumir-video` en Copilot CLI o en el listado de skills del cliente.
2. El cliente lista la skill: `claude plugin list` (y `claude plugin details resumir-video@resumen-videos`, que debe mostrar `Skills (1) resumir-video`), `copilot plugin list` y `copilot skill list`, `codex plugin list` o el selector `/skills`.
3. Opcional: ejecuta las pruebas de la skill **fuera** de la caché de plugins, desde una copia del repositorio:

```text
python3 -B -m unittest discover -s plugins/resumir-video/skills/resumir-video/scripts -p "test_*.py"
```

Ubicaciones de las copias instaladas como plugin:

| Cliente | Carpeta |
| --- | --- |
| Claude Code | `~/.claude/plugins/cache/resumen-videos/resumir-video/<versión>/` (cambia si defines `CLAUDE_CONFIG_DIR` o `CLAUDE_CODE_PLUGIN_CACHE_DIR`). Tras actualizar o desinstalar, la versión anterior queda marcada con `.orphaned_at`. |
| Copilot CLI | `~/.copilot/installed-plugins/resumen-videos/resumir-video/` (o `$COPILOT_HOME/installed-plugins/…` si `COPILOT_HOME` está definida). Con un catálogo de ruta local no se copia nada: el plugin se carga desde esa copia. |
| Codex | `$CODEX_HOME/plugins/cache/resumen-videos/resumir-video/<versión>/` (por defecto bajo `~/.codex`). |

No edites esas copias: se sustituyen al actualizar.

## 7. Publicar una versión nueva

1. Actualiza el número de versión en `CHANGELOG.md`, los tres `plugin.json`, `.claude-plugin/marketplace.json` (`metadata.version` y `plugins[0].version`), `SKILL.md` (`metadata.version`), `video.py` (`__version__`), `README.md` («Versión X.Y.Z ·»), el primer párrafo de `docs/capacidades.md` y la línea «Estado: versión X.Y.Z (fecha)» de este documento.
2. Ejecuta las pruebas y los validadores ([AGENTS.md](../AGENTS.md)).
3. Haz commit de los cambios y crea la etiqueta `resumir-video--v<versión>` con `claude plugin tag plugins/resumir-video` (prueba antes con `--dry-run`). La orden rechaza cambios sin commit que afecten a la versión y comprueba que `.claude-plugin/plugin.json` coincide con su entrada del catálogo; `--push` la publica.

Los usuarios de plugins reciben la versión con las órdenes de actualización de cada cliente, y VS Code detecta la actualización al cambiar la versión del manifiesto y del catálogo. Las copias de `$skill-installer` y las copias manuales se actualizan a mano (sección 5).

## 8. Solución de problemas

| Síntoma | Causa y solución |
| --- | --- |
| La skill no aparece | Abre una sesión nueva; en Copilot CLI, `/skills reload`. Comprueba que la carpeta es de confianza. |
| Aparece dos veces o el plugin no se usa | Hay otra copia en una carpeta de skills del proyecto (`.claude/skills`, `.agents/skills`, `.github/skills`) o personal (`~/.agents/skills`, `~/.copilot/skills`, `$COPILOT_HOME/skills`, `~/.codex/skills`); compruébalo con `/skills info resumir-video` o `copilot skill list`. Deja un solo canal. |
| `error: unexpected argument 'marketplace' found` (o `'list'`), o `error: unrecognized subcommand 'add'` al ejecutar `codex plugin …` | Codex CLI sin soporte completo de plugins (anterior a 0.131). Comprueba `codex --version`; actualiza con `npm install -g @openai/codex@latest` o usa la skill independiente. |
| Error al añadir el catálogo | Sin acceso al repositorio privado: revisa `gh auth setup-git` o usa la ruta de una copia de trabajo local (no una URL `file://` ni un repositorio bare). |
| `Filename too long` al añadir un catálogo de GitHub (Windows) | La carpeta de configuración o de caché del cliente tiene una ruta muy larga (`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PLUGIN_CACHE_DIR`, `CODEX_HOME`, `COPILOT_HOME` o `COPILOT_CACHE_HOME`). Usa una ruta más corta; `core.longpaths` no lo evita. Con las rutas por defecto no se ha observado. |
| `"libx264": false` o `FFmpeg no incluye libx264` | Instala una compilación completa de FFmpeg. |
| `"ffmpeg": null` o `Falta ffmpeg en PATH` | FFmpeg no está en PATH o, en Windows, solo hay un envoltorio `.cmd` o `.bat` (aunque `ffmpeg` funcione en la terminal): pon en PATH los ejecutables `ffmpeg.exe` y `ffprobe.exe`. |
| `check` muestra un valor en `"error"` | FFmpeg está instalado pero falla al ejecutarse; el texto indica el motivo. Reinstálalo. |
| `python3` no existe en Windows | Usa `python` o `py -3`. |
| `"python_ok": false` o `Se requiere Python 3.10 o superior` | Instala una versión reciente y usa ese intérprete. |
| `ensurepip is not available` al crear el entorno de transcripción | Debian/Ubuntu separan `venv`: `sudo apt install python3-venv` y repite la orden. |
| Texto con caracteres extraños en Windows (por ejemplo, `V├¡deo`) | `video.py` escribe siempre en UTF-8, pero Windows PowerShell 5.1 y `cmd` lo leen con la página de códigos OEM. Cambia la consola a UTF-8 antes de abrir el agente o de ejecutar el script: `chcp 65001` o, en PowerShell, `[Console]::OutputEncoding = [Text.Encoding]::UTF8`. |
| `La carpeta ya existe y no se sobrescribe` | Indica una carpeta nueva (por ejemplo, con el sufijo `-2`); no crees la carpeta antes de `prepare`, `frames` o `render`. |
| `install.py` indica `desactualizada` | La copia difiere de la del repositorio (versión anterior, cambios locales o metadatos de `gh skill`). `--force` la reemplaza y, con `--uninstall`, la elimina. |
| `Error: no existe la carpeta del proyecto …` | `--project-dir` debe apuntar a una carpeta existente. |
| El montaje supera el tiempo máximo de una orden del agente | Acota cada llamada con `--budget`: cada corte se verifica y se cachea en `cortes/` antes de contar, así que una llamada que se queda a medias devuelve código 3 sin perder lo ya montado. Repite la misma orden con `--plan` y `--out` para continuar, o ejecuta `render` en segundo plano si el cliente lo permite. |
