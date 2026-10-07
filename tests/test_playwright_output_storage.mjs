import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { resolvePlaywrightOutput, verifyPostflight } from "../scripts/playwright_output_storage.mjs";

function fixture(t) {
  const homeDir = fs.mkdtempSync(path.join(os.tmpdir(), "light-novel-output-"));
  t.after(() => fs.rmSync(homeDir, { recursive: true, force: true }));
  const repoRoot = path.join(homeDir, "Projects/light-novel");
  const mountPoint = path.join(homeDir, "data");
  const outputRoot = path.join(mountPoint, "ProjectOutputs/light-novel/playwright");
  fs.mkdirSync(path.join(repoRoot, "config"), { recursive: true });
  fs.mkdirSync(outputRoot, { recursive: true });
  const mapPath = path.join(repoRoot, "config/linux.outputs.local.json");
  const map = { schema: 1, repoRoot, mountPoint, uuid: "98a6a740-bf5c-41b5-90fe-fd8e78fa5f55", outputRoot };
  const saveMap = () => fs.writeFileSync(mapPath, JSON.stringify(map));
  saveMap();
  const probeDevice = () => fs.statSync(mountPoint).dev;
  const options = { repoRoot, homeDir, probeDevice, argv: [], env: {} };
  return { ...options, options, map, mapPath, saveMap, outputRoot, homeDir };
}

test("same invocation shares a fresh run; later invocation cannot clear it", t => {
  const f = fixture(t);
  const first = resolvePlaywrightOutput(f.options);
  fs.mkdirSync(first.outputDir);
  fs.writeFileSync(path.join(first.outputDir, "original.png"), "preserved");
  assert.equal(resolvePlaywrightOutput(f.options).outputDir, first.outputDir);
  verifyPostflight(first.metadata, f.probeDevice);
  const next = resolvePlaywrightOutput({ ...f.options, env: {} });
  assert.notEqual(next.outputDir, first.outputDir);
  assert.equal(fs.readFileSync(path.join(first.outputDir, "original.png"), "utf8"), "preserved");
});

test("wrong UUID/device fails before a runs directory is created, including CI", t => {
  const f = fixture(t);
  assert.throws(() => resolvePlaywrightOutput({ ...f.options, env: { CI: "1" }, probeDevice: () => { throw Error("UUID mismatch"); } }), /UUID mismatch/);
  assert.equal(fs.existsSync(path.join(f.outputRoot, "runs")), false);
});

test("registered checkout missing local map fails even in CI", t => {
  const f = fixture(t); fs.unlinkSync(f.mapPath);
  assert.throws(() => resolvePlaywrightOutput({ ...f.options, env: { CI: "1" } }), /requires config/);
});

test("portable and CI clones without a map preserve original output and explicit CLI priority", t => {
  const f = fixture(t); fs.unlinkSync(f.mapPath);
  const repoRoot = path.join(f.homeDir, "portable-clone");
  assert.equal(resolvePlaywrightOutput({ ...f.options, repoRoot, env: { CI: "1" } }).outputDir, "artifacts/playwright");
  const chosen = path.join(f.homeDir, "chosen");
  assert.equal(resolvePlaywrightOutput({ ...f.options, repoRoot, argv: ["--output", chosen] }).outputDir, chosen);
});

test("foreign namespace, canonical escape and symlink ancestors fail before writes", t => {
  const f = fixture(t);
  f.map.outputRoot += "/../other"; f.saveMap();
  assert.throws(() => resolvePlaywrightOutput(f.options), /foreign namespace/);
  assert.throws(() => resolvePlaywrightOutput({ ...f.options, argv: ["--output=/data/ProjectOutputs/light-novel/playwright/runs/a/../b/output"] }), /noncanonical --output/);
  f.map.outputRoot = f.outputRoot; f.saveMap();
  const moved = f.outputRoot + "-original";
  fs.renameSync(f.outputRoot, moved); fs.symlinkSync(moved, f.outputRoot);
  assert.throws(() => resolvePlaywrightOutput(f.options), /symlink/);
  assert.equal(fs.existsSync(path.join(moved, "runs")), false);
});

test("explicit DATA output cannot select archive, foreign namespace, or existing content", t => {
  const f = fixture(t);
  for (const chosen of [path.join(f.outputRoot, "archive/imported"), path.join(f.map.mountPoint, "unknown/output")])
    assert.throws(() => resolvePlaywrightOutput({ ...f.options, argv: [`--output=${chosen}`] }), /outside runs/);
  const chosen = path.join(f.outputRoot, "runs/occupied/output");
  fs.mkdirSync(chosen, { recursive: true }); fs.writeFileSync(path.join(chosen, "keep"), "unique");
  assert.throws(() => resolvePlaywrightOutput({ ...f.options, argv: [`--output=${chosen}`] }), /EEXIST/);
  assert.equal(fs.readFileSync(path.join(chosen, "keep"), "utf8"), "unique");
});

test("new explicit DATA output preserves its selected path; external override is unchanged", t => {
  const f = fixture(t);
  const chosen = path.join(f.outputRoot, "runs/explicit-new/output");
  assert.equal(resolvePlaywrightOutput({ ...f.options, argv: ["--output", chosen] }).outputDir, chosen);
  const outside = path.join(f.homeDir, "external-choice");
  assert.equal(resolvePlaywrightOutput({ ...f.options, argv: [`--output=${outside}`], env: {} }).outputDir, outside);
  assert.equal(fs.existsSync(outside), false);
});

test("list-only creates no directories", t => {
  const f = fixture(t);
  resolvePlaywrightOutput({ ...f.options, argv: ["--list"] });
  assert.equal(fs.existsSync(path.join(f.outputRoot, "runs")), false);
});

test("foreign invocation context and owner-marker changes are refused", t => {
  const f = fixture(t); resolvePlaywrightOutput(f.options);
  const context = JSON.parse(f.options.env.LIGHT_NOVEL_PLAYWRIGHT_OUTPUT_CONTEXT);
  context.start = "wrong";
  assert.throws(() => resolvePlaywrightOutput({ ...f.options, env: { LIGHT_NOVEL_PLAYWRIGHT_OUTPUT_CONTEXT: JSON.stringify(context) } }), /foreign invocation/);
  fs.writeFileSync(path.join(context.runRoot, ".playwright-output-owner.json"), "{}");
  assert.throws(() => resolvePlaywrightOutput(f.options), /foreign run owner/);
});

test("postflight rejects device change and directory replacement", t => {
  const f = fixture(t); const run = resolvePlaywrightOutput(f.options); fs.mkdirSync(run.outputDir);
  assert.throws(() => verifyPostflight(run.metadata, () => f.probeDevice() + 1), /namespace ownership\/device mismatch/);
  fs.renameSync(run.metadata.runRoot, run.metadata.runRoot + "-old");
  fs.mkdirSync(run.outputDir, { recursive: true });
  assert.throws(() => verifyPostflight(run.metadata, f.probeDevice), /postflight run\/device changed/);
});
