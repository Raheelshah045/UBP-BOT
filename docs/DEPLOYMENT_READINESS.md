# UBP BOT — Deployment and UAT Guide

## Purpose

This guide covers installation, configuration, operator-assisted portal authentication, validation, and rollback for the UBP BOT application.

Production use requires the applicable business-owner UAT, Information Security review, IT approval, and change-management authorization.

## Before deployment

- Windows 10/11 64-bit workstation.
- Approved access to the OTC BPS and GNB portals.
- IT-approved application folder and writable runtime-data locations.
- Network allowlisting for the approved portal endpoints.
- Confirmed browser policy: bundled Chromium or an IT-managed browser channel.
- Named operator account and authorized portal credentials.

## Configure portal endpoints

Before connecting to a live portal, open `config/config.json` and replace the two endpoint placeholders with the exact IT-approved URLs:

- `portal.login_url`: OTC BPS login URL.
- `gnb.login_url`: GNB login URL.
- `gnb.rejected_transactions_url`: GNB transaction search/report page, if different from its login URL.

Do not add passwords, OTP seeds, session cookies, or customer data to the repository. Use the approved credential handling method for the workstation. GNB username and password fields are intentionally blank in the handover configuration.

## Browser and manual authentication

OTC and GNB live portal sessions launch in visible browser windows. Headless mode is disabled in the live browser launch paths so the operator can complete interactive authentication.

1. Start the required OTC or GNB workflow from the application.
2. Complete the portal's approved username/password, CAPTCHA, and OTP steps in its visible browser.
3. Leave the browser open while the application detects authentication and continues.
4. Confirm the application reports that the OTC Check Bill Status screen or GNB authenticated state is ready.
5. Do not close the browser while a batch is active.

Authentication detection is based on configured portal selectors. If the portal's page structure changes, update and validate the selectors with the portal owner before operational use.

## Portable package

The Windows portable package is built by GitHub Actions from the `final-testing` branch. Download the artifact named `UBP-BOT-final-testing-portable` from the successful workflow run.

Extract the artifact to an IT-approved user-writable directory. Do not run it as a Windows service: interactive CAPTCHA and OTP require an active logged-in desktop session.

Run:
- `run_ubp_bot.bat` to launch the application.
- `verify_environment.bat` to run pre-flight diagnostics.

The portable package includes the executable, required runtime files, browser runtime, and application configuration. The endpoint placeholders must be configured before live portal testing.

## UAT checklist

- [ ] Application launches from a standard user account without elevation.
- [ ] Diagnostics report usable runtime, browser, and writable application folders.
- [ ] OTC browser opens visibly.
- [ ] OTC operator can complete credentials, CAPTCHA, and OTP.
- [ ] OTC authentication is detected and Check Bill Status becomes available.
- [ ] GNB browser opens visibly in its separate profile.
- [ ] GNB operator can complete credentials, CAPTCHA, and OTP where required.
- [ ] GNB authentication is detected and extraction proceeds.
- [ ] OTC and GNB can run without sharing browser sessions or output workbooks.
- [ ] Response codes 95 and 98 are excluded from OTC rejection output.
- [ ] Excel formula-injection protection is verified.
- [ ] Duplicate-file handling and checkpoint recovery are verified.
- [ ] Logs do not expose passwords, OTPs, tokens, or complete consumer numbers.
- [ ] Input/output directory selection and persistence work as expected.
- [ ] Stop/cancel behavior preserves recoverable processing state.

Record the workstation, application commit, test date, operator, test evidence, and any exceptions. Automated CI results do not replace live portal UAT or formal approval.

## Operational precautions

- Use only authorized portal accounts and approved workstation environments.
- Keep browser profiles, checkpoints, logs, input files, and reports within IT-approved storage.
- Never upload live customer files, reports, browser profiles, or credentials to GitHub.
- Do not run concurrent instances against the same browser profile or runtime directories.
- Keep the operator's Windows desktop session active during interactive authentication.

## Rollback

1. Stop OTC and GNB workflows from the dashboard.
2. Confirm browser processes for the application have closed.
3. Preserve the required logs and checkpoint database in an approved restricted location.
4. Restore the previously approved application package.
5. Record the rollback reason, time, application commit, and affected batch identifiers.
