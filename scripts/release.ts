#!/usr/bin/env bun

import { execSync } from 'node:child_process';
import { existsSync, fstatSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { stdin as input, stdout as output } from 'node:process';
import * as readline from 'node:readline/promises';

const rl = readline.createInterface({ input, output });
let pipedLines: string[] | null = null;
let pipedIdx = 0;
function isPipedInput(): boolean {
  try {
    const stat = fstatSync(0);
    return stat.isFIFO() || stat.isFile();
  } catch {
    return input.isTTY === false;
  }
}
function getPipedLines(): string[] {
  if (pipedLines !== null) return pipedLines;
  try {
    if (isPipedInput()) {
      const data = readFileSync(0, 'utf-8');
      pipedLines = data.split(/\r?\n/);
    } else {
      pipedLines = [];
    }
  } catch {
    pipedLines = [];
  }
  return pipedLines;
}
const ask = async (q: string): Promise<string> => {
  if (isPipedInput()) {
    const lines = getPipedLines();
    const ans = lines[pipedIdx++] ?? '';
    output.write(q);
    output.write(ans + '\n');
    return ans;
  }
  return rl.question(q);
};
const checkYesOrNo = (ans: string) => ans.trim().toLowerCase() === 'n';

const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const YELLOW = '\x1b[1;33m';
const BLUE = '\x1b[0;34m';
const DIM = '\x1b[2m';
const NC = '\x1b[0m';

function step(msg: string) {
  console.log(`\n${BLUE}==>${NC} ${msg}`);
}
function ok(msg: string) {
  console.log(`  ${GREEN}ok${NC} ${msg}`);
}
function fail(msg: string): never {
  console.error(`  ${RED}error${NC} ${msg}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Version parsing
// ---------------------------------------------------------------------------

interface VersionParsed {
  year: number;
  month: number;
  patch: number;
  prerelease: string | null;
  prereleaseNum: number;
}

function tryParseVersion(v: string): VersionParsed | null {
  const match = v.match(/^(\d{2})\.(\d{1,2})\.(\d+)(?:-(.+?)\.(\d+))?$/);
  if (!match) return null;
  return {
    year: parseInt(match[1], 10),
    month: parseInt(match[2], 10),
    patch: parseInt(match[3], 10),
    prerelease: match[4] ?? null,
    prereleaseNum: match[5] ? parseInt(match[5], 10) : 0,
  };
}

function parseVersion(v: string): VersionParsed {
  const parsed = tryParseVersion(v);
  if (!parsed) fail(`Invalid version: "${v}"`);
  return parsed;
}

function getLastNonBetaTag(): string {
  execSync('git fetch --tags --force', { stdio: 'ignore' });
  try {
    const tags = execSync('git tag --list "v*" --sort=-creatordate', { encoding: 'utf-8' })
      .trim()
      .split('\n')
      .filter(Boolean);
    for (const tag of tags) {
      const ver = tag.replace(/^v/, '');
      if (!/-/.test(ver)) return tag;
    }
    return '';
  } catch {
    return '';
  }
}

// ---------------------------------------------------------------------------
// Version resolution
// ---------------------------------------------------------------------------

function resolveNextVersion(current: string, bump: string, betaModifier: boolean): string {
  const parsed = parseVersion(current);
  const now = new Date();
  const yy = now.getFullYear() % 100;
  const mm = now.getMonth() + 1;
  const yStr = String(yy).padStart(2, '0');
  const mStr = String(mm);

  switch (bump) {
    case 'patch':
      if (parsed.year === yy && parsed.month === mm) {
        return betaModifier ? `${yStr}.${mStr}.${parsed.patch + 1}-beta.1` : `${yStr}.${mStr}.${parsed.patch + 1}`;
      }
      return betaModifier ? `${yStr}.${mStr}.0-beta.1` : `${yStr}.${mStr}.0`;
    case 'beta':
      if (parsed.prerelease === null) fail('Not a beta version. Use "patch beta" to start a beta series.');
      return `${String(parsed.year).padStart(2, '0')}.${parsed.month}.${parsed.patch}-beta.${parsed.prereleaseNum + 1}`;
    default:
      return bump;
  }
}

// ---------------------------------------------------------------------------
// Changelog generation
// ---------------------------------------------------------------------------

function generateChangelog(next: string, baseTag?: string): { changelogEntry: string; releaseEntry: string } {
  let rangeStart = baseTag;
  if (rangeStart === undefined) {
    try {
      rangeStart = execSync('git tag --list "v*" --sort=-creatordate', { encoding: 'utf-8' }).trim().split('\n')[0] ?? '';
    } catch {
      rangeStart = '';
    }
  }

  const range = rangeStart ? `${rangeStart}..HEAD` : 'HEAD';

  const log = execSync(`git log ${range} --pretty=format:"%s%n" --reverse`, { encoding: 'utf-8' });
  const lines = log.split('\n').filter(Boolean);

  const added: string[] = [];
  const fixed: string[] = [];
  const changed: string[] = [];
  const other: string[] = [];

  const pattern = /^(\w+)(\(.*?\))?!?:\s(.+)$/;

  for (const line of lines) {
    const m = line.match(pattern);
    if (m) {
      const [, type, scope, msg] = m;
      const entry = scope ? `**${scope.slice(1, -1)}**: ${msg}` : msg;
      switch (type) {
        case 'feat':
          added.push(entry);
          break;
        case 'fix':
          fixed.push(entry);
          break;
        case 'refactor':
        case 'perf':
        case 'style':
          changed.push(entry);
          break;
        default:
          other.push(entry);
          break;
      }
    } else {
      // Non-conventional commit: treat as Other
      other.push(line);
    }
  }

  let body = '';
  if (added.length) body += '\n\n### Added\n\n' + added.map((e) => `- ${e}`).join('\n');
  if (fixed.length) body += '\n\n### Fixed\n\n' + fixed.map((e) => `- ${e}`).join('\n');
  if (changed.length) body += '\n\n### Changed\n\n' + changed.map((e) => `- ${e}`).join('\n');
  if (other.length) body += '\n\n### Other\n\n' + other.map((e) => `- ${e}`).join('\n');
  if (!body) body = '\n\nMaintenance release.';

  const today = new Date().toISOString().slice(0, 10);
  const changelogEntry = `## [${next}] - ${today}${body}`;
  const releaseEntry = body.trimStart();

  return { changelogEntry, releaseEntry };
}

// ---------------------------------------------------------------------------
// Undo log types and helpers
// ---------------------------------------------------------------------------

interface UndoLog {
  version: { from: string; to: string };
  timestamp: string;
  branch: string;
  commit: string;
  tag: string;
  files: Record<string, string | null>;
  created: string[];
}

const UNDO_DIR = '.release-undo';

function captureFileSnapshot(files: string[]): Record<string, string | null> {
  const snapshot: Record<string, string | null> = {};
  for (const file of files) {
    snapshot[file] = existsSync(file) ? readFileSync(file, 'utf-8') : null;
  }
  return snapshot;
}

function saveUndoLog(log: UndoLog) {
  if (!existsSync(UNDO_DIR)) mkdirSync(UNDO_DIR, { recursive: true });
  writeFileSync(join(UNDO_DIR, `v${log.version.to}.json`), JSON.stringify(log, null, 2) + '\n');
}

function listUndoLogs(): { version: string; path: string }[] {
  if (!existsSync(UNDO_DIR)) return [];
  return readdirSync(UNDO_DIR)
    .filter((f: string) => f.endsWith('.json'))
    .map((f: string) => ({ version: f.replace(/^v/, '').replace(/\.json$/, ''), path: join(UNDO_DIR, f) }))
    .sort((a: { version: string }, b: { version: string }) => {
      const pa = tryParseVersion(a.version);
      const pb = tryParseVersion(b.version);
      if (pa && pb) {
        const base = pb.year - pa.year || pb.month - pa.month || pb.patch - pa.patch;
        if (base !== 0) return base;
        if (pa.prerelease && !pb.prerelease) return 1;
        if (!pa.prerelease && pb.prerelease) return -1;
        if (pa.prerelease && pb.prerelease) {
          if (pa.prerelease !== pb.prerelease) return pa.prerelease.localeCompare(pb.prerelease);
          return pb.prereleaseNum - pa.prereleaseNum;
        }
        return 0;
      }
      return b.version.localeCompare(a.version);
    });
}

async function undoRelease(dryRun = false) {
  const logs = listUndoLogs();
  if (logs.length === 0) fail('No undo logs found.');

  console.log(`${BLUE}Available undo logs:${NC}`);
  logs.forEach((log, i) => console.log(`  ${i + 1}. v${log.version}`));

  const choice = (await ask(`\nSelect version to undo (1-${logs.length}) [1]: `)) || '1';
  const idx = Math.max(0, Math.min(logs.length - 1, parseInt(choice, 10) - 1)) || 0;
  const selected = logs[idx];

  const log: UndoLog = JSON.parse(readFileSync(selected.path, 'utf-8'));
  console.log(`\nWill undo release v${log.version.to}:`);
  console.log(`  commit : ${log.commit.substring(0, 7)}`);
  console.log(`  tag    : ${log.tag}`);
  console.log(`  branch : ${log.branch}`);

  const proceed = await ask(`\nProceed? This will delete the local/remote tag and the GitHub release. (y/N) `);
  if (proceed.toLowerCase() !== 'y') {
    console.log('Aborted.');
    process.exit(0);
  }

  const branch = execSync('git branch --show-current', { encoding: 'utf-8' }).trim();
  if (branch !== log.branch) {
    const sw = await ask(`  Not on '${log.branch}' (on '${branch}'). Switch? (y/N) `);
    if (sw.toLowerCase() !== 'y') {
      console.log('Aborted.');
      process.exit(0);
    }
    if (!dryRun) execSync(`git checkout ${log.branch}`, { encoding: 'utf-8' });
  }

  if (dryRun) {
    console.log(`\n${YELLOW}DRY RUN${NC} — no changes will be made\n`);
  }

  step('Deleting local tag');
  if (!dryRun) execSync(`git tag -d "${log.tag}"`, { stdio: 'ignore', encoding: 'utf-8' });
  ok(`Deleted local tag ${log.tag}`);

  step('Deleting remote tag');
  if (!dryRun) execSync(`git push origin :refs/tags/${log.tag}`, { stdio: 'ignore', encoding: 'utf-8' });
  ok(`Deleted remote tag ${log.tag}`);

  step('Deleting GitHub release');
  if (!dryRun) {
    try {
      execSync(`gh release delete "v${log.version.to}" --yes`, { stdio: 'ignore', encoding: 'utf-8' });
    } catch {
      console.log(`  ${YELLOW}warning${NC} Could not delete GitHub release.`);
    }
  }
  ok('GitHub release deleted');

  if (!dryRun) {
    rmSync(selected.path);
  }
  ok(`Cleaned up ${selected.path}`);

  console.log(`\n${GREEN}${'='.repeat(40)}${NC}`);
  console.log(`${GREEN}  Undid release v${log.version.to}${NC}`);
  console.log(`${GREEN}${'='.repeat(40)}${NC}\n`);
}

// ---------------------------------------------------------------------------
// Usage
// ---------------------------------------------------------------------------

function showUsage() {
  console.log(`
Usage: ./scripts/release.ts [<bump> [beta]] [flags]

Bump commands:
  patch [beta]       Bump patch version. (e.g. 25.05.3 -> 25.05.4 or 25.05.4-beta.1)
  beta               Increment beta number (must already be beta)
  YY.MM.PATCH        Explicit version
  YY.MM.PATCH-beta.N Explicit beta version

  Append "beta" to start a beta:  patch beta
  No arguments on a beta version strips it to stable.

Flags:
  --no-changelog     Skip changelog generation
  --no-push          Commit and tag locally, skip git push
  --undo             Revert the most recent release
  --dry-run          Show what would be done without making changes
  --help, -h, help   Show this help

  Uncommitted changes are handled interactively: [s] stash & continue, [c] continue anyway, [a] abort.
  In non-interactive environments (CI) the script still exits with an error.

Changelog preview:
  changelog                      Preview changelog for current version
  changelog patch                Preview changelog for next patch

Examples:
  ./scripts/release.ts patch              # 25.05.3 -> 25.05.4
  ./scripts/release.ts patch beta         # 25.05.3 -> 25.05.4-beta.1
  ./scripts/release.ts beta               # 25.05.4-beta.1 -> 25.05.4-beta.2
  ./scripts/release.ts                    # 25.05.4-beta.2 -> 25.05.4 (stable)
  ./scripts/release.ts 25.05.4            # exact version
  ./scripts/release.ts changelog patch    # preview changelog for next patch
  ./scripts/release.ts --undo             # revert the most recent release
   ./scripts/release.ts patch --no-push    # bump locally without pushing
   ./scripts/release.ts --dry-run          # dry run the next release
   ./scripts/release.ts patch --dry-run    # dry run a patch bump
   ./scripts/release.ts --undo --dry-run   # dry run an undo
`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);

  // Help
  if (args.includes('--help') || args.includes('-h') || args.includes('help')) {
    showUsage();
    rl.close();
    process.exit(0);
  }

  // Undo
  if (args.includes('--undo')) {
    const dryRun = args.includes('--dry-run');
    await undoRelease(dryRun);
    rl.close();
    process.exit(0);
  }

  // Dry run
  const dryRun = args.includes('--dry-run');

  // Extract flags
  const skipChangelog = args.includes('--no-changelog');
  const noPush = args.includes('--no-push');
  const flags = new Set(['--undo', '--no-changelog', '--no-push', '--dry-run', '--help', '-h']);
  const positional = args.filter((a) => !flags.has(a));

  const isChangelogMode = positional[0] === 'changelog';
  const releaseArgs = isChangelogMode ? positional.slice(1) : positional;

  const betaModifier = releaseArgs.includes('beta');
  const nonBeta = releaseArgs.filter((a) => a !== 'beta');
  const hasNoBump = nonBeta.length === 0;
  const bumpArg = nonBeta[0] ?? '';

  let bump: string;
  if (hasNoBump && !betaModifier) bump = '';
  else if (hasNoBump && betaModifier) bump = 'beta';
  else bump = bumpArg;

  // Validate tools
  for (const cmd of ['git']) {
    try {
      execSync(`where ${cmd}`, { stdio: 'ignore' });
    } catch {
      try {
        execSync(`command -v ${cmd}`, { stdio: 'ignore' });
      } catch {
        fail(`Required tool not found: ${cmd}`);
      }
    }
  }

  // Read current version
  const pkg = JSON.parse(readFileSync('package.json', 'utf-8'));
  const current = pkg.version as string;
  const parsed = parseVersion(current);

  // Resolve next version
  let next: string;
  if (bump === '') {
    if (parsed.prerelease === null) fail('Already a stable release. Use "patch" to bump, or specify an explicit version.');
    next = `${String(parsed.year).padStart(2, '0')}.${parsed.month}.${parsed.patch}`;
  } else if (['patch', 'beta'].includes(bump)) {
    next = resolveNextVersion(current, bump, betaModifier);
  } else if (/^\d{2}\.\d{1,2}\.\d+(-beta\.\d+)?$/.test(bump)) {
    if (betaModifier) fail('Cannot combine "beta" modifier with an explicit version. Specify the full version instead.');
    next = bump;
  } else {
    fail(`Invalid version or bump type: "${bump}"`);
  }

  console.log(`  bump type : ${bump === '' ? 'stable (strip beta)' : bump}`);
  console.log(`  current   : ${DIM}${current}${NC}`);
  console.log(`  next      : ${GREEN}${next}${NC}\n`);

  // Changelog-only mode
  if (isChangelogMode) {
    step('Generating changelog preview');

    execSync('git fetch --tags --force', { stdio: 'ignore' });

    const isStableFromBeta = parsed.prerelease !== null && !next.includes('-');
    const baseTag = isStableFromBeta ? getLastNonBetaTag() : undefined;
    const { changelogEntry, releaseEntry } = generateChangelog(next, baseTag);

    console.log(`\n${BLUE}=== CHANGELOG.md entry ===${NC}\n`);
    console.log(changelogEntry);
    console.log(`\n${BLUE}=== Release body (changelogs/v${next}.md) ===${NC}\n`);
    console.log(releaseEntry);
    rl.close();
    process.exit(0);
  }

  // Pre-flight checks
  step('Running pre-flight checks');

  let didAutoStash = false;
  if (!dryRun) {
    const status = execSync('git status --porcelain', { encoding: 'utf-8' }).trim();
    if (status) {
      // Non-interactive (CI) — fail fast when stdin is explicitly non-TTY
      if (process.stdin.isTTY === false) {
        fail('Uncommitted changes detected. Commit or stash them first.');
      }
      console.log(`  ${YELLOW}warning${NC} Uncommitted changes detected:`);
      try {
        const short = execSync('git status --short', { encoding: 'utf-8' }).trim();
        if (short) console.log(`${DIM}${short}${NC}`);
      } catch {}
      const ans = await ask('  [s] Stash & continue  [c] Continue anyway  [a] Abort [s/c/a] (a): ');
      const v = ans.trim().toLowerCase();
      if (v === 's') {
        try {
          execSync('git stash push -m "release: autostash before v' + next + '" --include-untracked', {
            stdio: 'inherit',
          });
          didAutoStash = true;
          ok('Stashed working tree');
        } catch (e) {
          fail('Failed to stash changes: ' + e);
        }
      } else if (v === 'c') {
        ok('Continuing with dirty tree');
      } else {
        console.log('Aborted.');
        process.exit(0);
      }
    } else {
      ok('Working tree clean');
    }
  } else {
    ok('Working tree clean (dry run — ignoring dirty check)');
  }

  const branch = execSync('git branch --show-current', { encoding: 'utf-8' }).trim();
  if (branch !== 'main') {
    console.log(`  ${YELLOW}warning${NC} You are on branch '${branch}', not 'main'.`);
    const reply = await ask('  Continue anyway? (y/N) ');
    if (reply.toLowerCase() !== 'y') {
      if (didAutoStash) {
        try {
          execSync('git stash pop', { stdio: 'inherit' });
        } catch {}
      }
      console.log('Aborted.');
      process.exit(0);
    }
  }

  // Confirm
  if (!dryRun) {
    const proceed = await ask(`Proceed with release v${next}? (Y/n) `);
    if (checkYesOrNo(proceed)) {
      if (didAutoStash) {
        try {
          execSync('git stash pop', { stdio: 'inherit' });
        } catch {}
      }
      console.log('Aborted.');
      process.exit(0);
    }
  } else {
    console.log(`\n${YELLOW}DRY RUN${NC} — no changes will be made\n`);
  }

  const isBetaRelease = next.includes('-');
  const isStableFromBeta = parsed.prerelease !== null && !next.includes('-');

  // Snapshot files before any changes (for undo log)
  const fileSnapshot =
    dryRun ?
      {}
    : captureFileSnapshot([
        'package.json',
        'src-tauri/Cargo.toml',
        'src-tauri/Cargo.lock',
        'src-tauri/tauri.conf.json',
        ...(skipChangelog || isBetaRelease ? [] : ['CHANGELOG.md']),
      ]);

  // Bump versions
  step('Updating version numbers');

  if (!dryRun) {
    pkg.version = next;
    writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\n');
    try {
      execSync('bun run sync-version', { stdio: 'inherit' });
    } catch (error) {
      fail('Failed to sync version: ' + error);
    }
  }
  ok('package.json');
  ok('Synced version to Cargo.toml, Cargo.lock, and tauri.conf.json');

  // Changelog
  if (skipChangelog) {
    ok('SKIP — changelog generation disabled');
  } else {
    step('Generating changelog');

    // For stable releases from beta, aggregate all commits since last non-beta tag
    const baseTag = isStableFromBeta ? getLastNonBetaTag() : undefined;
    const { changelogEntry, releaseEntry } = generateChangelog(next, baseTag);

    if (isBetaRelease) {
      ok('SKIP — CHANGELOG.md not updated for beta releases');
    } else if (!dryRun) {
      // Insert into CHANGELOG.md
      const changelogPath = 'CHANGELOG.md';
      if (existsSync(changelogPath)) {
        const changelog = readFileSync(changelogPath, 'utf-8');
        if (changelog.startsWith('## [')) {
          writeFileSync(changelogPath, changelogEntry + '\n\n' + changelog);
        } else {
          const marker = '\n## [';
          const idx = changelog.indexOf(marker);
          if (idx !== -1) {
            const before = changelog.slice(0, idx);
            const after = changelog.slice(idx);
            writeFileSync(changelogPath, before + '\n\n' + changelogEntry + '\n' + after);
          } else {
            writeFileSync(changelogPath, changelog.trimEnd() + '\n\n' + changelogEntry + '\n');
          }
        }
      } else {
        writeFileSync(changelogPath, changelogEntry + '\n');
      }
      ok('CHANGELOG.md');
    } else {
      ok('CHANGELOG.md');
    }

    // Write tag-specific changelog
    const changelogsDir = 'changelogs';
    if (!dryRun) {
      if (!existsSync(changelogsDir)) {
        mkdirSync(changelogsDir, { recursive: true });
      }
      writeFileSync(`${changelogsDir}/v${next}.md`, releaseEntry);
    }
    ok(`${changelogsDir}/v${next}.md`);

    // Preview
    console.log(`\n${BLUE}=== CHANGELOG.md entry ===${NC}\n`);
    console.log(changelogEntry);
    console.log(`\n${BLUE}=== Release body (changelogs/v${next}.md) ===${NC}\n`);
    console.log(releaseEntry);

    if (!dryRun) {
      const looksGood = await ask('Does the changelog look good? (Y/n) ');
      if (checkYesOrNo(looksGood)) {
        console.log(`\n${YELLOW}Reverting changes...${NC}`);
        for (const [file, content] of Object.entries(fileSnapshot)) {
          try {
            if (content === null) rmSync(file);
            else writeFileSync(file, content);
          } catch {}
        }
        try {
          rmSync(`changelogs/v${next}.md`);
        } catch {}
        if (didAutoStash) {
          try {
            execSync('git stash pop', { stdio: 'inherit' });
            console.log(`  ${GREEN}ok${NC} Restored stashed changes`);
          } catch {
            console.log(`  ${YELLOW}warning${NC} Could not pop stash — check 'git stash list'`);
          }
        }
        console.log('Reverted to state before release.');
        console.log(`
If you want to edit manually, run:
  git diff
and re-run: ./scripts/release.ts ${bump}${betaModifier ? ' beta' : ''} ${noPush ? '--no-push' : ''} ${skipChangelog ? '--no-changelog' : ''}
`);
        process.exit(0);
      }
    }
  }

  // Git commit and tag
  step('Creating release commit');

  const filesToAdd = [
    'package.json',
    'src-tauri/Cargo.toml',
    'src-tauri/Cargo.lock',
    'src-tauri/tauri.conf.json',
    ...(skipChangelog ? [] : [`changelogs/v${next}.md`]),
    ...(skipChangelog || isBetaRelease ? [] : ['CHANGELOG.md']),
  ];
  if (!dryRun) {
    execSync(`git add ${filesToAdd.join(' ')}`, { encoding: 'utf-8' });
    execSync(`git commit -m "chore: release v${next}"`, { encoding: 'utf-8' });
  }
  ok(`Committed release v${next}`);

  step('Saving undo log');
  if (!dryRun) {
    const commitHash = execSync('git rev-parse HEAD', { encoding: 'utf-8' }).trim();
    const createdFiles: string[] = skipChangelog ? [] : [`changelogs/v${next}.md`];
    saveUndoLog({
      version: { from: current, to: next },
      timestamp: new Date().toISOString(),
      branch,
      commit: commitHash,
      tag: `v${next}`,
      files: fileSnapshot,
      created: createdFiles,
    });
  }
  ok(`.release-undo/v${next}.json`);

  step(`Creating tag v${next}`);
  if (!dryRun) {
    execSync(`git tag -a "v${next}" -m "Release v${next}"`, { encoding: 'utf-8' });
  }
  ok('Tagged');

  // Push to remote
  if (noPush) {
    console.log(`\n${YELLOW}SKIP — push disabled by --no-push${NC}`);
    console.log(`${DIM}To push manually:${NC}`);
    console.log(`  git push origin ${branch} --tags`);
  } else {
    step(`Pushing to origin/${branch}`);
    if (!dryRun) {
      execSync(`git push origin ${branch} --tags`, { encoding: 'utf-8' });
    }
    ok('Pushed');
  }

  if (didAutoStash && !dryRun) {
    step('Restoring stashed changes');
    try {
      execSync('git stash pop', { stdio: 'inherit' });
      ok('Restored stashed changes');
    } catch {
      console.log(`  ${YELLOW}warning${NC} Could not pop stash — check 'git stash list'`);
    }
  }

  // Done
  if (!dryRun) {
    console.log(`\n${GREEN}========================================${NC}`);
    console.log(`${GREEN}  Released v${next}${NC}`);
    console.log(`${GREEN}========================================${NC}\n`);
    console.log('Next step:');
    console.log('  CI will build and create a GitHub release.\n');
    console.log('To undo this release:');
    console.log('  ./scripts/release.ts --undo');
  }
}

main()
  .catch((err) => {
    console.error('Release script failed:', err);
    process.exit(1);
  })
  .finally(() => rl.close());
