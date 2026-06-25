---
name: atls
description: |
  ALL Atlassian work — Jira, Confluence, Bitbucket, Zephyr on Server/DC
  (지라/컨플루언스/비트버킷/지파이어). Load BEFORE the first atls command.

  Without this body, you WILL guess atls conventions wrong:
  JQL/CQL is positional, use --format=json not -f json, exit 5=stale.

  TRIGGER: Jira, Confluence, Bitbucket, Zephyr, atls, JQL, CQL, PROJ-123,
  지라, 컨플루언스, 비트버킷, 아틀라시안.
---

# atls

<!-- installed-by: atls 0.2.8 -->

## Upgrade
On missing command/flag or CHANGELOG-fixed behavior, run `atls version --check`; exit 1 → suggest `atls upgrade`.

## Command tree
```
atls
├── jira
│   ├── issue        get, search, create, update, delete, transition(s), dates, sla, images
│   ├── issue-batch  create
│   ├── epic         link
│   ├── comment      list, add, edit, delete
│   ├── sprint       list, issues, create, update, add-issues
│   ├── board        list, issues
│   ├── field        search, options
│   ├── link         list-types, create, remote-list, remote-create, delete
│   ├── worklog      list, add
│   ├── watcher      list, add, remove
│   ├── attachment   list, upload, download, delete
│   ├── dev-info     get, get-many
│   ├── service-desk list, queues, queue-issues
│   ├── project      list, issues, versions, components, versions-create
│   └── user         get, me
└── confluence
    ├── page         get, search, children, history, diff, images, create, update, delete, move, push-md, pull-md, diff-local
    ├── space        tree
    ├── comment      list, add, reply
    ├── label        list, add
    ├── attachment   list, upload, upload-batch, download, download-all, delete
    └── user         search, me
├── bitbucket
│   ├── project      list
│   ├── repo         list, get
│   ├── pr           list, get, diff, comments, commits, activity, create, update, merge, approve, statuses
│   ├── branch       list
│   ├── file         get
│   ├── comment      add, reply, update, delete, resolve, reopen
│   └── task         list, get, create, update, delete
└── zephyr
    ├── testcase     get, search, create, update, delete, latest-result, steps, add-step, add-steps
    ├── testresult   create
    ├── testplan     get, search, create
    ├── testrun      get, search, create, results, create-result, update-result, bulk-results
    ├── environment  list, create
    └── issuelink    testcases
```

## Format
compact=default scan, json=parse, md=read text, raw=byte-exact.

## Format placement
- Use `--format=...`; never `-f json` (`-f` may mean file input).

## page update vs push-md
`page update`=low-level body replace. `push-md`=markdown-native with attachments; prefer for md workflows.

## Common patterns
```bash
# Jira
atls jira issue get KEY
atls jira issue search "project=PROJ"
atls jira issue create --project PROJ --type Story --summary "..." --body-file=-
atls jira issue update KEY --body-file=- --body-format=md --heading-promotion=jira
atls jira comment add KEY --body-file=- --body-format=md

atls jira issue transitions KEY --format=json
atls jira issue transition KEY --transition-id 31
atls jira issue transition KEY --transition-name "In Progress"

# Confluence
atls confluence page get ID
atls confluence page search "CQL query"
atls confluence page push-md ID --md-file page.md --if-version 15
atls confluence page push-md ID --md-file page.md --asset-dir=assets/
atls confluence page pull-md ID --output page.md --resolve-assets=sidecar --asset-dir=assets/
atls confluence page diff-local ID page.md --passthrough-prefix workflow:

# Zephyr Scale
atls zephyr testcase get KEY
atls zephyr testcase search --query 'projectKey = "PROJ"' --max-results=20
atls zephyr testresult create --data-json '{"testCaseKey":"PROJ-T1","status":"Pass"}' --dry-run
```

## Write safety
- Always use `--dry-run` before write operations
- Use `--if-version N` for Confluence updates & push-md
- Use `--if-updated ISO` for Jira updates (stale check → exit 5)
- Use `--attachment-if-exists skip|replace` to control duplicate attachments (push-md)

## Key flags
| Flag | Commands | Effect |
|---|---|---|
| `--if-version N` | push-md, page update | Optimistic lock (exit 5 if stale) |
| `--asset-dir DIR` | push-md, pull-md | Batch attach / download assets |
| `--output -o PATH` | pull-md | Write markdown to file instead of stdout |
| `--resolve-assets=sidecar` | pull-md | Download attachments, rewrite image links |
| `--passthrough-prefix P` | push-md, pull-md, diff-local, issue update | Preserve `<!-- P:... -->` comments |
| `--md-file -` | push-md | Read markdown from stdin |
| `--body-repr md\|raw\|wiki` | issue get | Control body representation (separate from `--format`) |
| `--body-format md` / `--comment-format md` | jira/confluence writes | md → server format |
| `--heading-promotion jira` | issue update, issue get, issue search | Heading level adjust for md↔wiki |
| `--section "H2 Title"` | issue get, issue search | Extract specific H2 section from body |

## Exit codes
0=OK, 2=not found, 3=permission, 4=conflict (`--if-version`), 5=stale (re-fetch), 6=auth, 7=validation, 10=network, 11=rate-limited

## Jira wiki flags (--format=md)
```bash
atls jira issue get KEY --format=md --section "Acceptance Criteria"
atls jira issue get KEY --format=md --drop-leading-notice "Auto-generated"
```

## JSON output parsing
```bash
atls confluence page push-md ID --md-file p.md --format=json  # push-md uses -f for --md-file
atls confluence page pull-md ID --format=json                  # → {"markdown":"...","version":15,"title":"..."}
atls jira issue get KEY --format=json | jq '{key, summary}'
atls jira issue search "project=PROJ" --format=json | jq '.[].key'
atls jira issue get KEY --fields=summary,customfield_10100 --format=json | jq '.customfield_10100'
```

## Custom fields
- Explicitly requested Jira `customfield_*` values are preserved in JSON issue output.
- `jira issue update --set-customfield customfield_XXXXX=value` performs a read-back verification; if Jira silently ignores the update, the CLI exits with a validation error.
- Use `--fields-json` instead of `--set-customfield` when the Jira field expects a structured payload.

## Multi-profile setup
```bash
# Use non-default profile
atls --profile corp jira issue get CORP-1

# Env vars
export ATLS_CORP_JIRA_TOKEN="pat-token-here"
export ATLS_CORP_CONFLUENCE_TOKEN="pat-token-here"
```
