---
name: local-board-skill
user-invocable: true
description: "Use when bootstrapping a local work board, analyzing commits since its last sync, relating specs and tickets, reconciling historical Git evidence, or preparing and applying an approved Jira sync."
---

# Local Board Traceability

This skill is portable. It does not encode a project's board name, ticket prefix, Jira project, labels, repository names, dates or product taxonomy. Those belong to the selected board instance and its primary `Board.md` index profile.

Reusable deterministic utilities live in `local-board-skill/scripts/`. The scripts collect, validate, generate and synchronize facts. This skill owns interpretation of diffs, domain grouping and approval boundaries.

## Board Contract

A board instance must contain:

- A primary `Board.md` with frontmatter fields: `board_name`, `entity_glob`, `entity_id_prefix`, `sync_dir`, `relations_file`, `jira_project_key`, `jira_label`, `remote_link_namespace`.
- A relationship graph under `<sync_dir>`, named by `relations_file`, as the only structured source of relationships.
- A sync-state file at `<sync_dir>/state.json` with `last_run` or an equivalent last-applied timestamp.
- Entity Markdown files matched by `entity_glob`, with the project's own frontmatter contract.
- A `_meta/` directory for Markdown documentation maintained by people and the skill: `convenciones.md`, `autores.md`, `inventario-commits.md`, `mapeo-capacidades.md`, and `spec-ticket-traceability.md`.

`_meta/` never holds executable tools or structured sync state. Reusable code belongs in `local-board-skill/scripts/`; all board `.json`, `.csv`, and `.txt` artifacts belong in `<sync_dir>`. For a new board, `init_board.py` creates the complete initial `_meta` Markdown workspace and sync data directory. Define the project-specific entity hierarchy, naming and scope in the board contract; this skill does not require a board README.

For Jira synchronization, each instance declares `<sync_dir>/jira-config.json`. It contains its remote issue type names, local-to-remote status map, parent strategy, and author aliases. This data is instance-owned and must not be hardcoded in skill scripts:

```json
{
	"type_map": {"epic": "Remote Epic"},
	"status_map": {"To Do": "Open"},
	"parent_strategy": {"epic": "none", "story": "parent"},
	"aliases": {"owner": "remote-account-id"}
}
```

`parent_strategy` accepts `none`, `parent`, or `ancestor:<entity-type>`.

## Mode A: Bootstrap From Zero

1. Read the repository-level instructions and the board conventions.
2. Run `init_board.py`; it creates the primary index profile, sync directory, relation/state JSON assets, `.gitignore`, local `.env`, and `_meta` Markdown templates. Then define the project's entity structure and author mapping.
3. Inventory relevant repositories from the agreed historical start date with `inventory_git.py`, then generate `_meta/inventario-commits.md` with `render_git_inventory.py`.
4. Read each relevant diff and its affected-file context. Classify product outcome, author, specs/plans, PRs/tags and dependencies.
5. Design epics, stories, tasks and subtasks as functional groupings. Do not create one entity per commit, file or implementation task.
6. Create entity files, record structural links, and add each relevant commit to every supported `evidence_for` asset relation. Add an explicit exclusion for out-of-scope commits.
7. Refresh the asset/spec catalog, validate the graph, generate readable reports, generate a persisted Jira plan and request approval before any write.

## Create Hierarchy Assets

`create_asset.py` creates the conventional epic, story, task, and sub-task
directory hierarchy together with structured Markdown frontmatter. It derives
the identifier prefix from the instance profile, validates the parent type, and
updates the parent `children` list.

```bash
python3 local-board-skill/scripts/create_asset.py \
	--board-dir <board-dir> \
	--type epic \
	--summary "Platform capability"

python3 local-board-skill/scripts/create_asset.py \
	--board-dir <board-dir> \
	--type story \
	--parent <epic-id> \
	--summary "As an operator, I manage platform data"

python3 local-board-skill/scripts/create_asset.py \
	--board-dir <board-dir> \
	--type task \
	--parent <story-id> \
	--summary "Deliver data management" \
	--repo <repository> \
	--spec-ref <spec-id>

python3 local-board-skill/scripts/create_asset.py \
	--board-dir <board-dir> \
	--type sub-task \
	--parent <task-id> \
	--summary "Release the data management change"
```

Use `--slug` to override the directory name. The metadata options can be
repeated: `--spec-ref`, `--plan-ref`, `--repo`, `--release`, `--commit`, `--pr`,
and `--tag`.

## Mode B: Analyze Since Last Sync

1. Read `<sync_dir>/state.json` and resolve `last_run` or the board's documented last-applied timestamp. Do not guess the cutoff.
2. Run `inventory_git.py --since <cutoff>` against the workspace and save output under the instance sync directory.
3. Read every candidate diff, not only subjects. Compare it against existing asset evidence and specs.
4. Reuse the asset that represents the same functional capability. Create a new entity only when the new outcome cannot be accurately represented by an existing one.
5. Add new nodes and relations to `relations.json`, then update entity frontmatter from accepted relations.
6. Refresh catalog, validate, generate reports and save a dry-run plan. Present the exact action set for approval.
7. Apply only the approved unchanged plan. Re-run analysis if the graph, local entities or Jira baseline changes.

## Mode C: Historical Reconciliation

Use this mode when existing Jira assets do not have all known Git evidence linked remotely.

1. Inventory the agreed historical period.
2. Read existing entity evidence and Jira keys.
3. Associate each historical commit or PR with one existing asset after diff-based review; record a reason for exclusions.
4. Add or repair graph relations, then save a plan that contains only the missing remote links and valid metadata changes.
5. Apply after approval and verify idempotency by running a new dry-run.

## Graph Rules

- Each commit node uses a full hash and has one or more `evidence_for` asset relations, or one `excluded_with_reason` exception.
- Specs and commits may relate to multiple assets when their evidence supports each relationship.
- URLs for commits and PRs are derived only from verified Git remotes. Never invent them.
- Use `confidence` and `decision` for ambiguity. Stop for user direction when a material grouping cannot be supported by evidence.
- Scripts must reject dangling nodes and missing evidence resolutions before reaching Jira.

## Commands

Run from the workspace root, replacing `<board-dir>` with the instance directory:

```bash
python3 skills/local-board-skill/scripts/inventory_git.py --board-dir <board-dir> --since '<cutoff>'
python3 skills/local-board-skill/scripts/render_git_inventory.py --board-dir <board-dir>
python3 skills/local-board-skill/scripts/refresh_relations_catalog.py --board-dir <board-dir> --workspace . --output <board-dir>/sync/relations.json
python3 skills/local-board-skill/scripts/validate_relations.py --board-dir <board-dir>
python3 skills/local-board-skill/scripts/generate_traceability.py --board-dir <board-dir>
skills/local-board-skill/scripts/sync.sh <board-dir> --save-plan <board-dir>/sync/.review-plan.json
skills/local-board-skill/scripts/sync.sh <board-dir> --apply-plan <board-dir>/sync/.review-plan.json
```

### Jira sync performance

Entity creates/updates run sequentially in hierarchy order (epic → story → task → sub-task) so parents exist before children. A create persists its `jira_key`, `jira_sync` state, labels and sync-state record immediately before the next dependent action. The child then resolves `parent` or `ancestor:<type>` from that persisted in-memory/local mapping; an unresolved parent fails explicitly and stops the apply. `link_remote` actions run in parallel grouped by Jira issue key — each issue is processed in one worker thread with its own client.

```bash
# Fix commit URLs (strips .git suffix from remote paths)
python3 skills/local-board-skill/scripts/enrich_commit_urls.py \
  --board-dir <board-dir> --inventory <board-dir>/sync/git-inventory.json

# Purge stale remote links with malformed .git/commit URLs (parallel per issue)
python3 skills/local-board-skill/scripts/purge_bad_remote_links.py \
  --board-dir <board-dir> --workers 12

# Apply with parallel link_remote (default 12 workers, throttle 0.3s)
JIRA_WRITE_THROTTLE=0.3 JIRA_SYNC_WORKERS=12 \
  skills/local-board-skill/scripts/sync.sh <board-dir> --apply-plan <board-dir>/sync/.review-plan.json
```

`--workers` on `sync_board.py` overrides `JIRA_SYNC_WORKERS` (default 12).

`inventory_git.py` writes the machine-readable source to `<board-dir>/sync/git-inventory.json`. `render_git_inventory.py` is the only process that refreshes `_meta/inventario-commits.md`; it is a derived human-readable report.

`--save-plan` is read-only for Jira and records hierarchy create actions with deferred parent resolution, so a wholly new epic → story → task → sub-task hierarchy is a valid plan. Before planning a `create` for an asset without `jira_key`, it searches the configured Jira project by the exact local marker (`[asset-id]`). It adopts exactly one candidate only when its project, configured Jira type, full marked summary and board label all match. The persisted `adopt_jira` action includes the Jira key and the matching evidence; zero candidates produces `create`, while ambiguous or contradictory candidates fail explicitly. This also recovers an interruption after remote creation but before local key persistence without duplicating the issue.

`--apply-plan` verifies the checksum and the complete approved action set, then revalidates every `adopt_jira` identity before atomically persisting its local key, labels and sync state. A changed candidate stops the run and requires plan regeneration; it is never replaced by a `create`. It then resolves each hierarchy parent at its deterministic layer immediately before creating its child. Local entity and state files are atomically replaced to avoid partial JSON or frontmatter writes. Regenerate the plan if the graph, identity evidence or evidence links change; after a successful apply, a new dry-run should contain only `noop` actions.

Do **not** use Jira MCP or direct Jira API calls as a synchronization fallback. New hierarchies must be created through `sync.sh` / `sync_board.py` using the persisted plan → approval → deterministic apply → dry-run verification workflow.

Board ticket bodies are the source for Jira descriptions. Before syncing, refine them using the board's existing language and conventions: include evidenced objective/context, functional and technical scope, responsibilities and relevant flows, dependencies and restrictions, verifiable acceptance criteria, validation, documentation and exit criteria. Integration or SDK work should also cover applicable functional parity, contracts, error behavior, configuration, observability, compatibility, security and test strategy. Do not invent requirements; mark assumptions or pending decisions explicitly.
