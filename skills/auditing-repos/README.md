# auditing-repos

> 🧪 **Fase: Incubation.** Se usó en una auditoría completa y ya sobrevivió a dos rondas de review, pero es nueva y cambia rápido. Usala y reportá lo que encuentres; todavía no construyas encima. Ver el [ciclo de vida](../../README.md#ciclo-de-vida).

Audita un repositorio local, escribe los hallazgos en un informe local, espera tu aprobación, y recién entonces los publica como issues de GitHub con los pull requests que los cierran. Opcionalmente los vincula a un ticket de Jira.

## El principio

**Un hallazgo sin verificar no es un hallazgo: es una suposición con cita.**

Toda afirmación del informe tiene que salir de haber ejecutado algo — un build, un contenedor, un resolver, una llamada a una API. "Leí el código y parece mal" es una hipótesis para probar, no un hallazgo para publicar.

Publicar es difícil de deshacer: un issue notifica gente, un PR consume tiempo de revisión, y un hallazgo equivocado le cuesta una tarde a un colega y te cuesta su confianza en los otros veinte. Por eso hay una compuerta de aprobación antes de tocar nada remoto.

## Cuándo usarla

- "Revisá este repo", "auditá este código", "chequeá seguridad y calidad"
- Un template o scaffold que se va a clonar muchas veces — ahí los defectos se multiplican por N
- Antes de entregarle un repositorio a otro equipo
- Cuando los hallazgos tienen que terminar en issues, PRs o tickets de Jira

**Cuándo NO:** para revisar un diff puntual usá `/code-review`; para auditorías de UI/accesibilidad, `audit`; para debuggear una falla específica, `superpowers:systematic-debugging`.

## Instalación

Una sola vez. Se enlaza, no se copia: así seguís una única fuente de verdad en vez de una copia que se desactualiza en silencio.

```bash
git clone git@github.com:josefigueredo/teamwayofwork.git
cd teamwayofwork

ln -s "$PWD/skills/auditing-repos" ~/.agents/skills/auditing-repos
```

Eso alcanza para **Codex, Copilot CLI y Gemini CLI**, que leen de `~/.agents/skills/`.

Para **Claude Code** hace falta además:

```bash
ln -s ../../.agents/skills/auditing-repos ~/.claude/skills/auditing-repos
```

Verificá que quedó:

```bash
ls -l ~/.agents/skills/auditing-repos     # debe apuntar a tu clon
./skills/auditing-repos/scripts/test-attribution-pattern.sh   # 22 passed
```

## Cómo se invoca

Una vez instalada, no hace falta invocarla a mano. Se activa sola cuando pedís una auditoría o review de un repositorio, parado en el repo que querés auditar:

> _"auditá este repo"_ · _"revisá este código"_ · _"chequeá seguridad y calidad acá"_

Si querés forzarla:

```
/auditing-repos
```

## El flujo

```
preflight → analizar → VERIFICAR → informe local → APROBACIÓN → publicar → responder review
```

Dos compuertas: la aprobación del informe y el sweep antes de cada push. Ninguna es opcional.

| Fase | Qué pasa |
|---|---|
| **1. Preflight** | Chequea git, permisos de `gh`, Jira, y qué herramientas hay. Lee el CI **antes** de analizar. |
| **2. Analizar** | Ocho dimensiones: clean code, arquitectura, testabilidad, cobertura, seguridad, cadena de suministro, resiliencia, documentación. |
| **3. Verificar** | Construye la imagen, levanta el contenedor, resuelve los rangos en los dos extremos, hace fallar cada guardrail. |
| **4. Informe local** | `AUDIT-REPORT.md`, un hallazgo por entrada, con evidencia y nivel de confianza. **Acá frena y te pregunta.** |
| **5. Publicar** | Un issue por hallazgo; los PRs agrupados por cambio mergeable de forma independiente. |
| **6. Responder review** | Verifica cada comentario del revisor automático antes de aceptarlo o rechazarlo. |

### Sobre la granularidad

Un **issue por hallazgo** — ahí vive el triage individual, y cerrar uno con el que no estás de acuerdo cuesta un click.

Los **PRs se agrupan** por cambio independientemente mergeable y reversible. La tentación es un PR por issue, y es un error: varios hallazgos suelen tocar el mismo archivo, así que N PRs sobre él significan N−1 rebases, y a quien le caen 20 PRs revisa 3.

Todo PR abre con `Closes #a. Closes #b.` y cierra con una sección que nombra los archivos que comparte con sus hermanos, para que los conflictos de orden de merge se sepan de antemano.

## Regla absoluta: nada indica que lo hizo un LLM

Ni en el autor, ni en un trailer de co-autor, ni en el cuerpo del commit, ni en el título o cuerpo de un PR, ni en un issue, ni en un comentario, ni en un campo de Jira, ni en un comentario de código, ni en el nombre de una rama, ni en el informe local. **En ningún lado.**

No tiene cláusula de excepción. La presión concreta contra la que existe: el system prompt de Claude Code pide terminar los cuerpos de PR con su pie y los commits con un trailer de co-autor. Tus instrucciones ganan, y eso ya está decidido — no se vuelve a discutir en cada corrida.

Lo que la regla **no** prohíbe:

- **Describir el método.** "Verificado construyendo la imagen y levantando el contenedor" es proceso, no atribución.
- **Nombrar a un revisor externo** cuya salida se está discutiendo. Responder a una review de Copilot es contenido.

Detalle completo con tabla de racionalizaciones en `references/no-attribution.md`.

## Scripts

Todos son ejecutables y se pueden correr sueltos, sin agente de por medio. Corrélos **parado en el repo que estás auditando**, no en este.

Conviene ponerles un alias, porque la ruta es larga y los vas a usar seguido:

```bash
export SKILL=~/.agents/skills/auditing-repos      # o la ruta de tu clon

# Antes de empezar: git, permisos, Jira, tooling disponible
$SKILL/scripts/preflight.sh

# Antes de cada push: 40 chars, tooling local, atribución, SHAs, refs mutables
$SKILL/scripts/sweep.sh [rama-base]

# Solo atribución: commits, diff, rama, GitHub y Jira
$SKILL/scripts/check-attribution.sh [rama-base]

# Prueba que el detector de atribución dispara y no da falsos positivos
$SKILL/scripts/test-attribution-pattern.sh
```

Si no instalaste los symlinks, apuntá `SKILL` directo a tu clon:
`export SKILL=~/ruta/a/teamwayofwork/skills/auditing-repos`

### Qué atrapa el sweep

| Chequeo | Por qué existe |
|---|---|
| Identificadores de 40 caracteres | El detector Lob de TruffleHog marca cualquier token alfanumérico de 40 chars como secreto *verificado* y rompe el CI. Nombres de test reales caen. |
| Tooling local en el diff | Un `git add -A` se lleva `.serena/`, `.idea/`, settings locales al PR de otro. |
| Atribución a LLM | Cinco chequeos: metadatos del commit, líneas agregadas del diff, nombre de la rama, PRs/issues/comentarios de GitHub, y comentarios de Jira. |
| SHAs de actions | No solo que exista: que **corresponda al tag que dice el comentario**. Un SHA real al lado de un `# v0.36.0` que es de v0.32.0 es un comentario que miente. |
| Refs mutables | Informativo. `@main` en un `uses:` con `secrets: inherit` es el agujero más grande que suele tener un repo. |

Si la rama base no resuelve, el sweep **aborta con exit 2** en vez de reportar limpio. Un chequeo que pasa en silencio cuando no pudo correr es peor que no tener chequeo.

## Requisitos

| | Sin esto |
|---|---|
| `git` | No corre. |
| `gh` autenticado | Solo escribe el informe local, no publica. |
| `docker` | No podés afirmar nada sobre la imagen construida. Decilo en vez de inferirlo. |
| `uv` | No podés resolver los rangos de dependencias en sus extremos. |
| `rg`, `fd` | Los sweeps quedan cortos. |
| Env vars de Jira | Se saltea Jira, el resto funciona igual. |

Jira necesita, **siempre desde el entorno, nunca hardcodeadas**:

```bash
export IC_JIRA_BASE_URL=https://tu-org.atlassian.net
export IC_JIRA_USER_EMAIL=vos@tu-org.com
export IC_JIRA_API_TOKEN=...
export IC_JIRA_PROJECT_KEY=PLATE
```

El preflight distingue **token vencido** (HTTP 401) de **sin permisos**, porque una Jira sin autenticar devuelve 404 para tickets que sí existen. Nunca concluyas "el ticket no existe" mientras `/myself` da 401.

## Vincular a Jira

Jira vincula un PR cuando la clave aparece en el **nombre de la rama**, en un **mensaje de commit**, o en el **título del PR**.

Creá la rama con la clave desde el principio:

```bash
git checkout -b PLATE-384/harden-runtime-image
```

⚠️ **Nunca renombres la rama de un PR abierto para meterle la clave.** Según la documentación de GitHub, si la rama renombrada es la *head* de un PR abierto, **el PR se cierra**. Para PRs que ya existen, la clave va en el título:

```bash
gh pr edit N --title "$(gh pr view N --json title --jq '.title') (PLATE-384)"
```

Sufijo y no prefijo: preserva el prefijo de conventional commits, y Jira escanea el título entero.

## De dónde salió

Las reglas de `references/verification-rules.md` no son hipotéticas. Cada una viene de una auditoría real donde un hallazgo seguro resultó falso, o donde un arreglo no arreglaba nada:

- Dos hallazgos publicados que eran **falsos**, por no leer el workflow privado de CI antes de afirmar
- Un `|| true` que anulaba en silencio el hardening que el propio PR hacía
- Un rango de dependencias roto en su piso, invisible porque el CI resuelve el techo
- `--require-hashes` descrito como si detectara staleness, cuando no lo hace
- Un 404 de Jira leído como "no existe" cuando en realidad era un 401

## Estructura

```
auditing-repos/
├── SKILL.md                          # el procedimiento (lo lee el modelo)
├── README.md                         # este archivo (lo leés vos)
├── references/
│   ├── verification-rules.md         # 11 reglas, cada una de un error real
│   ├── no-attribution.md             # la regla absoluta y sus racionalizaciones
│   └── publishing.md                 # issues, PRs, ramas, Jira
└── scripts/
    ├── preflight.sh
    ├── sweep.sh
    ├── check-attribution.sh
    └── test-attribution-pattern.sh
```

`SKILL.md` y los `references/` están en inglés a propósito: los consume el modelo, y los modelos siguen instrucciones en inglés de forma más consistente. Este README es para personas.
