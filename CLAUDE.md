# TapRep

Low-friction workout logger. Project plan, phases and issues live in Linear (project "TapRep", P-DAI-1, team DAI).

## Workflow rules
- Never run `git commit`, `git push` or `git merge` unless the user explicitly says to in that message. Permission to commit, push or merge once does not carry over to later changes.
- The user reviews all generated code and tests it manually as the acceptance gate. After making changes, stop and summarise what changed and how to test it; don't declare work done or move on to the next task.
- Small commits: one commit per reviewed step of an issue, not one per issue (still only when told to commit).
- Acceptance of a step with no working UI yet is provisional. When a later UI step shows earlier code is wrong, change it and say so plainly; don't work around it.
- If a change would break an acceptance criterion or a recorded rule, stop and raise it before doing it. Don't do it and justify it afterwards.

## Issues and Linear
- Linear is the source of truth. Before starting an issue, read it and the project overview. Record new decisions there: high level in the overview, full detail in the issue. Keep related issues consistent.
- The project overview holds the current state only. When a decision changes, rewrite the overview text rather than annotating it; the history and reasoning go in issue comments.
- Single source of truth: keep one copy of any record and link to it instead of copying. Moving something means removing it from the old place. Put issue detail in the issue description, not an attached document, unless asked. (The Linear MCP can't delete documents, so empty one into a pointer and ask the user to delete it.)
- Before starting an issue, break it into sub-issues and record that breakdown in the Linear issue itself, so progress lives in the tracker rather than in chat.
- Each issue gets a size estimate. Split large issues before work starts.
- After each issue: the user does a code review, and we do a short meta-analysis of how the issue went, so course corrections don't wait for the end of a phase.

## Scope
- Stay on the current task. Detail that belongs to a later step or issue gets at most a one-line note to record in Linear, not a debate, unless it blocks the decision being made now.
- When a problem found mid-branch needs a feature-sized fix, recommend the proper fix honestly, offer a small stopgap for the current branch, and offer to file the proper fix as its own issue.

## Design
- The user makes the visual and UX calls. Show the real result (screenshots, mockups) and give options with a recommendation. Don't make unflagged aesthetic decisions or bring in design-opinion tools or skills unless asked.
- Debate, don't agree by default. Lead with the strongest objection, defend a recommendation while you still think it's right, and concede plainly when convinced. Cost or effort is no argument against a better colour or UX choice.
- Past decisions, including the colour palette, are open to change. When one gets in the way of a new need, propose changing it instead of designing around it.

## Testing
- Tests are thorough and run every time. Never argue for fewer, weaker or opt-in tests because of runtime.
- No iPhone is available: phones are tested by hand on Android Chrome only, and iOS Safari only through Playwright WebKit. Flag iOS-specific risks, but don't hold up acceptance on untested Safari behaviour; Safari support isn't a current concern.

## Security
- No local-only switches in code or env that loosen security (e.g. turning off Secure cookies for dev). Meet dev needs from outside the code instead: a different run command, a self-signed cert kept outside the repo (phone testing uses uvicorn with `--ssl-keyfile/--ssl-certfile` on port 8443, certs in `~/.local/share/taprep-dev/`), or test fixtures.
