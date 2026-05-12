# Agent Master Prompt

You are implementing a private investment-analysis MVP. Follow the project documentation exactly and develop the system phase by phase.

## Technology stack

- Python 3.11+
- Supabase/Postgres
- GitHub Actions
- Cloudflare Pages
- Email and Telegram alerts

## Non-negotiable rules

1. Implement only the requested phase.
2. Do not skip tests.
3. Do not commit secrets.
4. Do not expose service-role keys in frontend.
5. Store raw provider payloads before normalising.
6. Keep all outputs auditable and explainable.
7. Treat model output as research, not advice.
8. Use typed Python and small modules.
9. Handle missing data gracefully.
10. Update documentation when architecture or schema changes.

## Development loop

For each phase:

1. Read the phase document.
2. List implementation tasks.
3. Modify files.
4. Add tests.
5. Run tests.
6. Provide a concise summary of changes.
7. State any limitations or assumptions.

## Done definition

A phase is complete only when:

- code is implemented;
- tests pass;
- acceptance criteria are met;
- no unrelated phases were implemented;
- no secrets are present;
- documentation is updated if required.
