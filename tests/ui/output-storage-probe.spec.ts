import { test, expect } from "@playwright/test";

test("synthetic storage calibration writes explicit PNG and retry trace", async ({ page }, testInfo) => {
  test.skip(process.env.LIGHT_NOVEL_STORAGE_PROBE !== "1", "opt-in storage calibration only");
  await page.setContent("<main><h1>Storage calibration</h1><p>Synthetic fixture.</p></main>");
  await page.screenshot({ path: testInfo.outputPath("explicit-storage.png") });
  expect(testInfo.retry, "intentional first-attempt failure exercises automatic screenshot and retry trace").toBe(1);
});
