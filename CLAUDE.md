@AGENTS.md

## Git workflow

- Never push directly to `master`. All changes go to a feature branch first.
- Open a PR for every change — do not merge without user review.
- Branch naming: `feat/description`, `fix/description`, `chore/description`.
- Always confirm with the user before pushing or creating a PR.

## Security — absolute rules

- Never commit, push, or include in any file: API keys, passwords, tokens, secrets, or any credentials.
- `.env.local` and any `.env*` files must never be staged or committed — they are gitignored.
- If a secret is spotted in staged files, stop immediately and alert the user before doing anything else.
- Never log, print, or expose secrets in code, comments, or console output.
- All third-party API calls (Google, Upstash, etc.) go through server-side route handlers only — never in client-side code.
