#!/usr/bin/env node
/**
 * Lightweight checker for Stitch MCP integration.
 * Does not print secret values.
 */

const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..");
const MCP_PATH = path.join(REPO_ROOT, ".cursor", "mcp.json");
const ENV_EXAMPLE_PATH = path.join(REPO_ROOT, ".env.example");
const GITIGNORE_PATH = path.join(REPO_ROOT, ".gitignore");
const PROXY_PATH = path.join(REPO_ROOT, "scripts", "stitch_mcp_proxy.mjs");
const DESIGN_STITCH_ROOT = path.join(REPO_ROOT, "docs", "design", "stitch");

const REQUIRED_DESIGN_DOCS = [
  "README.md",
  "STITCH_MCP_SETUP.md",
  "STITCH_WORKFLOW.md",
  "UI_TASKS.md",
  "PROMPT_TEMPLATES.md",
  "EXPORT_GUIDE.md",
];

const REQUIRED_DESIGN_DIRS = [
  "exports",
  "screenshots",
  "prompts",
  "reviews",
];

const SUSPECT_KEY_PATTERNS = [
  /AIza[0-9A-Za-z_-]{20,}/,
  /AQ\.[0-9A-Za-z_-]{10,}/,
  /sk-[A-Za-z0-9]{20,}/,
  /ghp_[A-Za-z0-9_]+/,
];

function looksLikeHardcodedSecret(value) {
  if (typeof value !== "string") return false;
  if (value.includes("${env:") || value.startsWith("${")) return false;
  const trimmed = value.trim();
  if (!trimmed || trimmed === "your_stitch_api_key_here") return false;
  return SUSPECT_KEY_PATTERNS.some((p) => p.test(trimmed));
}

function collectStrings(obj) {
  if (typeof obj === "string") return [obj];
  if (Array.isArray(obj)) return obj.flatMap(collectStrings);
  if (obj && typeof obj === "object") {
    return Object.values(obj).flatMap(collectStrings);
  }
  return [];
}

function main() {
  const errors = [];
  const warnings = [];
  const summary = [];

  if (!fs.existsSync(MCP_PATH)) {
    errors.push(`Missing MCP config: ${path.relative(REPO_ROOT, MCP_PATH)}`);
  } else {
    let data;
    try {
      data = JSON.parse(fs.readFileSync(MCP_PATH, "utf8"));
    } catch (err) {
      errors.push(`Invalid JSON in mcp.json: ${err.message}`);
      data = null;
    }

    if (data) {
      const servers = data.mcpServers || {};
      if (!servers.stitch) {
        errors.push("mcpServers.stitch is not configured");
      } else {
        const stitch = servers.stitch;
        summary.push("stitch server: present");

        if (stitch.url && stitch.headers) {
          summary.push("stitch transport: remote HTTP");
          warnings.push(
            "Remote HTTP stitch config detected; prefer local proxy if header env interpolation fails in Cursor"
          );
        } else if (stitch.command) {
          summary.push(`stitch transport: stdio (${stitch.command})`);
        } else {
          warnings.push("stitch server has no recognizable transport (command or url)");
        }

        const env = stitch.env;
        if (env && typeof env === "object") {
          for (const [key, val] of Object.entries(env)) {
            if (looksLikeHardcodedSecret(val)) {
              errors.push(
                `stitch env.${key} looks like a hardcoded API key; use \${env:STITCH_API_KEY}`
              );
            }
          }
        }

        const headers = stitch.headers;
        if (headers && typeof headers === "object") {
          for (const [key, val] of Object.entries(headers)) {
            if (looksLikeHardcodedSecret(val)) {
              errors.push(
                `stitch headers.${key} looks like a hardcoded API key; use \${env:STITCH_API_KEY} or local proxy`
              );
            }
          }
        }

        for (const s of collectStrings(stitch)) {
          if (looksLikeHardcodedSecret(s)) {
            errors.push("stitch config contains a value that looks like a hardcoded API key");
            break;
          }
        }
      }
    }
  }

  if (!fs.existsSync(PROXY_PATH)) {
    warnings.push(`Local proxy script missing: ${path.relative(REPO_ROOT, PROXY_PATH)}`);
  } else {
    summary.push("local proxy script: present");
  }

  if (!fs.existsSync(ENV_EXAMPLE_PATH)) {
    errors.push("Missing .env.example");
  } else {
    const envExample = fs.readFileSync(ENV_EXAMPLE_PATH, "utf8");
    if (!envExample.includes("STITCH_API_KEY")) {
      errors.push(".env.example does not document STITCH_API_KEY");
    } else {
      summary.push(".env.example: STITCH_API_KEY documented");
    }
  }

  if (!fs.existsSync(GITIGNORE_PATH)) {
    errors.push("Missing .gitignore");
  } else {
    const gitignore = fs.readFileSync(GITIGNORE_PATH, "utf8");
    if (!/\.env\b/.test(gitignore)) {
      errors.push(".gitignore does not ignore .env");
    } else {
      summary.push(".gitignore: .env ignored");
    }
  }

  if (!fs.existsSync(DESIGN_STITCH_ROOT)) {
    errors.push("Missing docs/design/stitch/");
  } else {
    summary.push("docs/design/stitch/: present");
    for (const doc of REQUIRED_DESIGN_DOCS) {
      const docPath = path.join(DESIGN_STITCH_ROOT, doc);
      if (!fs.existsSync(docPath)) {
        errors.push(`Missing design doc: docs/design/stitch/${doc}`);
      }
    }
    for (const dir of REQUIRED_DESIGN_DIRS) {
      const dirPath = path.join(DESIGN_STITCH_ROOT, dir);
      if (!fs.existsSync(dirPath)) {
        errors.push(`Missing design directory: docs/design/stitch/${dir}/`);
      }
    }
  }

  const designMd = path.join(REPO_ROOT, "docs", "design", "DESIGN.md");
  if (!fs.existsSync(designMd)) {
    errors.push("Missing docs/design/DESIGN.md");
  }

  printReport(errors, warnings, summary);
  process.exit(errors.length > 0 ? 1 : 0);
}

function printReport(errors, warnings, summary) {
  console.log("Stitch config check");
  console.log(`  path: ${path.relative(REPO_ROOT, MCP_PATH)}`);
  console.log("  summary:");
  for (const line of summary) {
    console.log(`    ${line}`);
  }
  if (warnings.length) {
    console.log("  warnings:");
    for (const w of warnings) {
      console.log(`    - ${w}`);
    }
  }
  if (errors.length) {
    console.log("  errors:");
    for (const e of errors) {
      console.log(`    - ${e}`);
    }
  }
  console.log(`  result: ${errors.length ? "FAIL" : "PASS"}`);
}

main();
