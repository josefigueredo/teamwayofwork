# teamwayofwork

La forma de trabajo del equipo **team**: los procedimientos con los que trabajamos, las convenciones que acordamos, y las **AI skills** que los vuelven ejecutables en vez de dejarlos en un documento que nadie abre.

Un procedimiento que vive sólo en una wiki se cumple cuando alguien se acuerda. Acá cada procedimiento viaja con sus scripts y sus tests, así que la parte mecánica la hace la máquina y las personas se ocupan de las decisiones.

## Ciclo de vida

Todo lo que hay en este repo —skills, procedimientos, convenciones— tiene una fase declarada. La fase responde una sola pregunta: **¿cuánto puedo apoyarme en esto hoy?**

| Fase | Qué significa | ¿Me apoyo en esto? |
| --- | --- | --- |
| 🧪 **Incubation** | Se está explorando. Puede cambiar de forma o morir. | **No.** Probalo y reportá; no construyas encima. Cambios sin aviso. |
| 🚧 **Beta** | Se usa de verdad, todavía se ajusta con el uso. | **Sí, con red.** Apoyate y avisá si rompe. Los cambios se anuncian. |
| ✅ **Standardized** | Es **la** forma en que el equipo hace esto. | **Sí, por defecto.** Apartarse se justifica, no al revés. |
| ⚰️ **Deprecated** | Ya no es como trabajamos. Reemplazado o abandonado. | **No.** No empieces nada nuevo acá. Debe decir por qué y qué usar en su lugar. |

Cada fase responde una sola pregunta, y por eso son cuatro y no más: cuánto puedo apoyarme en esto hoy. Una fase intermedia con nombre ambiguo obliga a preguntar en el canal del equipo, que es exactamente el trabajo que la etiqueta tendría que ahorrar.

Una fase no se gana por antigüedad sino por uso: algo pasa a `Standardized` cuando el equipo lo aplicó varias veces, en contextos distintos, y dejó de encontrarle sorpresas.

`Deprecated` existe para que lo viejo pueda dejar de recomendarse sin desaparecer de golpe. Sin ese estado, lo que se abandona se queda marcado `Standardized` para siempre —y alguien lo va a seguir usando porque eso es lo que dice— o se borra sin dejar rastro de por qué.

## Skills

| Skill | Fase | Para qué |
| --- | --- | --- |
| [`auditing-repos`](skills/auditing-repos/) | 🧪 Incubation | Auditar un repositorio y convertir los hallazgos en issues, PRs y tickets de Jira, con una compuerta de aprobación antes de publicar nada |
| [`local-board-skill`](skills/local-board-skill/) | 🚧 Beta | Mantener un board de trabajo local trazado contra evidencia de Git y sincronizarlo con Jira sólo con aprobación explícita |
| [`install-unified-ci`](skills/install-unified-ci/) | 🧪 Incubation | Evaluar un repositorio, auditar compatibilidad con Unified CI, generar `.github/workflows/ci.yml` canónico y podar workflows obsoletos |

Cada skill tiene su `README.md` en castellano. El `SKILL.md` y los `references/` están en inglés a propósito: los consume el modelo.

### Tests automatizados

Las skills que incluyen scripts Python se validan en GitHub Actions por grupos independientes. Actualmente corre el grupo [`local-board-skill`](skills/local-board-skill/) con su suite bajo `skills/local-board-skill/tests/` y exige al menos 90% de cobertura sobre sus scripts:

```bash
python3 -m unittest discover -s skills/local-board-skill/tests -p 'test*.py' -v
```

Para sumar otra skill Python al workflow, agregá una entrada con sus directorios `source_dir` y `test_dir` en [`.github/workflows/python-skill-tests.yml`](.github/workflows/python-skill-tests.yml).

### Instalación

Enlazá la skill donde tu runtime la busca, en vez de copiarla — así seguís una sola fuente de verdad y no una copia que se desactualiza:

```bash
ln -s "$PWD/skills/auditing-repos" ~/.agents/skills/auditing-repos
ln -s ../../.agents/skills/auditing-repos ~/.claude/skills/auditing-repos

ln -s "$PWD/skills/local-board-skill" ~/.agents/skills/local-board-skill
ln -s ../../.agents/skills/local-board-skill ~/.claude/skills/local-board-skill
```

`~/.agents/skills/` lo leen Codex, Copilot CLI, GitHub Copilot en VS Code, Cursor y Gemini CLI. Para Claude Code además hace falta el enlace en `~/.claude/skills/`.

## Comandos

| Comando | Fase | Para qué |
| --- | --- | --- |
| [`query-from-cli`](commands/query-from-cli/) | 🚧 Beta | Preguntarle algo rápido a un modelo de IA desde la terminal (`q "..."`), sin abrir una sesión interactiva |

A diferencia de las skills, un comando es un script suelto: no se enlaza a `~/.agents/skills/`, se agrega al `PATH` o se aliasea. Cada uno tiene su `README.md` con el detalle de instalación.

## Harness

Los repos del Harness (skills, CLIs y MCPs del flujo Product Brain + Spec-Kit + Jira) viven en su propio repositorio y acá se asocian como submódulos de git bajo [`harness/`](harness/). Cada submódulo queda fijado a un commit concreto: actualizarlo es una decisión explícita, no algo que cambia solo.

| Repo | Fase | Para qué |
| --- | --- | --- |
| [`WayOfWork`](https://github.com/josefigueredo/wow) | 🧪 Incubation | Skills atómicas y el CLI `wow` para trabajar con Product Brain, Spec-Kit y modelos fuertes sin perder la telemetría de Spec-Kit |
| [`arq-review`](https://github.com/josefigueredo/arch-review) | 🧪 Incubation | Revisión de Arquitectura de pedidos `PRY-AAAA-NNNN`: skills `arq-manager` y `arq-architect` |
| [`product-brain-mcp`](https://github.com/josefigueredo/product-brain-skill-mcp) | 🧪 Incubation | MCP local `pbmcp` y skill `product-brain` para armar iniciativas, PRD, RFC y épicas y exportarlas a Jira |
| [`run-in-cursor`](https://github.com/josefigueredo/run-in-cursor) | 🚧 Beta | Mandarle un prompt o slash command al agente de Cursor desde otro agente, registrado como uso real de Cursor |
| [`jira-team-kit`](https://github.com/josefigueredo/jira-team-kit) | 🚧 Beta | Skill `jira-team-kit`: crea una épica de Jira y la mantiene espejada como kanban local |

Los repos son privados (`josefigueredo`), así que hace falta acceso por SSH. Para traerlos al clonar:

```bash
git clone --recurse-submodules git@github.com:josefigueredo/teamwayofwork.git
# o, en un clone existente:
git submodule update --init --recursive
```

Para llevar un submódulo a lo último de su `main`: `git submodule update --remote harness/<nombre>`, y commitear el nuevo puntero.

## Principios que atraviesan todo lo que hay acá

**Lo que no se ejecuta, no se afirma.** Un hallazgo sin verificar es una suposición con cita. Vale para una auditoría, para un comentario en un PR y para una línea de documentación.

**Un chequeo que pasa en silencio cuando no pudo correr es peor que no tener chequeo.** Si un guardrail no puede evaluar, tiene que gritar, no aprobar. Un tilde verde que no distingue *verifiqué* de *no pude verificar* hace que la gente deje de mirar.

**Un guardrail probado sólo en la dirección de éxito no está probado.** Hacelo fallar a propósito antes de confiar en él.

**Un comentario que miente es peor que ningún comentario.** El siguiente que lo lea le va a creer y va a saltear la verificación.
