# local-board-skill

> 🚧 **Fase: Beta.** Se usa de verdad, todavía se ajusta con el uso. Apoyate y avisá si rompe. Ver el [ciclo de vida](../../../README.md#ciclo-de-vida).

Mantiene un board de trabajo local en Markdown — épics, historias, tareas y sub-tareas — trazado contra la evidencia de Git, y lo sincroniza con Jira sólo después de una aprobación explícita.

## El principio

El board vive en archivos Markdown versionados junto al código, no en la cabeza de nadie ni sólo en Jira. Cada entidad del board se relaciona con la evidencia que la sustenta — commits, specs, PRs — a través de un grafo de relaciones explícito, así que un hallazgo o un estado siempre se puede rastrear hasta el commit que lo originó.

Publicar en Jira es la última etapa, no la primera: primero se genera un plan de sincronización en modo *dry-run*, se lo revisa, y recién con la aprobación se aplica.

## Cuándo usarla

- Bootstrapear un board local desde cero para un proyecto nuevo
- Analizar los commits desde el último sync y relacionarlos con specs, tickets y capacidades
- Reconciliar evidencia histórica de Git que todavía no está vinculada a los assets de Jira
- Preparar y aplicar (con aprobación) una sincronización hacia Jira

## Instalación

Enlazá la skill donde tu runtime la busca, en vez de copiarla — así seguís una sola fuente de verdad y no una copia que se desactualiza:

```bash
ln -s "$PWD/skills/local-board-skill" ~/.agents/skills/local-board-skill
ln -s ../../.agents/skills/local-board-skill ~/.claude/skills/local-board-skill
```

`~/.agents/skills/` lo leen Codex, Copilot CLI, GitHub Copilot en VS Code, Cursor y Gemini CLI. Para Claude Code además hace falta el enlace en `~/.claude/skills/`.

## El contrato del board

Un board instanciado necesita:

- Un `Board.md` primario con frontmatter: `board_name`, `entity_glob`, `entity_id_prefix`, `sync_dir`, `relations_file`, `jira_project_key`, `jira_label`, `remote_link_namespace`.
- Un grafo de relaciones bajo `<sync_dir>`, nombrado según `relations_file`.
- Un archivo de estado de sync en `<sync_dir>/state.json` con `last_run`.
- Archivos de entidad Markdown que matchean `entity_glob`.
- Un directorio `_meta/` con la documentación mantenida por personas y por la skill.

`init_board.py` crea toda esa estructura inicial de una vez. El detalle completo de los tres modos de operación (bootstrap, análisis desde el último sync, reconciliación histórica), el contrato de `jira-config.json` y los comandos disponibles está en `SKILL.md`, en inglés porque lo consume el modelo.

## Configuración de Jira

Completá tus credenciales en `<board-dir>/sync/.env`; nunca commiteés ese archivo:

```bash
cp scripts/.env.example <board-dir>/sync/.env   # solo si tu board no se creó con init_board.py
```

> **Nota (corregida respecto de la versión anterior de este README).** `init_board.py` ya crea `<board-dir>/sync/.env`
> a partir de esa plantilla, y un `sync/.gitignore` que lo ignora, así que el `cp` solo hace falta si el board se armó
> a mano. Las variables que lee `sync_board.py` son `JIRA_EMAIL`, `JIRA_API_TOKEN` (o `JIRA_TOKEN`) y, para la URL,
> `JIRA_CLOUD_ID` (si está, usa `api.atlassian.com`) o `JIRA_BASE_URL` / `JIRA_URL` (HTTPS obligatorio).

## Scripts

Todos son ejecutables desde `scripts/`. El punto de entrada para sincronizar es:

```bash
scripts/sync.sh <board-dir> --save-plan <board-dir>/sync/.review-plan.json
scripts/sync.sh <board-dir> --apply-plan <board-dir>/sync/.review-plan.json
```

`--save-plan` no escribe nada en Jira. `--apply-plan` verifica el plan guardado y el checksum del grafo antes de aplicar cambios remotos.
