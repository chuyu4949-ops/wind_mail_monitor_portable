# Repository Automation Rules

After completing a user-requested code change in this repository:

1. Run the relevant automated tests.
2. Rebuild `release/WindMailMonitor-portable.zip` when the customer application changes.
3. Verify that release files do not contain mailbox accounts, authorization codes, licenses, private keys, or customer runtime data.
4. Stage only files related to the current request. Never stage unrelated or untracked runtime directories.
5. Create a concise Git commit after verification succeeds.
6. Push the commit to `origin/main` unless the user explicitly asks not to publish it.
7. Clearly report any test, build, commit, or push failure.

The background auto-push process may only push existing commits. It must never add or commit files.
