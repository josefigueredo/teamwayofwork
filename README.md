# teamwayofwork

La forma de trabajo del equipo **team**: los procedimientos con los que trabajamos, las convenciones que acordamos, y las **AI skills** que los vuelven ejecutables en vez de dejarlos en un documento que nadie abre.

Un procedimiento que vive sólo en una wiki se cumple cuando alguien se acuerda. Acá cada procedimiento viaja con sus scripts y sus tests, así que la parte mecánica la hace la máquina y las personas se ocupan de las decisiones.

## Ciclo de vida

Todo lo que hay en este repo —skills, procedimientos, convenciones— tiene una fase declarada. La fase responde una sola pregunta: **¿cuánto puedo apoyarme en esto hoy?**

| Fase | Qué significa | Qué esperar |
| --- | --- | --- |
| 🧪 **Incubation** | Se está explorando. Puede cambiar de forma o morir. | Usalo y reportá; no construyas encima. Cambios sin aviso. |
| 🚧 **Alpha/Beta** | Se usa de verdad, todavía se ajusta con el uso. | Podés apoyarte, avisando que puede moverse. Cambios anunciados. |
| ✅ **Standardized** | Es **la** forma en que el equipo hace esto. | Es la opción por defecto. Apartarse se justifica, no al revés. |

Una fase no se gana por antigüedad sino por uso: algo pasa a `Standardized` cuando el equipo lo aplicó varias veces, en contextos distintos, y dejó de encontrarle sorpresas.

## Skills

| Skill | Fase | Para qué |
| --- | --- | --- |
| [`auditing-repos`](skills/auditing-repos/) | 🧪 Incubation | Auditar un repositorio y convertir los hallazgos en issues, PRs y tickets de Jira, con una compuerta de aprobación antes de publicar nada |

Cada skill tiene su `README.md` en castellano. El `SKILL.md` y los `references/` están en inglés a propósito: los consume el modelo.

### Instalación

Enlazá la skill donde tu runtime la busca, en vez de copiarla — así seguís una sola fuente de verdad y no una copia que se desactualiza:

```bash
ln -s "$PWD/skills/auditing-repos" ~/.agents/skills/auditing-repos
ln -s ../../.agents/skills/auditing-repos ~/.claude/skills/auditing-repos
```

`~/.agents/skills/` lo leen Claude Code, Codex, Copilot CLI y Gemini CLI.

## Principios que atraviesan todo lo que hay acá

**Lo que no se ejecuta, no se afirma.** Un hallazgo sin verificar es una suposición con cita. Vale para una auditoría, para un comentario en un PR y para una línea de documentación.

**Un chequeo que pasa en silencio cuando no pudo correr es peor que no tener chequeo.** Si un guardrail no puede evaluar, tiene que gritar, no aprobar. Un tilde verde que no distingue *verifiqué* de *no pude verificar* hace que la gente deje de mirar.

**Un guardrail probado sólo en la dirección de éxito no está probado.** Hacelo fallar a propósito antes de confiar en él.

**Un comentario que miente es peor que ningún comentario.** El siguiente que lo lea le va a creer y va a saltear la verificación.
