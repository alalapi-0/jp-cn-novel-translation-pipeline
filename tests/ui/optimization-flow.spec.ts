import { test, expect } from '@playwright/test';

for (const viewport of [{width:1280,height:900},{width:390,height:844}]) {
  test(`optimization entry baseline ${viewport.width}`, async ({page}, info) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({reducedMotion:'reduce'});
    const errors:string[]=[];const messages:string[]=[];const exchanges:any[]=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push(m.text());});
    page.on('response',r=>exchanges.push({path:new URL(r.url()).pathname,status:r.status()}));
    for(const route of ['index','review','export']) {
      await page.goto(`/${route}.html`);
      await page.waitForLoadState('networkidle');
      await page.screenshot({path:info.outputPath(`${route}-${viewport.width}.png`),fullPage:true});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    }
    fs.writeFileSync(info.outputPath('entry-observations.json'),JSON.stringify({viewport,errors,messages,exchanges,browserVersion:page.context().browser()?.version()},null,2));
    await info.attach('entry-observations',{path:info.outputPath('entry-observations.json'),contentType:'application/json'});
    expect(messages).toEqual([]);expect(exchanges.filter(r=>r.status>=400)).toEqual([]);
    expect(errors).toEqual([]);
  });
}

import fs from 'node:fs';
import {trustedSyntheticAgentSetup} from './trusted-native-fixture';

for (const viewport of [{width:1280,height:900},{width:390,height:844}]) {
 test(`R189 honest mutation outcomes ${viewport.width}`,async({page,request})=>{
  await page.setViewportSize(viewport);await page.emulateMedia({reducedMotion:'reduce'});
  const pageErrors:string[]=[];const consoleErrors:string[]=[];const exchanges:any[]=[];
  page.on('pageerror',e=>pageErrors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  page.on('response',r=>exchanges.push({path:new URL(r.url()).pathname,method:r.request().method(),status:r.status()}));
  const before={error:'review_state_unavailable',message:'工作区或审核状态暂不可用，本次未写入。',effect_applied:false,mutation_committed:false};
  const after={effect_applied:true,mutation_committed:true,selection_status_available:false,
   warning_code:'review_state_unavailable_after_effect',warning:'操作已完成，但审核状态暂不可用。当前页面仍为操作前内容，请刷新后核对；请勿重复提交。'};
  const pid=`pw-r189-outcome-${viewport.width}-${Date.now()}`;
  await page.goto('/index.html');
  await page.locator('#long-project-id').fill(pid);await page.locator('#long-project-name').fill('合成导入结果');
  await page.locator('#long-source-files').setInputFiles({name:'001-synthetic.md',mimeType:'text/markdown',buffer:Buffer.from('# 合成\n\n测试。')});
  let mode='before';let sourcePosts=0;let reviewMutations=0;let protectedMutations=0;let confirmations=0;
  page.on('dialog',dialog=>{confirmations++;dialog.accept();});
  page.on('request',req=>{
   if(req.url().endsWith('/review-state') && req.method()==='PATCH')reviewMutations++;
   if(req.method()!=='GET' && /\/(review-state|candidate-import|candidate-restore|select-version|native-agent-job|canonical-export)$/.test(new URL(req.url()).pathname))protectedMutations++;
  });
  await page.route('**/api/source-import',async route=>{
   sourcePosts++;
   if(mode==='before')await route.fulfill({status:503,json:before});
   else {const actual=await route.fetch();expect(actual.ok()).toBeTruthy();await route.fulfill({response:actual,json:{...after,project_id:pid}});}
  });
  await page.locator('#long-import-form button').click();
  await expect(page.locator('#long-import-result')).toContainText('工作区或审核状态暂不可用，本次未写入');
  mode='after';await page.locator('#long-import-form button').click();
  await expect(page.locator('#long-import-result')).toContainText('操作已完成，但审核状态暂不可用');
  await expect(page.locator('#long-import-form button')).toBeDisabled();
  await page.waitForTimeout(200);expect(sourcePosts).toBe(2);
  fs.mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:`artifacts/r189-source-outcome-${viewport.width}.png`,fullPage:true});
  await page.unroute('**/api/source-import');

  await page.route('**/canonical-selection',async route=>{
   const actual=await route.fetch();const value=await actual.json();value.native_status.admission.blocked=false;
   await route.fulfill({response:actual,json:value});
  });
  await page.goto(`/review.html?project=${pid}`);
  await expect(page.locator('#native-generate')).toBeEnabled();
  let nativePosts=0;
  await page.route('**/native-agent-job',async route=>{nativePosts++;await route.fulfill({status:503,json:{
   error:'native_request_history_unknown',message:'本次调用未执行；无法安全确认同一请求此前是否已完成，请勿自动重试，待安全回执能力具备后核查。',
   invocation_effect_applied:false,request_effect_status:'unknown',idempotent_replay:'unknown',selection_status_available:false,retry_operation:false}});});
  await page.locator('#native-generate').click();
  await expect(page.locator('#version-action-result')).toContainText('本次调用未执行；无法安全确认同一请求此前是否已完成');
  await expect(page.locator('#review-snapshot-notice')).toContainText('审核状态暂不可用');
  await page.waitForTimeout(200);expect(nativePosts).toBe(1);
  await page.unroute('**/native-agent-job');await page.unroute('**/canonical-selection');

  const project=`pw-r189-recovery-${viewport.width}-${Date.now()}`;
  let response=await request.post('/api/source-import',{data:{project_id:project,name:'合成恢复',language_direction:'JP_TO_CN',
   chapters:[{filename:'001-synthetic.md',text:'# 合成\n\n测试。'}]}});
  expect(response.ok()).toBeTruthy();let state=await response.json();
  for (const text of ['候选一。','候选二。']) {
   response=await request.post(`/api/projects/${project}/candidate-import`,{data:{expected_manifest_sha256:state.manifest_sha256,
    source_inventory_sha256:state.source_inventory_sha256,candidates:state.segments.map((r:any)=>({segment_id:r.segment_id,target_text:text}))}});
   expect(response.ok()).toBeTruthy();state=await response.json();
  }
  await page.goto(`/review.html?project=${project}`);
  await expect(page.locator('#version-summary')).toContainText(project);
  await expect(page.locator('#version-candidate-file')).toBeEnabled();
  const packet={source_inventory_sha256:state.source_inventory_sha256,candidates:state.segments.map((r:any)=>({segment_id:r.segment_id,target_text:'合成新候选。'}))};
  let candidatePosts=0;mode='before';
  await page.route('**/candidate-import',async route=>{candidatePosts++;
   if(mode==='before')await route.fulfill({status:503,json:before});
   else {const actual=await route.fetch();expect(actual.ok()).toBeTruthy();await route.fulfill({response:actual,json:{...after,project_id:project}});}
  });
  const file={name:'candidate.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(packet))};
  await page.locator('#version-candidate-file').setInputFiles(file);
  await expect(page.locator('#version-action-result')).toContainText('工作区或审核状态暂不可用，本次未写入');
  await expect(page.locator('#version-candidate-file')).toBeDisabled();
  await page.reload();await expect(page.locator('#version-summary')).toContainText(project);
  mode='after';await page.locator('#version-candidate-file').setInputFiles(file);
  await expect(page.locator('#version-action-result')).toContainText('操作已完成，但审核状态暂不可用');
  await expect(page.locator('#version-candidate-file')).toBeDisabled();
  await expect(page.locator('#review-snapshot-notice')).toContainText('操作前的失效快照');
  await expect(page.locator('#review-root')).toContainText('候选二。');
  const approval=page.locator('#review-root button[data-action="approve"]');
  await expect(approval).toBeDisabled();
  const beforeProtected=protectedMutations;
  await approval.evaluate((element:HTMLButtonElement)=>{element.disabled=false;element.click();element.disabled=true;});
  await page.locator('body').click({position:{x:1,y:1}});await page.keyboard.press('a');
  for(const id of ['version-restore','version-select','native-generate','native-review'])
   await page.locator(`#${id}`).evaluate((element:HTMLButtonElement)=>{element.disabled=false;element.click();element.disabled=true;});
  await page.locator('#version-candidate-file').evaluate((element:HTMLInputElement)=>element.dispatchEvent(new Event('change',{bubbles:true})));
  expect(confirmations).toBe(0);expect(reviewMutations).toBe(0);expect(protectedMutations).toBe(beforeProtected);
  await page.waitForTimeout(200);expect(candidatePosts).toBe(2);
  await page.screenshot({path:`artifacts/r189-candidate-outcome-${viewport.width}.png`,fullPage:true});
  await page.unroute('**/candidate-import');
  await page.route('**/review-state',async route=>{
   if(route.request().method()==='GET')await route.fulfill({status:503,json:before});else await route.continue();
  });
  await page.reload();
  await expect(page.locator('#review-snapshot-notice')).toContainText('审核状态暂不可用');
  await expect(page.locator('#review-root button[data-action="approve"]')).toBeDisabled();
  await page.waitForFunction(()=>typeof (document.querySelector('#version-refresh') as HTMLButtonElement).onclick==='function');
  let load=page.waitForEvent('load');await page.locator('#version-refresh').click();await load;
  await expect(page.locator('#review-snapshot-notice')).toContainText('审核状态暂不可用');
  await expect(page.locator('#review-root button[data-action="approve"]')).toBeDisabled();
  await page.waitForFunction(()=>typeof (document.querySelector('#version-refresh') as HTMLButtonElement).onclick==='function');
  await page.unroute('**/review-state');
  load=page.waitForEvent('load');await page.locator('#version-refresh').click();await load;
  await expect(page.locator('#review-snapshot-notice')).toHaveCount(0);
  await expect(page.locator('#review-root')).toContainText('合成新候选。');
  await expect(page.locator('#review-root button[data-action="approve"]')).toBeEnabled();

  await expect(page.locator('#version-restore')).toBeEnabled();
  let restorePosts=0;mode='before';
  await page.route('**/candidate-restore',async route=>{restorePosts++;
   if(mode==='before')await route.fulfill({status:503,json:before});
   else {const actual=await route.fetch();expect(actual.ok()).toBeTruthy();await route.fulfill({response:actual,json:after});}
  });
  await page.locator('#version-restore').click();
  await expect(page.locator('#version-action-result')).toContainText('工作区或审核状态暂不可用，本次未写入');
  await page.reload();await expect(page.locator('#version-restore')).toBeEnabled();mode='after';
  await page.locator('#version-restore').click();
  await expect(page.locator('#version-action-result')).toContainText('操作已完成，但审核状态暂不可用');
  await expect(page.locator('#version-restore')).toBeDisabled();
  await expect(page.locator('#review-snapshot-notice')).toContainText('操作前的失效快照');
  await expect(page.locator('#review-root button[data-action="approve"]')).toBeDisabled();
  await page.waitForTimeout(200);expect(restorePosts).toBe(2);
  await page.screenshot({path:`artifacts/r189-restore-outcome-${viewport.width}.png`,fullPage:true});
  await page.unroute('**/candidate-restore');
  let selectionGets=0;let exportPosts=0;
  await page.route('**/canonical-selection',async route=>{
   selectionGets++;const actual=await route.fetch();const value=await actual.json();value.selected_current=true;
   await route.fulfill({response:actual,json:value});
  });
  await page.route('**/canonical-export',async route=>{exportPosts++;await route.fulfill({status:503,json:before});});
  await page.goto(`/export.html?project=${project}`);
  await expect(page.locator('#version-summary')).toContainText(project);
  await page.locator('#canonical-confirm').check();await expect(page.locator('#canonical-export')).toBeEnabled();
  const initialGets=selectionGets;
  await page.locator('#canonical-export').click();
  await expect(page.locator('#canonical-result')).toContainText('工作区或审核状态暂不可用，本次未写入');
  await expect(page.locator('#version-summary')).toContainText('当前版本信息未确认');
  await expect(page.locator('#canonical-export')).toBeDisabled();
  await page.locator('#canonical-export').evaluate((element:HTMLButtonElement)=>{element.disabled=false;element.click();element.disabled=true;});
  await page.waitForTimeout(200);expect(exportPosts).toBe(1);expect(selectionGets).toBe(initialGets);
  await page.screenshot({path:`artifacts/r189-export-unavailable-${viewport.width}.png`,fullPage:true});
  await page.locator('#version-refresh').click();
  await expect.poll(()=>selectionGets).toBe(initialGets+1);
  await expect(page.locator('#canonical-export')).toBeEnabled();
  await page.unroute('**/canonical-selection');await page.unroute('**/canonical-export');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter(message=>!message.includes('503 (Service Unavailable)'))).toEqual([]);
  fs.writeFileSync(`artifacts/r189-outcomes-${viewport.width}.json`,JSON.stringify({viewport,pageErrors,consoleErrors,exchanges,sourcePosts,candidatePosts,restorePosts,nativePosts,reviewMutations,protectedMutations,confirmations,selectionGets,exportPosts,
   classification:'synthetic browser; preflight responses intercepted, post-effect responses replaced after real synthetic writes; isolated Python tests cover backend failure semantics'},null,2));
 });
}

for(const viewport of [{width:1280,height:900},{width:390,height:844}]) {
 test(`candidate recovery confirmation undo stale and review identity ${viewport.width}`,async({page,request},info)=>{
  await page.setViewportSize(viewport);await page.emulateMedia({reducedMotion:'reduce'});
  const errors:string[]=[];const messages:string[]=[];const exchanges:any[]=[];const failures:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push(m.text());});
  page.on('response',r=>exchanges.push({path:new URL(r.url()).pathname,method:r.request().method(),status:r.status()}));
  page.on('requestfailed',r=>failures.push(r.failure()?.errorText||r.url()));
  const pid=`recovery-${viewport.width}-${Date.now()}`;
  const imported=await request.post('/api/source-import',{data:{project_id:pid,name:'合成恢复验证',language_direction:'JP_TO_CN',chapters:[{filename:'003-synthetic.md',text:'# 合成章\n\n甲。\n\n乙。'}]}});
  expect(imported.ok()).toBeTruthy();let state=await imported.json();
  await page.goto(`/review.html?project=${pid}`);await expect(page.locator('#version-restore')).toBeDisabled();
  const upload=async(targets:string[])=>{
    const response=await request.post(`/api/projects/${pid}/candidate-import`,{data:{expected_manifest_sha256:state.manifest_sha256,
      source_inventory_sha256:state.source_inventory_sha256,candidates:state.segments.map((r:any,i:number)=>({segment_id:r.segment_id,target_text:targets[i]}))}});
    expect(response.ok()).toBeTruthy();state=await response.json();
  };
  await upload(['恢复前候选甲。','保持乙。']);trustedSyntheticAgentSetup(pid);
  state=await (await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  await upload(['新候选甲。','保持乙。']);await page.reload();
  await expect(page.locator('.review-reading')).toContainText('新候选甲。');
  await expect(page.locator('#version-restore')).toBeEnabled();
  await expect(page.locator('#version-summary')).toContainText('当前 Agent/PSH 接受 1/2');
  const before=state.manifest_sha256;let confirmations=0;
  page.once('dialog',async dialog=>{expect(dialog.message()).toContain('需要重新审核');confirmations++;await dialog.dismiss();});
  await page.locator('#version-restore').click();
  expect((await (await request.get(`/api/projects/${pid}/canonical-selection`)).json()).manifest_sha256).toBe(before);
  expect(exchanges.filter(r=>r.path.endsWith('/candidate-restore'))).toHaveLength(0);
  await page.locator('#version-restore').focus();await expect(page.locator('#version-restore')).toBeFocused();
  page.once('dialog',async dialog=>{confirmations++;await dialog.accept();});
  const restoredResponse=page.waitForResponse(r=>r.url().endsWith('/candidate-restore')&&r.request().method()==='POST');
  let release!:()=>void;const pending=new Promise<void>(resolve=>release=resolve);
  await page.route('**/candidate-restore',async route=>{await pending;await route.continue();},{times:1});
  const pressing=page.keyboard.press('Enter');
  await expect(page.locator('#version-action-result')).toContainText('正在恢复');
  await expect(page.locator('#version-restore')).toBeDisabled();
  await expect(page.locator('#version-candidate-file')).toBeDisabled();
  release();await pressing;expect((await restoredResponse).status()).toBe(200);
  await expect(page.locator('.review-reading')).toContainText('恢复前候选甲。');
  const restored=await (await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  expect(restored.current_agent_accepted).toBe(1);expect(restored.human_approved_final).toBe(false);
  await expect(page.locator('#version-select')).toBeDisabled();
  await expect(page.locator('#version-summary')).toContainText('当前 Agent/PSH 接受 1/2');
  await page.screenshot({path:info.outputPath('recovered-pending.png'),fullPage:true});
  page.once('dialog',async dialog=>{confirmations++;await dialog.accept();});
  await page.locator('#version-restore').click();await expect(page.locator('.review-reading')).toContainText('新候选甲。');
  await expect(page.locator('#version-restore')).toBeEnabled();
  state=await (await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  await upload(['并发候选甲。','保持乙。']);const concurrent=state.manifest_sha256;
  page.once('dialog',async dialog=>{confirmations++;await dialog.accept();});
  await page.locator('#version-restore').click();await expect(page.locator('#version-action-result')).toContainText('版本已变化');
  expect((await (await request.get(`/api/projects/${pid}/canonical-selection`)).json()).manifest_sha256).toBe(concurrent);
  await page.route('**/canonical-selection',async route=>{
    const response=await route.fetch();const body=await response.json();
    body.native_status.generation_job={mode:'mock',status:'running',request_id:'synthetic-active'};
    await route.fulfill({response,json:body});
  });
  await page.locator('#version-refresh').click();await expect(page.locator('#version-recovery-hint')).toContainText('仍在运行');
  await expect(page.locator('#version-restore')).toBeDisabled();
  await page.unroute('**/canonical-selection');await page.locator('#version-refresh').click();
  await expect(page.locator('#version-restore')).toBeEnabled();
  await page.screenshot({path:info.outputPath('stale-recovery-preserved.png'),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);expect(failures).toEqual([]);
  expect(messages.filter(m=>!m.includes('409 (Conflict)'))).toEqual([]);
  expect(exchanges.filter(r=>r.status>=400)).toEqual([{path:`/api/projects/${pid}/candidate-restore`,method:'POST',status:409}]);
  expect(confirmations).toBe(4);
  fs.writeFileSync(info.outputPath('recovery-observations.json'),JSON.stringify({viewport,errors,messages,failures,exchanges,confirmations,
    restoredChangedSegments:1,oldAcceptanceResurrected:false,physicalDisplay:false,browserVersion:page.context().browser()?.version()},null,2));
 });
}


for(const viewport of [{width:1280,height:900},{width:390,height:844}]) {
 test(`source candidate opinion native decision selection and singleton export ${viewport.width}`,async({page,request},info)=>{
  test.setTimeout(30000);
  await page.setViewportSize(viewport);await page.emulateMedia({reducedMotion:'reduce'});
  const errors:string[]=[];const consoleErrors:string[]=[];const failedRequests:string[]=[];const exchanges:any[]=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  page.on('requestfailed',r=>failedRequests.push(r.url()));page.on('response',r=>exchanges.push({path:new URL(r.url()).pathname,method:r.request().method(),status:r.status()}));
  const pid=`source-flow-${viewport.width}-${Date.now()}`;
  await page.goto('/index.html');
  await page.locator('#long-project-id').fill(pid);await page.locator('#long-project-name').fill('合成长篇流程');
  await page.locator('#long-source-files').setInputFiles([
    {name:'003-synthetic.md',mimeType:'text/markdown',buffer:Buffer.from('# 合成章三\n\n'+Array.from({length:5},(_,i)=>`原段${i}。`).join('\n\n'))},
    {name:'718-synthetic.md',mimeType:'text/markdown',buffer:Buffer.from('# 合成章七一八\n\n另段甲。\n\n另段乙。')}
  ]);
  await page.getByRole('button',{name:'导入完整源章节'}).click();
  await expect(page.locator('#long-import-result')).toContainText('2 章 / 7 段');
  await page.locator('#long-import-result a').click();
  await expect(page.locator('#version-summary')).toContainText('候选 0/7');
  let state=await (await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  const downloadEvent=page.waitForEvent('download');await page.locator('#version-download').focus();await expect(page.locator('#version-download')).toBeFocused();await page.keyboard.press('Enter');
  const download=await downloadEvent;const packet=JSON.parse(fs.readFileSync((await download.path())!,'utf8'));
  expect(packet.generation_started).toBe(false);expect(packet.source_segments).toHaveLength(7);
  const candidates=state.segments.map((r:any,i:number)=>({segment_id:r.segment_id,target_text:`合成译文${i}。`}));
  await page.locator('#version-candidate-file').setInputFiles({name:'candidate.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({source_inventory_sha256:state.source_inventory_sha256,candidates}))});
  await expect(page.locator('.review-reading')).toContainText('合成译文0。');
  await expect(page.locator('#version-select')).toBeDisabled();
  const action=(name:string)=>page.locator(viewport.width<500?`#review-mobile-actions button[data-action=${name}]`:`.review-meta button[data-action=${name}]`);
  await action('approve').click();
  await expect(page.locator('#review-decision-truth')).toContainText('尚无当前 Agent/PSH 接受');
  await expect(page.locator('.review-meta [data-status=unverified_claim]')).toBeVisible();
  await expect(page.locator('#version-select')).toBeDisabled();
  await page.screenshot({path:info.outputPath('opinion-unverified.png'),fullPage:true});
  trustedSyntheticAgentSetup(pid);await page.reload();
  await expect(page.locator('#version-select')).toBeEnabled();
  await action('reject').click();await expect(page.locator('#version-select')).toBeDisabled();
  state=await (await request.get(`/api/projects/${pid}/canonical-selection`)).json();expect(state.current_agent_accepted).toBe(6);
  trustedSyntheticAgentSetup(pid);await page.reload();
  await expect(page.locator('#version-select')).toBeEnabled();await page.locator('#version-select').click();
  await expect(page.locator('#version-summary')).toContainText('已选择当前接受版本');
  await page.screenshot({path:info.outputPath('selected-current-version.png'),fullPage:true});
  await page.locator('#version-export-link').click();
  await expect(page.locator('#canonical-export')).toBeDisabled();await page.locator('#canonical-confirm').check();await expect(page.locator('#canonical-export')).toBeEnabled();
  const exportedResponse=page.waitForResponse(r=>r.url().endsWith('/canonical-export')&&r.request().method()==='POST');
  await page.locator('#canonical-export').click();const exported=await (await exportedResponse).json();
  await expect(page.locator('#canonical-result')).toContainText('2 章 / 7 段');expect(exported.human_approved_final).toBe(false);
  await expect(page.locator('#canonical-export')).toBeEnabled();
  state=await (await request.get(`/api/projects/${pid}/canonical-selection`)).json();
  const changed=await request.post(`/api/projects/${pid}/candidate-import`,{data:{expected_manifest_sha256:state.manifest_sha256,source_inventory_sha256:state.source_inventory_sha256,candidates:candidates.map((r:any)=>({...r,target_text:r.target_text+' changed'}))}});expect(changed.ok()).toBeTruthy();
  await page.locator('#canonical-export').click();await expect(page.locator('#canonical-result')).toContainText('旧稿已保留');
  const summary=await (await request.get('/api/export/status')).json();expect(summary.production_summary.bundle_revision).toBe(exported.bundle_revision);
  await page.screenshot({path:info.outputPath('stale-export-refused.png'),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);expect(failedRequests).toEqual([]);expect(consoleErrors.filter(e=>!e.includes('409 (Conflict)'))).toEqual([]);
  expect(exchanges.filter(r=>r.status>=400)).toEqual([{path:`/api/projects/${pid}/canonical-export`,method:'POST',status:409}]);
  await page.goto(`/review.html?project=${pid}`);
  await expect(page.locator('#version-summary')).toContainText(pid);
  await page.locator('#project-switcher').selectOption('demo-jp-cn');
  await expect(page.locator('#version-summary')).toContainText('短样例');
  await expect(page.locator('#version-download')).toBeDisabled();
  await page.locator('#project-switcher').selectOption(pid);
  await expect(page.locator('#version-summary')).toContainText(pid);
  await expect(page.locator('#version-summary')).toContainText('当前 Agent/PSH 接受 0/7');
  await expect(page.locator('#version-select')).toBeDisabled();

  fs.writeFileSync(info.outputPath('flow-evidence.json'),JSON.stringify({viewport,errors,consoleErrors,failedRequests,exchanges,bundleRevision:exported.bundle_revision,sourceSegments:7,humanApprovedFinal:false,nativeDecisionFixture:'existing local CAS, synthetic-only; not model/quality evidence',browserVersion:page.context().browser()?.version()},null,2));
  await info.attach('flow-evidence',{path:info.outputPath('flow-evidence.json'),contentType:'application/json'});
 });
}
