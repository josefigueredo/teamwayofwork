# install-unified-ci

> 🧪 **Fase: Incubation.** Esta skill vive canónicamente en [`core-architecture-gh-workflows`](https://github.com/josefigueredo/core-architecture-gh-workflows/tree/main/skills/install-unified-ci). Usala y reportá lo que encuentres; todavía no construyas encima. Ver el [ciclo de vida](../../../README.md#ciclo-de-vida).

Evalúa un repositorio, audita su compatibilidad con los workflows de Unified CI (UCI), genera el `.github/workflows/ci.yml` canónico adecuado a su stack tecnológico y elimina workflows de CI obsoletos.

## El principio

**Cero boilerplate, cero roturas.**

Si un repositorio tiene requerimientos incompatibles (deploys directos a la nube como AWS ECS/Lambda o GCP, matrices multi-OS o migraciones de base de datos directas en el runner), la skill frena y reporta los gaps con exactitud en vez de romper la integración continua del equipo.

**La verdad vive con los workflows:** La especificación de los entrypoints, parámetros, flags y comandos internos vive directamente en el repositorio `core-architecture-gh-workflows`. Mantener la skill alojada allí garantiza que cualquier evolución de los workflows se refleje de manera atómica en la skill sin desincronizaciones.

## Cuándo usarla

- Al incorporar un nuevo servicio o API para despliegue en Platform
- Al estandarizar repositorios legados que usan workflows custom de test, build, lint o Sonar
- Al auditar si un repositorio existente puede migrar al CI unificado sin fricción
- Frases típicas:
  > _"adoptá el CI unificado acá"_ · _"migrá este repo a unified CI"_ · _"revisá si este repo puede usar el CI unificado"_ · _"reemplazá los workflows viejos por el CI unificado"_

**Cuándo NO:**
- Repositorios con deploys directos a AWS ECS/Lambda, GCP Cloud Run o Kubernetes que no utilicen Platform
- Proyectos en lenguajes fuera del catálogo unificado (Rust, C++, Ruby, PHP)
- Repositorios con matrices de testing obligatorias en macOS o Windows

## Instalación

La skill vive en el repositorio `core-architecture-gh-workflows`. Podés instalarla en tu entorno de dos formas:

### Opción 1: Mediante el script instalador (Recomendado)

Ejecutá el script de instalación incluido en este repositorio:

```bash
./skills/install-unified-ci/scripts/install.sh
```

El script descarga siempre la versión canónica de la skill directamente desde la rama `main` de `core-architecture-gh-workflows` en GitHub (vía sparse-checkout en `~/.cache/`) y crea los symlinks correspondientes.

### Opción 2: Enlace manual

Si ya tenés clonado `core-architecture-gh-workflows` en tu máquina:

```bash
# Para Codex, Copilot CLI, Gemini CLI y Open Multi-Agent Platform (OMP):
ln -s "/ruta/a/core-architecture-gh-workflows/skills/install-unified-ci" ~/.agents/skills/install-unified-ci

# Para Claude Code:
mkdir -p ~/.claude/skills
ln -s ../../.agents/skills/install-unified-ci ~/.claude/skills/install-unified-ci
```

Verificá que quedó instalada:

```bash
ls -l ~/.agents/skills/install-unified-ci/SKILL.md
```

## Cómo se invoca

Una vez instalada, no hace falta invocarla manualmente con comandos complejos. Se activa sola cuando pedís migrar o evaluar el CI de un repositorio:

> _"adoptá el CI unificado"_ · _"migrá este proyecto a Unified CI"_ · _"revisá si podemos usar Unified CI acá"_

Si querés forzarla explícitamente:

```
/install-unified-ci
```

## Arquitectura de la skill

La skill implementa el estándar de *progressive disclosure* de Agent Skills:
- `SKILL.md`: Guía procedimental ágil de 5 pasos para evaluación, auditoría, generación, poda y reporte.
- `references/migration-rules.md`: Reglas universales de decisión, matrices de incompatibilidad y políticas de preservación y poda de workflows.
- `references/stacks/<stack>.md`: Módulos específicos por runtime con catálogos de parámetros, comandos de ciclo de vida y plantillas YAML canónicas (`ci.yml` y `publish.yml`).

## Stacks soportados

La skill cuenta con catálogos precomputados para los siguientes runtimes en `references/stacks/`:
- **Node.js** (`references/stacks/node.md`): npm, yarn (v1 y v2+), pnpm, soporte de paquetes privados en GitHub Packages.
- **Go** (`references/stacks/go.md`): detección de Dockerfile propio o plantillas UCI, soporte para `GOPRIVATE`, parámetros en mayúsculas.
- **Maven** (`references/stacks/maven.md`): Java con baseline JDK 21, soporte de Testcontainers, publicación a GitHub Packages.
- **Gradle** (`references/stacks/gradle.md`): Java & Kotlin con `gradlew`, plugin de SonarCloud y publicación de paquetes.
- **Python** (`references/stacks/python.md`): uv, poetry, pipenv, pip, ruff, mypy, pytest con tolerancia a código de salida 5 (`NO_TESTS_COLLECTED`).
- **Docker** (`references/stacks/docker.md`): contenedores puros sin buildpacks de lenguaje.
- **Flutter** (`references/stacks/flutter.md`): Dart format, Flutter analyze, Flutter test con Melos o standalone, integración con Mobile Build Hub.
- **Kong** (`references/stacks/kong.md`): validación y despliegue de configuración declarativa del gateway desde `./conf/**/*.yml`.
- **Package Publishing**: publicación de librerías en GitHub Packages con validación SemVer (Node, Maven, Gradle).
