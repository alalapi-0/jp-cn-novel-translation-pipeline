import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { randomUUID } from "node:crypto";

const contextKey = "LIGHT_NOVEL_PLAYWRIGHT_OUTPUT_CONTEXT";
const markerName = ".playwright-output-owner.json";

function fail(message) { throw new Error(`Playwright output storage: ${message}`); }

export function canonicalDirectory(target, { allowMissing = false } = {}) {
  if (!path.isAbsolute(target) || path.normalize(target) !== target) fail("noncanonical path");
  let current = path.parse(target).root;
  for (const part of target.slice(current.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    let stat;
    try { stat = fs.lstatSync(current); } catch (error) {
      if (allowMissing && error.code === "ENOENT") continue;
      throw error;
    }
    if (stat.isSymbolicLink() || !stat.isDirectory()) fail("symlink or non-directory ancestor");
  }
}

export function verifyMount(mountPoint, uuid) {
  canonicalDirectory(mountPoint);
  const device = fs.statSync(`/dev/disk/by-uuid/${uuid}`);
  const mounted = fs.statSync(mountPoint);
  if (!device.isBlockDevice() || device.rdev !== mounted.dev || fs.statSync(path.dirname(mountPoint)).dev === mounted.dev)
    fail("DATA UUID/device is not mounted at the configured mount point");
  return mounted.dev;
}

function verifyNamespace(map, probeDevice) {
  if (map.schema !== 1 || !/^[a-f0-9-]{36}$/i.test(map.uuid || "")) fail("invalid local mapping");
  canonicalDirectory(map.mountPoint);
  if (map.outputRoot !== path.join(map.mountPoint, "ProjectOutputs/light-novel/playwright")) fail("foreign namespace");
  canonicalDirectory(map.outputRoot);
  const dev = probeDevice(map.mountPoint, map.uuid);
  for (const target of [path.join(map.mountPoint, "ProjectOutputs"), path.dirname(map.outputRoot), map.outputRoot]) {
    const st = fs.statSync(target);
    if (st.uid !== process.getuid() || st.dev !== dev || (st.mode & 0o002)) fail("namespace ownership/device mismatch");
  }
  return dev;
}

export function explicitOutput(argv) {
  const resolve = value => {
    if (!value) fail("missing --output value");
    if (path.isAbsolute(value) && path.normalize(value) !== value) fail("noncanonical --output path");
    return path.resolve(value);
  };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--output=")) return resolve(argv[i].slice(9));
    if (argv[i] === "--output") {
      if (!argv[i + 1] || argv[i + 1].startsWith("--")) fail("missing --output value");
      return resolve(argv[i + 1]);
    }
  }
  return undefined;
}

function processStart(pid) {
  const text = fs.readFileSync(`/proc/${pid}/stat`, "utf8");
  return text.slice(text.lastIndexOf(")") + 2).split(" ")[19];
}

function isInvocationAncestor(pid, start) {
  if (!Number.isInteger(pid) || pid < 1 || processStart(pid) !== start) return false;
  let current = process.pid;
  while (current > 1) {
    if (current === pid) return true;
    const text = fs.readFileSync(`/proc/${current}/stat`, "utf8");
    current = Number(text.slice(text.lastIndexOf(")") + 2).split(" ")[1]);
  }
  return false;
}

export function resolvePlaywrightOutput({ repoRoot, argv = process.argv, env = process.env,
  homeDir = os.userInfo().homedir, probeDevice = verifyMount } = {}) {
  const mapPath = path.join(repoRoot, "config/linux.outputs.local.json");
  const registered = repoRoot === path.join(homeDir, "Projects/light-novel");
  const chosen = explicitOutput(argv);
  if (!fs.existsSync(mapPath)) {
    if (registered) fail("registered local checkout requires config/linux.outputs.local.json");
    return { outputDir: chosen || "artifacts/playwright", metadata: undefined };
  }
  if (fs.lstatSync(mapPath).isSymbolicLink()) fail("mapping must not be a symlink");
  canonicalDirectory(path.dirname(mapPath));
  const map = JSON.parse(fs.readFileSync(mapPath, "utf8"));
  if (map.repoRoot !== repoRoot) fail("mapping belongs to another checkout");
  const dev = verifyNamespace(map, probeDevice);
  // Explicit CLI paths retain Playwright's priority. Archive and foreign DATA
  // paths are never eligible for its recursive output cleanup.
  if (chosen && chosen !== map.mountPoint && !chosen.startsWith(map.mountPoint + path.sep))
    return { outputDir: chosen, metadata: undefined };
  if (chosen && !chosen.startsWith(path.join(map.outputRoot, "runs") + path.sep)) fail("explicit DATA output is outside runs");
  if (argv.includes("--list")) return { outputDir: chosen || path.join(map.outputRoot, "runs/list-only/output"), metadata: undefined };
  if (env[contextKey]) {
    const context = JSON.parse(env[contextKey]);
    if (context.repoRoot !== repoRoot || context.dev !== dev || !isInvocationAncestor(context.pid, context.start)) fail("foreign invocation context");
    if (chosen && chosen !== context.outputDir) fail("CLI/context mismatch");
    canonicalDirectory(context.runRoot);
    if (!context.runRoot.startsWith(path.join(map.outputRoot, "runs") + path.sep) ||
      context.outputDir !== path.join(context.runRoot, "output")) fail("context escapes runs");
    const markerPath = path.join(context.runRoot, markerName);
    const markerStat = fs.lstatSync(markerPath);
    if (!markerStat.isFile() || markerStat.uid !== process.getuid() || markerStat.dev !== dev) fail("foreign owner marker");
    const marker = JSON.parse(fs.readFileSync(markerPath, "utf8"));
    if (JSON.stringify(marker) !== JSON.stringify(context)) fail("foreign run owner");
    const st = fs.statSync(context.runRoot);
    if (st.dev !== dev || st.uid !== process.getuid() || st.ino !== context.ino) fail("run replaced");
    return { outputDir: context.outputDir, metadata: { mapPath, ...context } };
  }
  const runs = path.join(map.outputRoot, "runs");
  canonicalDirectory(runs, { allowMissing: true });
  if (!fs.existsSync(runs)) fs.mkdirSync(runs, { mode: 0o700 });
  if (fs.statSync(runs).uid !== process.getuid() || fs.statSync(runs).dev !== dev) fail("foreign runs parent");
  const runRoot = chosen ? path.dirname(chosen) : path.join(runs, randomUUID());
  if (chosen && (chosen !== path.join(runRoot, "output") || path.dirname(runRoot) !== runs)) fail("explicit DATA output must be runs/<new-id>/output");
  canonicalDirectory(runRoot, { allowMissing: true });
  // Exclusive creation prevents clearing a prior run or unknown content.
  fs.mkdirSync(runRoot, { mode: 0o700 });
  const context = { repoRoot, pid: process.pid, start: processStart(process.pid), dev,
    runRoot, outputDir: path.join(runRoot, "output"), ino: fs.statSync(runRoot).ino };
  fs.writeFileSync(path.join(runRoot, markerName), JSON.stringify(context), { flag: "wx", mode: 0o600 });
  env[contextKey] = JSON.stringify(context);
  return { outputDir: context.outputDir, metadata: { mapPath, ...context } };
}

export function verifyPostflight(metadata, probeDevice = verifyMount) {
  if (!metadata) return;
  const map = JSON.parse(fs.readFileSync(metadata.mapPath, "utf8"));
  const dev = verifyNamespace(map, probeDevice);
  canonicalDirectory(metadata.outputDir);
  const outputStat = fs.statSync(metadata.outputDir);
  if (outputStat.dev !== dev || outputStat.uid !== process.getuid()) fail("postflight output/device changed");
  const st = fs.statSync(metadata.runRoot);
  if (dev !== metadata.dev || st.dev !== dev || st.ino !== metadata.ino || st.uid !== process.getuid()) fail("postflight run/device changed");
  const { mapPath, ...context } = metadata;
  if (fs.readFileSync(path.join(metadata.runRoot, markerName), "utf8") !== JSON.stringify(context)) fail("postflight owner changed");
}

// Playwright invokes this after workers finish, before it reports success.
export default async function outputStorageTeardown(config) {
  verifyPostflight(config.metadata.lightNovelOutputStorage);
}
