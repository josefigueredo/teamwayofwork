#!/usr/bin/env bash
# install.sh - Enlaza o instala la skill install-unified-ci en los runtimes del agente.
set -euo pipefail

REPO_URL="https://github.com/josefigueredo/core-architecture-gh-workflows.git"
BRANCH="main"
SKILL_SUBPATH="skills/install-unified-ci"
TARGET_DIR="${HOME}/.agents/skills/install-unified-ci"
CLAUDE_DIR="${HOME}/.claude/skills"
CACHE_DIR="${HOME}/.cache/core-architecture-gh-workflows"

echo "=== Instalador de skill: install-unified-ci ==="
echo "Obteniendo la skill desde ${REPO_URL} (${BRANCH})..."

mkdir -p "${CACHE_DIR}"
if [[ ! -d "${CACHE_DIR}/.git" ]]; then
  git clone --depth 1 --branch "${BRANCH}" --filter=blob:none --sparse "${REPO_URL}" "${CACHE_DIR}"
  git -C "${CACHE_DIR}" sparse-checkout set "${SKILL_SUBPATH}"
else
  git -C "${CACHE_DIR}" sparse-checkout set "${SKILL_SUBPATH}"
  git -C "${CACHE_DIR}" fetch --depth 1 origin "${BRANCH}"
  git -C "${CACHE_DIR}" reset --hard FETCH_HEAD
fi
SOURCE_DIR="${CACHE_DIR}/${SKILL_SUBPATH}"

# 4. Validar source antes de reemplazar enlaces
if [[ ! -f "${SOURCE_DIR}/SKILL.md" ]]; then
  echo "❌ Error: no se encontró un SKILL.md válido en ${SOURCE_DIR}." >&2
  exit 1
fi

# 5. Crear directorios y symlinks
mkdir -p "${HOME}/.agents/skills"
rm -rf "${TARGET_DIR}"
ln -sfn "${SOURCE_DIR}" "${TARGET_DIR}"
echo "✓ Enlazado a ~/.agents/skills/install-unified-ci -> ${SOURCE_DIR}"

# 5. Enlace para Claude Code
mkdir -p "${CLAUDE_DIR}"
rm -rf "${CLAUDE_DIR}/install-unified-ci"
ln -sfn "${TARGET_DIR}" "${CLAUDE_DIR}/install-unified-ci"
echo "✓ Enlazado a ~/.claude/skills/install-unified-ci"

# 6. Enlace para OMP si el directorio de skills existe
if [[ -d "${HOME}/.omp/skills" ]]; then
  rm -rf "${HOME}/.omp/skills/install-unified-ci"
  ln -sfn "${TARGET_DIR}" "${HOME}/.omp/skills/install-unified-ci"
  echo "✓ Enlazado a ~/.omp/skills/install-unified-ci"
fi

# 7. Verificación
if [[ -f "${TARGET_DIR}/SKILL.md" ]]; then
  echo ""
  echo "✅ Skill install-unified-ci instalada correctamente desde origin/${BRANCH}."
  echo "Probá ejecutar en tu agente: /install-unified-ci o 'revisá si este repo puede usar el CI unificado'."
else
  echo "❌ Error: no se encontró SKILL.md en ${TARGET_DIR}." >&2
  exit 1
fi
