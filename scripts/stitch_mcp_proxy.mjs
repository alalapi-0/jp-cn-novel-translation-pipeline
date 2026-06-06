#!/usr/bin/env node
/**
 * Local stdio MCP proxy for Google Stitch.
 * Reads STITCH_API_KEY from environment only; never prints the key.
 */
import { StitchProxy } from "@google/stitch-sdk";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const apiKey = process.env.STITCH_API_KEY;

if (!apiKey || !apiKey.trim()) {
  console.error(
    "STITCH_API_KEY is not set. Export it in your shell or Cursor MCP env before starting stitch."
  );
  process.exit(1);
}

const proxy = new StitchProxy({ apiKey: apiKey.trim() });
const transport = new StdioServerTransport();

await proxy.start(transport);
