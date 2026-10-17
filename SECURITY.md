# Security Policy

## Supported Versions

Security fixes are applied to the current default branch. Older builds may not receive fixes; upgrade to the latest verified release where possible.

## Reporting a Vulnerability

Please do not publish credentials, tokens, personal data, or exploitable details in a public issue.

Report suspected vulnerabilities privately through GitHub's **Report a vulnerability** feature on this repository's Security tab, if enabled. Include:
- A concise impact description and affected commit or release.
- Reproduction steps and sanitized logs.
- Any suggested mitigation.

Do not include live API keys, broker credentials, TOTP seeds, access tokens, or user data. If private vulnerability reporting is unavailable, contact the repository maintainer privately through their verified GitHub profile.

## Credential handling

- Keep secrets in deployment secret stores or untracked local environment files.
- Never commit broker credentials, TOTP seeds, encryption keys, or private server tokens.
- Firebase web configuration is client-visible by design; protect the project with API-key restrictions, enabled authorized domains, Firebase Authentication, and strict Firestore Security Rules.
- Treat any key that was unintentionally exposed or insufficiently restricted as potentially compromised and rotate/restrict it in the provider console.
