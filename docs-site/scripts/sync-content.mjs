// Pulls the-loop's canonical markdown (docs/, cli/README.md, skills/the-loop/reference/)
// into docs-site/ so the site has one source of truth instead of duplicated-by-hand
// copies that drift. Run automatically before docs:dev / docs:build.
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const repoRoot = dirname(siteRoot);

// [sourceDir (repo-relative), destDir (docs-site-relative), transform?]
const DIR_MAPPINGS = [
  ["docs/decisions", "developer/decisions", null],
  ["docs/capabilities", "developer/capabilities", rewriteCapabilityLinks],
  // Kept under reference/ (not directly in developer/operating-model/) so it never
  // collides with the hand-written developer/operating-model/index.md landing page.
  ["skills/the-loop/reference", "developer/operating-model/reference", rewriteReferenceLinks],
];

// [sourceFile (repo-relative), destFile (docs-site-relative), transform?]
const FILE_MAPPINGS = [
  ["docs/architecture/architecture.md", "developer/architecture.md", null],
  ["docs/roadmap.md", "developer/roadmap.md", null],
  ["cli/README.md", "cli/index.md", null],
];

function rewriteCapabilityLinks(content) {
  return content
    .replaceAll("../architecture/architecture.md", "../architecture.md")
    .replaceAll("../../cli/README.md", "/cli/")
    .replaceAll("../../skills/the-loop/SKILL.md", "/developer/operating-model/")
    .replace(
      /\.\.\/\.\.\/skills\/the-loop\/reference\/([a-z-]+)\.md/g,
      "/developer/operating-model/reference/$1.md",
    );
}

function rewriteReferenceLinks(content) {
  return content.replaceAll("../../../docs/decisions/", "/developer/decisions/");
}

function copyFile(srcRel, destRel, transform) {
  const srcPath = join(repoRoot, srcRel);
  const destPath = join(siteRoot, destRel);
  mkdirSync(dirname(destPath), { recursive: true });
  const content = readFileSync(srcPath, "utf8");
  writeFileSync(destPath, transform ? transform(content) : content);
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

for (const [srcRel, destRel, transform] of FILE_MAPPINGS) {
  copyFile(srcRel, destRel, transform);
}

console.log("docs-site: content synced from docs/, cli/README.md, skills/the-loop/reference/");
