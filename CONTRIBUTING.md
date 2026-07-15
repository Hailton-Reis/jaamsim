# Contributing

Thank you for helping improve this academic prototype.

## Before opening a change

1. Confirm whether the change belongs to upstream JaamSim or this extension.
2. Open a focused issue that describes the problem, evidence, expected behavior, and scope.
3. Keep deterministic rules, optional online assistance, and UI integration separate.
4. Do not include private simulation models, credentials, thesis files, or copyrighted papers.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r extensions\academic-assistant\requirements-dev.txt
python -m pytest extensions\academic-assistant\python\tests
.\scripts\build.ps1
```

## Pull request checklist

- [ ] change is based on branch `academic-assistants-v2026-03`;
- [ ] new or changed behavior has focused tests;
- [ ] Python tests pass;
- [ ] JaamSim clean build passes;
- [ ] no secrets or private data are present;
- [ ] user-facing behavior and limitations are documented;
- [ ] modified upstream files are recorded in `CHANGES.md`;
- [ ] network access remains opt-in;
- [ ] model changes still require human confirmation.

## Rule changes

Every new RCL rule should document:

- rule identifier and severity;
- exact trigger condition;
- expected evidence;
- safe operator guidance;
- positive and negative tests;
- known false-positive and false-negative risks.

## Commit style

Use small commits with messages such as:

```text
feat: add rule contract check
fix: resolve assistant root from fork layout
docs: clarify batch evidence branches
test: cover disconnected process path
```

