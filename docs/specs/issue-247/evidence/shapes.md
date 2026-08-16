---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#247"
---

<!-- Captured linter output below quotes a hard tab back at us, because a hard tab is
     one of the things section 3 feeds it. Kept verbatim; MD010 disabled for this file. -->
<!-- markdownlint-disable MD010 -->

# Evidence: the linter's verdict on each shape (issue-247)

Every run below is the linter `make lint` pins — `markdownlint-cli2@0.18.1`
(markdownlint v0.38.0) — invoked from the repository root, so the repository's own
`.markdownlint-cli2.jsonc` applies. Files were written under `.mdcheck-tmp/` for the
run and removed afterwards.

## 1. The three candidate attribution shapes (task 1)

The design's rejection table, measured rather than reasoned about.

```console
$ npx --yes markdownlint-cli2@0.18.1 ".mdcheck-tmp/cand-*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: .mdcheck-tmp/cand-*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 3 file(s)
Summary: 1 error(s)
.mdcheck-tmp/cand-a-emphasis-alone.md:7 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "@owner"]
```

`cand-a` is the shipped shape before this fix (`**@owner**` alone), `cand-b` the chosen
one (`**@owner** wrote:`), `cand-c` the ticket's blockquote suggestion (`> **@owner**`).

`cand-c` passes — but only because MD036 does not descend into blockquotes, which section
3 below shows again from the other side. That is why the fix took `cand-b`: it fails the
rule's premise outright instead of resting on where the rule chooses to look.

## 2. A real artifact, recorded by each shape (T12)

Both files are the output of the actual hook over the same two comments: `new.md` as the
fixed `record_feedback` wrote it, `old.md` the same text with the attribution returned to
the pre-fix expression.

```console
$ npx --yes markdownlint-cli2@0.18.1 ".mdcheck-tmp/old.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: .mdcheck-tmp/old.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 1 file(s)
Summary: 2 error(s)
.mdcheck-tmp/old.md:11 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "@owner"]
.mdcheck-tmp/old.md:15 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "@second"]
```

```console
$ npx --yes markdownlint-cli2@0.18.1 ".mdcheck-tmp/new.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: .mdcheck-tmp/new.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 1 file(s)
Summary: 0 error(s)
```

The recorded section, as the fixed hook writes it:

```markdown
## Review comments

### 2026-08-16 — approved-with-comments

**@owner** wrote:

approved, but tighten the nit in the error path

**@second** wrote:

lgtm
```

## 3. Why the reviewer's body is out of scope

A deliberately hostile comment body — an H1, a mixed bullet marker, a hard tab, a line of
bold text — recorded verbatim, and the same body blockquoted. If quoting the body were a
defence, the second file would be clean.

```console
$ npx --yes markdownlint-cli2@0.18.1 ".mdcheck-tmp/body-*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: .mdcheck-tmp/body-*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 2 file(s)
Summary: 8 error(s)
.mdcheck-tmp/body-blockquoted.md:9 MD025/single-title/single-h1 Multiple top-level headings in the same document [Context: "my big heading"]
.mdcheck-tmp/body-blockquoted.md:12:3 MD004/ul-style Unordered list style [Expected: asterisk; Actual: plus]
.mdcheck-tmp/body-blockquoted.md:15:3 MD010/no-hard-tabs Hard tabs [Column: 3]
.mdcheck-tmp/body-blockquoted.md:15:3 MD027/no-multiple-space-blockquote Multiple spaces after blockquote symbol [Context: "> 	tab line"]
.mdcheck-tmp/body-verbatim.md:9 MD025/single-title/single-h1 Multiple top-level headings in the same document [Context: "my big heading"]
.mdcheck-tmp/body-verbatim.md:12:1 MD004/ul-style Unordered list style [Expected: asterisk; Actual: plus]
.mdcheck-tmp/body-verbatim.md:15:1 MD010/no-hard-tabs Hard tabs [Column: 1]
.mdcheck-tmp/body-verbatim.md:17 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "bold as heading"]
```

It is not. MD025, MD004 and MD010 fire identically through a blockquote (MD032 would too,
under markdownlint's defaults; this repository disables it), and the quoting adds an MD027
of its own. The only thing blockquoting buys is MD036 — the one rule this fix already
handles in the text the harness itself writes, and `body-blockquoted.md` shows that same
quirk from section 1 again: the body's `**bold as heading**` is not flagged once quoted.

So there is no shape that makes an arbitrary human comment lint-clean, and rewriting a
reviewer's words to chase one is not something the harness should do. Hence
`bugfix.md` §Out of scope.

## 4. The empty-body case (R1.2)

A reviewer who approves without writing anything produced `**@handle**` followed by two
blank lines under the pre-fix expression — an MD012 on top of the MD036, whether the
block lands mid-file or at the end.

```console
$ npx --yes markdownlint-cli2@0.18.1 ".mdcheck-tmp/empty-*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: .mdcheck-tmp/empty-*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 2 file(s)
Summary: 5 error(s)
.mdcheck-tmp/empty-eof.md:11 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "@second"]
.mdcheck-tmp/empty-eof.md:13 MD012/no-multiple-blanks Multiple consecutive blank lines [Expected: 1; Actual: 2]
.mdcheck-tmp/empty-eof.md:14 MD012/no-multiple-blanks Multiple consecutive blank lines [Expected: 1; Actual: 3]
.mdcheck-tmp/empty-mid.md:7 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "@second"]
.mdcheck-tmp/empty-mid.md:9 MD012/no-multiple-blanks Multiple consecutive blank lines [Expected: 1; Actual: 2]
```

The fixed hook writes one line for that comment — `**@handle** left no comment text.` —
which is neither an emphasis-only paragraph nor a blank-line run. The attribution survives:
an approval submitted with no text is still a fact about the gate, so it is recorded rather
than dropped.
