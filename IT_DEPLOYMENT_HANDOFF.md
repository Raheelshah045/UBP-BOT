# UBP BOT — IT Deployment Handover

## Included

- UBP BOT Windows desktop application.
- OTC and GNB portal automation modules.
- Visible browser launch for interactive CAPTCHA and OTP.
- Separate OTC and GNB browser profiles.
- Runtime configuration and operational directories.
- Pre-flight diagnostics and portable launch scripts.
- Deployment, security, and UAT documentation.

## Required before live testing

1. Configure the approved OTC and GNB portal URLs in `config/config.json`.
2. Confirm the browser runtime is permitted by workstation security policy.
3. Confirm the extracted application folder and runtime directories are writable by the operator.
4. Confirm portal network access and authorized test accounts with the portal owners.
5. Keep the operator logged into an interactive Windows desktop session.

The handover configuration intentionally contains endpoint placeholders and blank GNB credentials. No production credentials or customer data are included.

## Launch

- Run `verify_environment.bat` first.
- Resolve any failed diagnostics.
- Run `run_ubp_bot.bat`.
- Start OTC or GNB from the dashboard and complete manual authentication in the visible browser window.

## Validation status

This package is a testing handover candidate. A successful GitHub Actions run validates automated checks and package construction only. It does not certify live portal authentication, production security, or production readiness. Complete the UAT checklist in `docs/DEPLOYMENT_READINESS.md` and obtain required approvals before production use.

## Source

Repository branch: `final-testing`
