// Use only the isolated local provider in tests/plain_language_fixture.py.
const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const base=process.env.PLAIN_TEST_URL||'http://127.0.0.1:8012';
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1600,height:1100},reducedMotion:'reduce'});
 const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 const output=path.resolve(__dirname,'../.verification');
 async function start(){await page.goto(base);await page.getByRole('button',{name:'想边聊边说？直接聊天'}).click();await page.getByRole('combobox',{name:'对话对象'}).selectOption('lecturer');}
 async function send(text){await page.getByRole('textbox',{name:'聊天消息'}).fill(text);await page.getByRole('button',{name:'发送',exact:true}).click();}
 async function credential(){return page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.chat.sessions.v1'))[0]);}
 const latest=()=>page.locator('.annotated-lecture').last();
 async function geometry(row){
  return row.evaluate(element=>{
   const article=element.querySelector('.conversation-message').getBoundingClientRect(),row=element.getBoundingClientRect();
   const cards=[...element.querySelectorAll('.plain-callout')].map(card=>{const rect=card.getBoundingClientRect();return {top:rect.top,bottom:rect.bottom,left:rect.left,right:rect.right};});
   const links=[...element.querySelectorAll('.plain-annotation-link')].map(link=>{
    const index=link.parentElement.dataset.linkIndex,card=element.querySelector(`[data-callout-index="${index}"]`),id=card.dataset.annotationId;
    const anchors=[...element.querySelectorAll(`.conversation-message [data-plain-ids~="${CSS.escape(id)}"]`)];
    const rects=anchors.flatMap(anchor=>[...anchor.getClientRects()]).filter(rect=>rect.width&&rect.height),end=rects.at(-1);
    const match=link.getAttribute('d').match(/^M([-\d.]+),([-\d.]+)/);
    return {y:Number(match[2])+row.top,quoteY:end?end.top+end.height/2:null};
   });
   return {articleRight:article.right,rowBottom:row.bottom,cards,links,overflow:document.documentElement.scrollWidth>innerWidth};
  });
 }
 async function checkGeometry(row,count){
  await page.waitForFunction(({id,count})=>document.querySelector(`[data-annotated-message-id="${CSS.escape(id)}"]`)?.querySelectorAll('.plain-annotation-link').length===count,{id:await row.getAttribute('data-annotated-message-id'),count});
  const result=await geometry(row);assert.equal(result.overflow,false);assert.equal(result.cards.length,count);assert.equal(result.links.length,count);
  for(let i=0;i<result.cards.length;i++){
   assert.ok(result.cards[i].left>result.articleRight+20,'callout remains to the right of the original');
   assert.ok(result.cards[i].bottom<=result.rowBottom+1,'callout remains within its own lecture row');
   if(i)assert.ok(result.cards[i].top>=result.cards[i-1].bottom+16,'callouts do not overlap');
  }
  for(const link of result.links){assert.notEqual(link.quoteY,null);assert.ok(Math.abs(link.y-link.quoteY)<1,'arrow starts at the selected original line');}
 }
 try{
  await start();assert.equal(await page.locator('.plain-annotation-rail').count(),0);
  await send('解释分母');await latest().getByRole('status').filter({hasText:'正在找出难懂的句子'}).waitFor();
  const cred=await credential(),headers={Authorization:`Bearer ${cred.token}`};
  const before=(await context.request.get(`${base}/api/sessions/${cred.session_id}`,{headers}).then(response=>response.json())).snapshot;
  assert.equal(before.working,false);
  const firstId=before.messages.find(message=>message.agent==='lecturer'&&message.status==='ai'&&message.kind!=='handoff').id;
  await send('接着解释分子');
  await latest().getByText('它告诉你，分好的东西拿了几份。',{exact:true}).waitFor();
  const secondId=await latest().getAttribute('data-annotated-message-id');
  await page.locator(`[data-annotated-message-id="${firstId}"]`).getByText('它告诉你，一整个东西被平均分成几份。',{exact:true}).waitFor();
  assert.equal(await page.locator(`[data-annotated-message-id="${secondId}"]`).getByText('它告诉你，分好的东西拿了几份。',{exact:true}).count(),1);
  await page.reload();await latest().getByText('它告诉你，分好的东西拿了几份。',{exact:true}).waitFor();
  const restored=(await context.request.get(`${base}/api/sessions/${cred.session_id}`,{headers}).then(response=>response.json())).snapshot;
  const cached=await context.request.post(`${base}/api/sessions/${cred.session_id}/plain-language`,{headers,data:{message_id:secondId}}).then(response=>response.json());
  assert.equal(cached.status,'completed');assert.equal(cached.format_version,2);
  const unchanged=(await context.request.get(`${base}/api/sessions/${cred.session_id}`,{headers}).then(response=>response.json())).snapshot;
  assert.equal(unchanged.revision,restored.revision);assert.deepEqual(unchanged.evidence,[]);
  await page.getByRole('combobox',{name:'对话对象'}).selectOption('lecturer');await send('解释分母，辅助失败');
  await latest().getByRole('button',{name:'重新生成',exact:true}).waitFor();
  assert.equal(await latest().locator('.conversation-message').filter({hasText:'模拟辅助失败'}).count(),1);
  await latest().getByRole('button',{name:'重新生成',exact:true}).click();
  await latest().getByText('它告诉你，一整个东西被平均分成几份。',{exact:true}).waitFor();
  // A longer lecture exercises separate paragraph anchors, bold spans and a formula.
  await send('批注演示');await latest().getByRole('heading',{name:'分数写法',exact:true}).waitFor();
  const row=latest();await checkGeometry(row,3);
  assert.equal(await row.locator('.plain-difficulty').count(),3);
  assert.ok(await row.locator('.conversation-message strong .plain-quote-anchor').count()>=2);
  assert.equal(await row.locator('.conversation-message .katex').count(),1);
  assert.equal(await row.locator('.conversation-message .formula-fallback').count(),0);
  await row.getByRole('button',{name:'定位这句话'}).last().click();
  assert.equal(await row.getAttribute('data-active-annotation'),'2');
  await row.locator('.plain-callout').first().getByText('看个直观例子',{exact:true}).click();
  await page.waitForFunction(id=>{
   const cards=[...document.querySelector(`[data-annotated-message-id="${CSS.escape(id)}"]`).querySelectorAll('.plain-callout')].map(card=>card.getBoundingClientRect());
   return cards[1].top>=cards[0].bottom+16;
  },await row.getAttribute('data-annotated-message-id'));
  await checkGeometry(row,3);
  await row.locator('.conversation-message').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,'annotation-desktop.png'),fullPage:true});
  await row.screenshot({path:path.join(output,'annotation-detail.png')});
  for(const width of [1200,1000]){await page.setViewportSize({width,height:1000});await checkGeometry(row,3);}
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const mobile=await geometry(row);for(let i=1;i<mobile.cards.length;i++)assert.ok(mobile.cards[i].top>=mobile.cards[i-1].bottom+10);
  assert.equal(await row.locator('.plain-annotation-arrows').isVisible(),false);
  await page.screenshot({path:path.join(output,'annotation-mobile.png'),fullPage:true});
  const usage=await context.request.get(`${base}/api/sessions/${cred.session_id}/usage`,{headers}).then(response=>response.json());assert.ok(usage.recent_calls.some(call=>call.agent==='plain_language'));
  await page.getByRole('button',{name:'新学习会话'}).click();await page.getByRole('button',{name:'想边聊边说？直接聊天'}).click();
  assert.equal(await page.locator('.plain-callout').count(),0);assert.deepEqual(errors,[]);
  console.log('PASS: paragraph highlights and arrows, separate non-overlapping callouts, bold and formula anchors, resize/expansion alignment, mobile, history isolation, retries, caching and session switching.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
