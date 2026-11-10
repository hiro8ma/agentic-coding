# Sample project

## Commits

- Do not commit secrets. The `secret-guard` hook stops the commit
  - **Why:** 2025-03-04 a key was pushed. 2025-05-06 it happened again
- Keep commit messages under 72 characters
  - **Why:** 2025-04-01 a long subject was cut in the log. 2025-06-02 again

## Lint

Run ruff before you push

- Format the files with a hook before review

## Merge

- `gh pr merge` needs the user's approval every time
