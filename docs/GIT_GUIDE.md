# Git Guide

[← Back to README](../README.md)

This project follows a **GitHub Flow–based workflow** with strict naming conventions to keep collaboration clean, predictable, and scalable.

> Git is not just version control — it is communication. Every branch and commit should clearly describe intent.

---

## Branch Strategy

We use **short-lived branches** created from `main`.

```text
main
 ├── feature/*
 ├── bugfix/*
 ├── hotfix/*
 ├── refactor/*
 ├── docs/*
 ├── test/*
 └── chore/*
```

---

## Branch Naming Convention

### Format

```text
type/short-description
```

Optional:

```text
type/ticket-id-short-description
```

### Allowed Characters

- lowercase letters
- numbers
- hyphens (-)
- slash (/)

### Examples

**Feature**

```text
feature/login
feature/user-profile
feature/auth-refresh-token
```

**Bugfix**

```text
bugfix/login-redirect-loop
bugfix/token-expired-error
```

**Hotfix** (production urgent)

```text
hotfix/payment-failure
hotfix/security-patch
```

**Refactor**

```text
refactor/auth-service
refactor/api-layer
```

**Docs**

```text
docs/readme-update
docs/api-guide
```

**Chore**

```text
chore/update-dependencies
chore/remove-unused-code
```

### Avoid

```text
Feature/LoginPage
fix1
my-branch
update
John-branch
```

---

## Workflow

```text
1. Pull latest main
2. Create branch
3. Develop feature
4. Commit changes
5. Push branch
6. Open Pull Request
7. Code review
8. Merge to main
```

### Start New Work

```bash
git checkout main
git pull origin main

git checkout -b feature/login
```

### Keep Branch Updated

Prefer **rebase** for clean history.

```bash
git fetch origin

git rebase origin/main
```

OR merge if your team prefers:

```bash
git merge origin/main
```

---

## Commit Convention

We use **Conventional Commits**.

### Format

```text
type(scope): description
```

### Types

```text
feat     → new feature
fix      → bug fix
refactor → code change (no behavior change)
docs     → documentation
test     → tests
chore    → maintenance
style    → formatting only
perf     → performance improvement
ci       → CI/CD changes
build    → build system changes
```

### Examples

```text
feat(auth): add login with email
fix(api): handle unauthorized response
refactor(user): simplify mapper
docs: update contributing guide
test(auth): add login tests
chore: upgrade dependencies
```

### Bad commits

```text
fix stuff
update
changes
final commit
```

---

## Pull Request Flow

### PR Title

Good:

```text
Add login authentication flow
Fix leaderboard pagination
Improve API error handling
```

Bad:

```text
fix
update
work
```

### PR Description Template

```md
## Summary

What changed and why

## Changes

- Feature A
- Fix B
- Refactor C

## How to Test

- Step 1
- Step 2

## Notes

Any important context
```

---

## Before Opening a PR

- [ ] Code runs successfully (`python manage.py check`, see `README.md`)
- [ ] Lint passes (`make lint`, including naming — see `docs/NAMING_CONVENTIONS.md`)
- [ ] Tests pass (`pytest`)
- [ ] No unused debug output (`print`, stray logging)
- [ ] Code follows `docs/CODING_GUIDELINES.md` and `docs/LAYER_GUIDELINES.md` (new code is in the right layer — view/service/repository/model/util)
- [ ] Branch is up to date with main

---

## Code Review Rules

Review focuses on:

- Correctness
- Readability
- Maintainability
- Performance
- Security
- Test coverage

---

## Merge Rules

- Never push directly to `main`
- All changes go through PR
- Require at least 1 review (recommended)
- Squash merge preferred (optional policy)

---

## Branch Cleanup

After merge:

```bash
git branch -d feature/login
git push origin --delete feature/login
```

---

## Rules

### Do NOT

- commit secrets
- push `.env`
- commit virtualenvs (`venv/`, `.venv/`) or `__pycache__/`
- force push to shared branches
- commit broken code to main

---

## Best Practices

- Keep branches small and focused
- One feature = one branch
- Commit often, but meaningfully
- Write descriptive commit messages
- Rebase before PR
- Keep PRs small and reviewable

---

## Why This Matters

Consistent Git practices:

- improve collaboration
- reduce merge conflicts
- speed up code review
- make history readable
- support CI/CD automation

---

## Summary

If you're unsure:

> Keep branch small, commit clean, PR simple.
