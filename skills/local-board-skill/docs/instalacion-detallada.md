# Instalación detallada: comando por comando

> **¿Solo vas a usarla desde Cursor?** Tenés la [instalación simple](instalacion.md), que usa solo prompts. Esta guía es para
> quien quiere ver (o correr) cada comando.

| Paso | Qué hacés |
|---|---|
| [1. Requisitos](#1-requisitos) | `python3` y `git` |
| [2. Instalar](#2-instalar) | Clonar y enlazar, o `npx skills add` |
| [3. Comprobar la instalación](#3-comprobar-la-instalación) | Correr los tests |
| [4. Credenciales de Jira](#4-credenciales-de-jira) | Para sincronizar |
| [5. Primer board, comando por comando](#5-primer-board-comando-por-comando) | Del `init_board.py` al plan |

> **Sobre las capturas.** Salen de ejecutar los scripts de este repo sobre un board y un repo de prueba (`~/pagos-demo`), sin
> credenciales ni red. Las rutas están acortadas. Los tests son los del repo. La captura de `npx skills add` es la salida real del CLI en un `HOME` falso.

---

## 1. Requisitos

| Qué | Para qué |
|---|---|
| `python3` | Todos los scripts; usan solo la biblioteca estándar (los tests corren en CI con Python 3.12) |
| `git` | `inventory_git.py` lee el historial de los repos |
| Un Jira Cloud y un token | Solo para `sync.sh` y `purge_bad_remote_links.py` |

## 2. Instalar

```bash
git clone git@github.com:josefigueredo/teamwayofwork.git && cd teamwayofwork
mkdir -p ~/.agents/skills ~/.claude/skills
ln -s "$PWD/skills/local-board-skill" ~/.agents/skills/local-board-skill
ln -s ../../.agents/skills/local-board-skill ~/.claude/skills/local-board-skill   # además, para Claude Code
```

`~/.agents/skills/` lo leen Codex, Copilot CLI, GitHub Copilot en VS Code, Cursor y Gemini CLI.

### Instalar solo la skill con `npx skills add`

Alternativa al `ln -s`: el CLI [`skills`](https://github.com/vercel-labs/skills) instala **solo la carpeta de esta skill**
(la que cumple la [especificación de Agent Skills](https://agentskills.io/specification)), sin que enlaces nada a mano.
Necesita Node (`npx`) y el clon del repo; se corre desde la raíz del clon:

```bash
DISABLE_TELEMETRY=1 npx skills@1.7.2 add . --skill local-board-skill -a cursor -a claude-code -g -y
```

![Terminal con npx skills add instalando local-board-skill en ~/.agents/skills y enlazándola desde ~/.claude/skills](img/terminal-npx-skills.png)

Lo que se comprobó corriéndolo con la versión 1.7.2, un `HOME` falso y la ruta del clon como fuente:

| Qué | Resultado |
|---|---|
| Descubrimiento | `--list` encuentra `auditing-repos` y `local-board-skill` en `skills/<nombre>/`; no lista nada más del repo |
| Dónde queda | Una **copia** en `~/.agents/skills/local-board-skill` (la lee Cursor) y un enlace `~/.claude/skills/local-board-skill -> ../../.agents/skills/local-board-skill` para Claude Code. Con `--copy` el enlace pasa a ser otra copia |
| Qué se copia | La carpeta completa (46 archivos: `SKILL.md`, `scripts/` con su `.env.example`, `tests/`, `docs/`, `.gitignore`), idéntica al original: `diff -r` no encuentra diferencias. `sync.sh` conserva el permiso de ejecución; los `.py` no lo tienen en el clon tampoco, y se corren con `python3` |
| Funciona desde ahí | En un proyecto de prueba ajeno al clon, con `env -i`, los scripts de la copia instalada (`init_board.py`, `create_asset.py` de épica a subtarea, `inventory_git.py`, `render_git_inventory.py`, `refresh_relations_catalog.py`, `validate_relations.py`, `generate_traceability.py`) corren sin errores; `init_board.py` deja `board/sync/.env` desde la plantilla que viaja junto a él. `sync.sh` y `purge_bad_remote_links.py` sin credenciales cortan con `missing JIRA_EMAIL / JIRA_API_TOKEN`. Las rutas del `SKILL.md` (`~/.agents/skills/local-board-skill/scripts/…`) resuelven, y la suite de la skill corrida desde la copia (`python3 -m unittest discover -s ~/.agents/skills/local-board-skill/tests`) da 39 tests OK |

Límites, para que no te sorprendan:

- **No se actualiza con `git pull`.** Lo instalado es una copia: después de traer cambios al clon, repetí el mismo comando.
  `npx skills update` no la revisa: con una fuente local dice `cannot be checked automatically (Local path)` y te indica volver a
  correr `add`.
- **Si ya la enlazaste a mano, `add` te reemplaza el enlace por una copia** (el clon no se toca, pero deja de ser la fuente
  de verdad). Si preferís seguir con `ln -s`, no corras este comando.
- El CLI avisa «Review skills before use; they run with full agent permissions»: esta skill corre scripts de Python y, con tus
  credenciales, solo escribe en Jira con `--apply-plan` o con `--apply`. Revisá el clon antes de instalar.
- `DISABLE_TELEMETRY=1` apaga la telemetría anónima del CLI, según su [README](https://github.com/vercel-labs/skills#telemetry).
- Usá siempre una versión fija (`skills@1.7.2`): lo descrito arriba es lo que se vio en esa versión.
- No se probó la fuente remota privada (`git@github.com:josefigueredo/…`), solo la ruta local; por eso el comando usa el clon.
- No se probó contra Jira real: las credenciales no se usaron.

> **Las skills de `harness/` (`jtk`, `wow`, `arq`, `pbmcp`, `ric`) no se instalan así.** Cada repo trae un `install.sh` que además
> deja un CLI en `~/.local/bin`, registra un servidor MCP o instala un hook, y `skills add` solo cubre carpetas de skills.
> Sus guías explican el camino correcto.

## 3. Comprobar la instalación

```bash
python3 -m unittest discover -s skills/local-board-skill/tests -p 'test*.py'
```

![Terminal con el resumen de los tests: Ran 35 tests, OK](img/terminal-tests.png)

CI corre lo mismo y además exige 90% de cobertura:
`python -m coverage run --source=skills/local-board-skill/scripts -m unittest discover -s skills/local-board-skill/tests -p "test*.py"`
y luego `python -m coverage report --fail-under=90` (necesita `pip install coverage`).

## 4. Credenciales de Jira

Solo para sincronizar. `init_board.py` deja `<board>/sync/.env` (y un `sync/.gitignore` que lo ignora) con esta plantilla:

```bash
JIRA_BASE_URL=https://tu-empresa.atlassian.net
JIRA_CLOUD_ID=              # opcional: si está, se usa api.atlassian.com/ex/jira/<id>
JIRA_EMAIL=vos@tu-empresa.com
JIRA_API_TOKEN=el-token     # https://id.atlassian.com/manage-profile/security/api-tokens
# SSL_CERT_FILE=/ruta/al/bundle-de-CA.pem    # opcional, para redes con CA propia
```

Los scripts también aceptan `JIRA_URL` en lugar de `JIRA_BASE_URL` y `JIRA_TOKEN` en lugar de `JIRA_API_TOKEN`. `sync.sh`
carga el `.env` solo; los otros scripts leen el entorno, así que exportá las variables o cargá el archivo vos.

## 5. Primer board, comando por comando

Desde la carpeta que contiene `board/` y los repos a inventariar (el workspace):

```bash
S=~/.agents/skills/local-board-skill/scripts
python3 $S/init_board.py --board-dir board --name "Pagos DEMO" --jira-project-key DEMO --jira-label pagos-demo --entity-id-prefix PAG
python3 $S/create_asset.py --board-dir board --type epic --summary "Cobros con tarjeta"
python3 $S/create_asset.py --board-dir board --type story --parent PAGE01 --summary "Como cajero, cobro con tarjeta"
python3 $S/create_asset.py --board-dir board --type task --parent PAGS01 --summary "Reintentar cobros rechazados" --repo pagos
```

![Terminal con el árbol del board: Board.md, _meta/, la jerarquía PAGE01 > PAGS01 > PAGT01 y sync/ con .env, grafo y estado](img/terminal-tablero.png)

Cada `create_asset.py` imprime el identificador que generó (`Created PAGE01: …`): usalo como `--parent`. Después, la evidencia:

```bash
python3 $S/inventory_git.py --workspace . --board-dir board --since 2000-01-01
python3 $S/render_git_inventory.py --board-dir board
python3 $S/refresh_relations_catalog.py --board-dir board --workspace . --output board/sync/relations.json
python3 $S/validate_relations.py --board-dir board
```

Y el plan, que **no escribe en Jira** pero sí lo consulta, así que necesita credenciales:

```bash
$S/sync.sh board --save-plan board/sync/.review-plan.json    # revisalo
$S/sync.sh board --apply-plan board/sync/.review-plan.json   # escribe en Jira
```

Sin credenciales, ambos terminan con `ERROR: missing JIRA_EMAIL / JIRA_API_TOKEN`. Con credenciales y sin ninguna de las
dos banderas, el código de `sync_board.py` imprime `DRY-RUN: use --save-plan, review it, then use --apply-plan.` (no lo
corrí: necesita Jira).

## Referencia rápida de scripts

| Script | Qué hace | Jira |
|---|---|---|
| `init_board.py` | Estructura inicial del board | No |
| `create_asset.py` | Crea una épica, historia, tarea o subtarea con su frontmatter | No |
| `inventory_git.py`, `render_git_inventory.py` | Inventario de commits (JSON) y su reporte en Markdown | No |
| `refresh_relations_catalog.py`, `validate_relations.py`, `generate_traceability.py` | Catálogo, validación y reporte de trazabilidad del grafo | No |
| `reconcile_inventory.py`, `import_git_evidence.py`, `enrich_commit_urls.py` | Resuelven commits en evidencia o exclusiones, importan evidencia y arreglan URLs | No |
| `rebuild_index.py` | Regenera el índice del board | No |
| `sync.sh --save-plan` | Plan (dry run) con checksum | Lee |
| `sync.sh --apply-plan` | Aplica el plan verificado | Escribe |
| `purge_bad_remote_links.py` | Lista los links remotos con `.git` que borraría; los borra solo con `--apply` | Lee; con `--apply`, borra |

El orden y el criterio de cada modo (bootstrap, desde el último sync, reconciliación histórica) están en la
[referencia](referencia.md#el-contrato-del-board) y, en detalle, en el `SKILL.md`.
