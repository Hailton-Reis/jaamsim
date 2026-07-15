# Security policy

## Supported status

This repository is an academic prototype and does not currently provide a production support guarantee.

## Reporting a vulnerability

Do not publish API keys, private model files, personal data, or exploit details in a public issue. Contact the repository maintainer privately through the email address associated with the GitHub account before disclosing sensitive details.

## Data and credentials

- offline RCL and StatFit-like analysis does not require network access;
- online LLM assistance is disabled unless explicitly requested;
- provider keys must be supplied through local environment variables or an ignored `.env` file;
- generated output is ignored because it can contain model names or user-provided data;
- do not process confidential models with an online provider without authorization;
- do not commit `.env`, logs, chat histories, snapshots derived from private models, or generated reports.

## Threat model notes

Online prompts and attached text must be treated as untrusted input. A language-model response is advisory and must not execute code or modify a simulation automatically. Deterministic rules and human review remain the control boundary.

