import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf-8"));
const version = pkg.version;
const bare = version.replace(/-.*$/, "");
console.log(`Syncing version: ${version} (bare: ${bare})`);

const cargoPath = resolve(root, "src-tauri", "Cargo.toml");
let cargo = readFileSync(cargoPath, "utf-8");
const pkgName = cargo.match(/^name\s*=\s*"([^"]*)"/m)?.[1];
if (!pkgName) {
  console.error("Could not find package name in Cargo.toml");
  process.exit(1);
}
cargo = cargo.replace(/^(version\s*=\s*")[^"]*(")\s*$/m, `$1${bare}$2`);
writeFileSync(cargoPath, cargo);
console.log(`  Updated ${cargoPath}`);

const cargoLockPath = resolve(root, "src-tauri", "Cargo.lock");
let cargoLock = readFileSync(cargoLockPath, "utf-8");
cargoLock = cargoLock.replace(
  new RegExp(`^(name\\s*=\\s*"${pkgName}"\\nversion\\s*=\\s*")[^"]*(")\\s*$`, "m"),
  (_, prefix, suffix) => `${prefix}${bare}${suffix}`,
);
writeFileSync(cargoLockPath, cargoLock);
console.log(`  Updated ${cargoLockPath}`);

const tauriConfPath = resolve(root, "src-tauri", "tauri.conf.json");
const tauriConf = JSON.parse(readFileSync(tauriConfPath, "utf-8"));
tauriConf.version = bare;
writeFileSync(tauriConfPath, JSON.stringify(tauriConf, null, 2) + "\n");
console.log(`  Updated ${tauriConfPath}`);