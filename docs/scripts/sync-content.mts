// Pulls the two doc sources that structurally cannot live under docs/ into the site:
// cli/README.md is also the CLI's PyPI package readme (cli/pyproject.toml readme=),
// and skills/the-loop/reference/*.md is read at RUNTIME by the harness from that exact
// path. Everything else the site needs (architecture/, capabilities/, decisions/,
// specs/) already lives directly under docs/ and needs no copy. Run automatically
// before docs:dev / docs:build (Node runs this .mts directly via native type stripping).
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

type Transform = (content: string) => string;
type FileMapping = readonly [srcRel: string, destRel: string, transform: Transform | null];
type DirMapping = readonly [srcDirRel: string, destDirRel: string, transform: Transform | null];

const siteRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const repoRoot = dirname(siteRoot);

function rewriteReferenceLinks(content: string): string {
  return content.replaceAll("../../../docs/decisions/", "/decisions/");
}

const FILE_MAPPINGS: readonly FileMapping[] = [["cli/README.md", "cli.md", null]];

const DIR_MAPPINGS: readonly DirMapping[] = [
  ["skills/the-loop/reference", "operating-model/reference", rewriteReferenceLinks],
];

function copyFile(srcRel: string, destRel: string, transform: Transform | null): void {
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
