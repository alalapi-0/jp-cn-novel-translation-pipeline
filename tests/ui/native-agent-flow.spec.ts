import {test,expect} from '@playwright/test';
import fs from 'node:fs';

for (const width of [1280,390]) {
 test(`verified native provenance labels ${width}`, async ({page}, info) => {
  await page.setViewportSize({width,height:844}); await page.emulateMedia({reducedMotion:'reduce'});
  let verified=true, producer='native_agent_quota'; const errors:string[]=[], consoleErrors:string[]=[], network:any[]=[];
  page.on('pageerror', e=>errors.push(e.message));
  page.on('console', m=>{if(['error','warning'].includes(m.type()))consoleErrors.push(m.text());});
  page.on('response', r=>network.push({path:new URL(r.url()).pathname,status:r.status()}));
  await page.route('**/api/projects/demo-jp-cn/workbench-data', async route=>{
   const response=await route.fetch(); const payload=await response.json();
   payload.segments=payload.segments.map((s:any)=>({...s,generated_by:producer,native_provenance:{status:verified?'verified':'unverified',execution_mode:verified?'agent_quota_translation':null}}));
   await route.fulfill({response,json:payload});
  });
  await page.goto('/review.html?project=demo-jp-cn');
  await expect(page.locator('.review-reading')).toBeVisible();
  await page.screenshot({path:info.outputPath('native-provenance-render.png'),fullPage:true});
  await expect(page.locator('.review-reading')).toContainText('译文（本机 Agent 额度）');
  await expect(page.locator('.review-meta')).toContainText('本机 Agent 额度');
  verified=false; await page.reload();
  await expect(page.locator('.review-reading')).toContainText('译文（来源未核验）');
  await expect(page.locator('.review-meta')).toContainText('来源未核验');
  producer='imported_candidate';verified=true;await page.reload();
  await expect(page.locator('.review-reading')).toContainText('译文（导入候选）');
  await expect(page.locator('.review-meta')).not.toContainText('本机 Agent 额度');
  producer='mock';await page.reload();
  await expect(page.locator('.review-meta')).toContainText('mock');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  expect(errors).toEqual([]);expect(consoleErrors).toEqual([]);expect(network.filter(r=>r.status>=400)).toEqual([]);
  fs.writeFileSync(info.outputPath('native-provenance-evidence.json'),JSON.stringify({width,errors,consoleErrors,network,classification:'Explicit intercepted synthetic server provenance for UI rendering only; no native model or approval',browser:page.context().browser()?.version()},null,2));
 });
}

// Actual browser/API refusal evidence. No real login or injected native approval.
for(const width of [1280,390]) {
 test(`native quota admission refusal preserves source and candidate ${width}`,async({page,request},info)=>{
  await page.setViewportSize({width,height:844});await page.emulateMedia({reducedMotion:'reduce'});
  const errors:string[]=[];const network:any[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>network.push({path:new URL(r.url()).pathname,status:r.status()}));
  const pid=`native-refusal-${width}-${Date.now()}`;
  await page.goto('/index.html');await page.locator('#long-project-id').fill(pid);
  await page.locator('#long-source-files').setInputFiles({name:'001-synthetic.md',mimeType:'text/markdown',buffer:Buffer.from('# 合成\n\n雨が降っていた。\n\n彼は扉を閉めた。')});
  await page.getByRole('button',{name:'导入完整源章节'}).click();await page.locator('#long-import-result a').click();
  await expect(page.locator('#version-summary')).toContainText(`${pid} · 1 章 / 2 段`);
  const initial=await(await request.get(`/api/projects/${pid}/native-agent-status`)).json();
  expect(initial.admission.blocked).toBe(true); // preseeded negative fixture; no native process
  await expect(page.locator('#native-admission-status')).toContainText('原生准入记录尚未解决');
  await expect(page.locator('#native-review')).toBeDisabled();
  const before=await(await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  await page.screenshot({path:info.outputPath('native-before.png'),fullPage:true});
  const after=await(await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  expect(after.manifest_sha256).toBe(before.manifest_sha256);expect(after.can_select).toBe(false);expect(after.human_approved_final).toBe(false);
  await expect(page.locator('#native-generate')).toBeDisabled();await expect(page.locator('#native-review')).toBeDisabled();
  const status=await(await request.get(`/api/projects/${pid}/native-agent-status`)).json();
  const bypass=await request.post(`/api/projects/${pid}/native-agent-job`,{data:{action:'generate',request_id:'new-id-cannot-bypass',expected_manifest_sha256:before.manifest_sha256},headers:{Origin:new URL(page.url()).origin}});
  expect(bypass.status()).toBe(503);
  const unchanged=await(await request.get(`/api/projects/${pid}/native-agent-status`)).json();expect(unchanged.admission.attempts).toBe(status.admission.attempts);
  await page.reload();await expect(page.locator('#version-summary')).toContainText(`${pid} · 1 章 / 2 段`);
  await expect(page.locator('#native-admission-status')).toContainText('原生准入记录尚未解决');
  await expect(page.locator('#native-generate')).toBeDisabled();
  const cancelForged=await request.post(`/api/projects/${pid}/native-agent-cancel`,{data:{request_id:'wrong-request'},headers:{Origin:new URL(page.url()).origin}});expect(cancelForged.status()).toBe(400);
  const cancelCross=await request.post(`/api/projects/${pid}/native-agent-cancel`,{data:{request_id:'wrong-request'},headers:{Origin:'https://untrusted.invalid'}});expect(cancelCross.status()).toBe(403);
  const forgery=await request.post(`/api/projects/${pid}/native-agent-job`,{data:{action:'generate',request_id:'forged',expected_manifest_sha256:before.manifest_sha256,actor_type:'agent'},headers:{Origin:new URL(page.url()).origin}});
  expect(forgery.status()).toBe(400);
  const crossOrigin=await request.post(`/api/projects/${pid}/native-agent-job`,{data:{action:'generate',request_id:'cross-origin',expected_manifest_sha256:before.manifest_sha256},headers:{Origin:'https://untrusted.invalid'}});
  expect(crossOrigin.status()).toBe(403);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);expect(errors).toEqual([]);
  await page.screenshot({path:info.outputPath('native-after.png'),fullPage:true});
  fs.writeFileSync(info.outputPath('native-refusal-evidence.json'),JSON.stringify({browser:page.context().browser()?.version(),network,errors,scope:'private actual browser/API refusal of explicitly preseeded synthetic failed admission; no native start/generation/approval',manifest_preserved:true,loaded_state_verified_after_reload:true},null,2));
 });
}
