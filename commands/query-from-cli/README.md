# query-from-cli

> 🚧 **Fase: Beta.** Se usa de verdad para consultas rápidas del día a día, pero el prompt y las opciones todavía se ajustan con el uso. Apoyate y avisá si algo rompe. Ver el [ciclo de vida](../../README.md#ciclo-de-vida).

Un `q` para hacerle una pregunta rápida a un modelo de IA sin abrir una sesión interactiva ni gastar contexto de un agente. Corre el CLI que elijas (`claude`, `codex`, `copilot` o `gemini`) en modo liviano —sin MCPs, plugins ni skills— y devuelve solo la respuesta, en texto plano listo para leer en la terminal.

## Cuándo usarlo

- Preguntas puntuales de una sola línea: un comando de `git`, una regex, un flag que no te acordás
- Cuando no querés arrastrar el contexto de la sesión de agente que tenés abierta
- Scripting: el output es texto plano, sin markdown, pensado para parsearse o pegarse directo

**Cuándo NO:** para tareas que necesitan editar archivos, correr comandos, o mantener contexto entre turnos, usá el agente normal — esto es de una sola pasada (`-p`), sin forma de responderle.

## Instalación

Es un script suelto, no una skill: no se enlaza a `~/.agents/skills/`, se agrega al `PATH` o se aliasea.

```bash
git clone git@github.com:josefigueredo/teamwayofwork.git
cd teamwayofwork

# opción A: alias en tu shell
echo 'alias q="$PWD/commands/query-from-cli/query.sh"' >> ~/.zshrc

# opción B: symlink a un directorio que ya esté en tu PATH
ln -s "$PWD/commands/query-from-cli/query.sh" ~/.local/bin/q
```

Verificá que quedó:

```bash
q "decime hola"
```

## Uso

```
q [--model=claude|codex|copilot|gemini] <prompt>
```

Sin `--model`, usa `copilot`.

```bash
q "command to rank folders by last modified recursively"
q --model=gemini "how to find large files on macOS"
q --model=codex "regex to match IPv6 addresses"
q --model=copilot "git command to squash last 3 commits"
```

La respuesta llega en el mismo idioma de tu pregunta, sin `**`, `#` ni backticks de markdown — si el modelo arma una tabla, la alinea a mano con espacios para que se lea bien en una terminal monoespaciada.

Como es de una sola pasada, si tu pregunta es muy ambigua el modelo no se queda esperando una aclaración: responde con su mejor interpretación y, si de verdad le falta contexto, termina con una línea del estilo *"volvé a correr el prompt agregando el detalle que falta"*.

## Requisitos

| | Sin esto |
|---|---|
| El CLI del modelo elegido (`claude`, `codex`, `copilot` o `gemini`) instalado y autenticado | Ese `--model` no corre |
| `jq` | `--model=codex` no puede extraer la respuesta del JSON que devuelve |

`copilot` es el standalone de `@github/copilot` (npm, Homebrew o el script de instalación) — no depende de la extensión de `gh`.

## Estructura

```
query-from-cli/
├── query.sh    # el script (lo corrés vos, o lo aliaseás a `q`)
└── README.md   # este archivo
```
