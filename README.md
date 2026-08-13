# teamwayofwork

Cómo trabaja el equipo de team: procedimientos, convenciones y las herramientas que los hacen cumplibles.

## `skills/`

Skills de agente compartidas por el equipo. Cada una es un procedimiento ejecutable, no un documento de buenas intenciones: lleva sus propios scripts y sus propios tests.

| Skill | Para qué |
| --- | --- |
| [`auditing-repos`](skills/auditing-repos/) | Auditar un repositorio y convertir los hallazgos en issues, PRs y tickets de Jira, con una compuerta de aprobación antes de publicar nada |

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

**Un chequeo que pasa en silencio cuando no pudo correr es peor que no tener chequeo.** Si un guardrail no puede evaluar, tiene que gritar, no aprobar.

**Un guardrail probado sólo en la dirección de éxito no está probado.** Hacelo fallar a propósito antes de confiar en él.

**Un comentario que miente es peor que ningún comentario.** El siguiente que lo lea le va a creer y va a saltear la verificación.
