# Issue tracker: GitHub

Issues and specs live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --json number,title,body,labels,comments`
- List: `gh issue list --state open`
- Comment: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

Pull requests are not an incoming issue triage surface.

## Wayfinding

Use one GitHub issue as the map and child issues as decision tickets. Link blockers with GitHub issue dependencies when available; otherwise record `Blocked by: #<n>` in each child. Claim work with `gh issue edit <n> --add-assignee @me`. Resolve with a comment, close the issue, and add a context pointer to the map.
