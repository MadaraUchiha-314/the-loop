// Pulls the two doc sources that structurally cannot live under docs/ into the site:
// cli/README.md is also the CLI's PyPI package readme (cli/pyproject.toml readme=),
// and skills/the-loop/reference/*.md is read at RUNTIME by the harness from that exact
// path. Everything else the site needs (architecture/, capabilities/, decisions/,
// roadmap.md) already lives directly under docs/ and needs no copy. Run automatically
// before docs:dev / docs:build.
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const repoRoot = dirname(siteRoot);

const FILE_MAPPINGS = [["cli/README.md", "cli.md", null]];

// [sourceDir (repo-relative), destDir (docs-relative), transform?]
const DIR_MAPPINGS = [["skills/the-loop/reference", "operating-model/reference", rewriteReferenceLinks]];

function rewriteReferenceLinks(content) {
  return content.replaceAll("../../../docs/decisions/", "/decisions/");
}

function copyFile(srcRel, destRel, transform) {
  const srcPath = join(repoRoot, srcRel);
  const destPath = join(siteRoot, destRel);
  mkdirSync(dirname(destPath), { recursive: true });
  const content = readFileSync(srcPath, "utf8");
  writeFileSync(destPath, transform ? transform(content) : content);
}

for (const [srcRel, destRel, transform] of FILE_MAPPINGS) {
  copyFile(srcRel, destRel, transform);
}

for (const [srcDirRel, destDirRel, transform] of DIR_MAPPINGS) {
  const destDir = join(siteRoot, destDirRel);
  if (existsSync(destDir)) rmSync(destDir, { recursive: true, force: true });
  mkdirSync(destDir, { recursive: true });

  const srcDir = join(repoRoot, srcDirRel);
  for (const entry of readdirSync(srcDir)) {
    if (!entry.endsWith(".md")) continue;
    copyFile(join(srcDirRel, entry), join(destDirRel, entry), transform);
  }
}

console.log("docs: synced cli/README.md -> docs/cli.md, skills/the-loop/reference/ -> docs/operating-model/reference/");
