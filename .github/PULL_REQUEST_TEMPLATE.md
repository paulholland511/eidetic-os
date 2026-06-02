<!--
Thanks for contributing! Keep changes focused and read CONTRIBUTING.md first.
THE GOLDEN RULE: never commit personal data, credentials, or PII.
-->

## Summary of changes

<!-- What does this PR do, and why? -->

## Type of change

<!-- Put an `x` in all that apply. -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] Feature (non-breaking change that adds functionality)
- [ ] Documentation
- [ ] Refactor / tooling / chore
- [ ] Breaking change (fix or feature that changes existing behavior)

## Testing done

<!-- How did you verify this works? Commands run, output, manual steps. -->

```bash
ruff check scripts tests
pytest
```

## Checklist

- [ ] Tests pass locally (`pytest`) and lint is clean (`ruff check scripts tests`)
- [ ] Docs updated where relevant (README, `docs/`, `CHANGELOG.md`)
- [ ] New env vars documented in `.env.example` and `docs/CONFIGURATION.md`
- [ ] No PII, credentials, secrets, or vault content in the diff (ran the
      PII scan in `CONTRIBUTING.md`)
- [ ] `SKILL.md` / template additions use `{{PLACEHOLDER}}` tokens, not real values
