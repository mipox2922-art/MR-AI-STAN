# MR AI STAN PostgreSQL backup and migration

## Why this must happen

The production database `mr-ai-stan-db` is a Render Free PostgreSQL 18 instance created on 12 October 2026. Render reports its expiry as **11 November 2026 at 18:49:56 UTC**.

Render Free PostgreSQL instances:
- expire 30 days after creation;
- become inaccessible after expiry unless upgraded;
- have a 14-day grace period after expiry before deletion;
- have **no automatic backups, snapshots, or point-in-time recovery** on the Free compute plan.

Sources:
- https://render.com/docs/free
- https://render.com/docs/postgresql-backups

The application is therefore at risk of losing access to its production data. This migration must be completed and verified before the expiry timestamp.

## What is prepared in this repository

`scripts/postgres-backup-migrate.sh` uses PostgreSQL 18 client tools to:

1. create a compressed custom-format `pg_dump`;
2. validate it with `pg_restore --list`;
3. create a SHA-256 checksum;
4. optionally restore to a **new, empty** target database;
5. compare every user table's row count between source and target.

The script does not print database URLs, does not commit credentials, does not modify the source, and refuses to restore into a target containing user tables. It deliberately does not use `--clean` or drop destination data.

## Choose a destination before running migration

Use an existing zero-cost PostgreSQL project only after checking both its database size quota and its compute/egress limits. Current published examples:

- Supabase Free: 500 MB database per project, 5 GB egress, and projects may pause after one week of inactivity. Free projects do not include automatic backups. The existing Supabase Nano project should only be used if its organization is on the Free plan (Nano in a paid organization can incur a charge) and the source dump is below the storage quota.
  https://supabase.com/docs/guides/platform/billing-on-supabase
  https://supabase.com/kb/faqs/platform/free-postgres-for-side-projects
- Neon Free: 1 GB storage per project, 100 CU-hours per project/month, 5 GB public network transfer, scale-to-zero after five minutes, and six hours of instant-restore history. MR AI's continuous scheduler may consume more than 100 CU-hours, so this is not automatically a suitable always-on destination.
  https://neon.com/docs/introduction/plans
  https://neon.com/docs/introduction/limits

Do not select a destination until the source database size is known. Neon can be unsuitable for an always-active database workload if its 100 CU-hour allowance is exceeded. Supabase Free can be unsuitable if the source database exceeds 500 MB. No paid plan is assumed by this runbook.

## Configure secrets safely

In GitHub, open **Settings → Secrets and variables → Actions → New repository secret** and add:

- `MR_AI_SOURCE_DATABASE_URL`: the Render database's **External** connection URL from its Connect page. It must use TLS (`sslmode=require`).
- `MR_AI_TARGET_DATABASE_URL`: the target provider's external PostgreSQL URL, also with TLS enabled.
- `MR_AI_BACKUP_ENCRYPTION_PASSPHRASE`: a unique random passphrase of at least 32 characters. Save it in a password manager. It encrypts the backup before any artifact is uploaded.
- `RENDER_API_KEY`: a Render API key with permission to read and update the source PostgreSQL instance's IP allowlist. Use a scoped key limited to this workspace/resource where Render supports it.

Never paste either connection URL, the Render API key, or the encryption passphrase into chat, source code, an issue, or a workflow input. The workflow consumes encrypted repository secrets and does not print them. The repository is public, so **only AES-256 encrypted backup files are uploaded**. The workflow decrypts the archive on the runner and byte-compares it before uploading the ciphertext.

The workflow obtains the GitHub runner's current public IPv4 address, temporarily adds only that address as a `/32` rule to the source database, and removes that exact rule in an unconditional cleanup step. Existing allowlist entries are preserved, including any concurrent administrator additions. It never opens `0.0.0.0/0`. If cleanup fails, the workflow fails visibly and the temporary rule must be removed manually in Render Dashboard.

## Run the backup first

1. Add the four secrets above in GitHub.
2. Open **Actions → PostgreSQL backup and migration**.
3. Choose `backup` and run the workflow.
4. Confirm the run succeeds and download the `mr-ai-stan-postgres-backup-encrypted` artifact.
5. Keep the encrypted `.gpg` file and checksum in private durable storage. GitHub workflow artifacts are retained for 90 days only.
6. Decrypt locally with the passphrase saved in your password manager. Example: `gpg --decrypt --output mr-ai-stan-backup.tar.gz mr-ai-stan-postgres-backup.tar.gz.gpg`. Then extract and verify the included dump checksum with `sha256sum -c mr-ai-stan-postgres.dump.sha256`.

## Restore and verify

After creating an empty destination database and setting `MR_AI_TARGET_DATABASE_URL`:

1. Run the same workflow with mode `migrate`.
2. Confirm the run reports matching source/target row counts for every user table.
3. Download and retain the encrypted backup artifact. Keep the passphrase separate from the dump file.
4. Only after verification, change the Render backend service's `DATABASE_URL` to the target provider's URL.
5. Confirm `https://mr-ai-stan.onrender.com/health` returns HTTP 200, `database_engine=postgresql`, and `database=reachable`. Then test authenticated login, Gmail status, chat, tasks, and scheduler.
6. Keep the original Render database intact until the new database has passed production verification. Do not delete the old database as part of this workflow.

## What is not automated yet

The Render and GitHub connections available to the assistant do not expose the existing database's sensitive connection URL or allow repository secrets to be created. The hosted read-only SQL connector is blocked by the database's empty external IP allowlist. The workflow now handles this safely by adding only its current runner IP temporarily and removing it afterward, but it still needs the owner to add the encrypted source URL, Render API key, and backup passphrase secrets. Migration additionally needs a target URL and a destination with enough capacity. **No dump or restore has been executed yet.**

The current Render production database must stay untouched until the migration is verified.
