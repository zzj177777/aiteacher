// Local browser smoke test. Uses an isolated server with model credentials disabled.
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const base=process.env.INTAKE_TEST_URL||'http://127.0.0.1:8012';
const output=path.resolve(__dirname,'../.verification');
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1100},deviceScaleFactor:1,reducedMotion:'reduce'});
  const page=await context.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.goto(base);await page.getByRole('button',{name:'直接开始小课'}).click();await page.getByRole('heading',{name:'今天，我们学点什么？'}).waitFor();
    await page.screenshot({path:path.join(output,'intake-desktop.png'),fullPage:true});
    await page.getByRole('button',{name:'生成我的学习计划'}).click();
    assert.equal(await page.getByText('请选择至少一个学习目标。').count(),1);
    assert.equal(await page.locator('textarea[aria-invalid=true]').count(),1);
    await page.getByLabel('你想学什么？').fill('分数的意义');
    await page.getByRole('button',{name:'跟上课堂 配合教材与学校进度'}).click();
    await page.getByLabel('教材版本').fill('人教版');
    await page.getByLabel('当前章节或进度').fill('分数的初步认识');
    await page.getByRole('button',{name:'备考提分 围绕考试查漏补缺'}).click();
    await page.getByLabel('考试范围').fill('分数单元');
    await page.getByRole('button',{name:'小学',exact:true}).click();
    await page.getByLabel('具体年级').selectOption('三年级');
    await page.getByText('补充基础与学习时间').click();
    await page.getByLabel('学过哪些内容？哪里容易卡住？').fill('不清楚分母的含义');
    await page.getByRole('button',{name:'20 分钟',exact:true}).click();
    await page.reload();
    await page.getByRole('heading',{name:'今天，我们学点什么？'}).waitFor();
    assert.equal(await page.getByLabel('你想学什么？').inputValue(),'分数的意义');
    await page.getByRole('button',{name:'备考提分 围绕考试查漏补缺'}).click();
    assert.equal(await page.getByLabel('考试范围').count(),0);
    await page.screenshot({path:path.join(output,'intake-filled.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(output,'intake-mobile.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
    await page.setViewportSize({width:1440,height:1100});
    let failOnce=true,submitted;
    await page.route('**/api/sessions/*/events',async route=>{
      const body=route.request().postDataJSON();
      if(body.type==='chat_intake'){
        submitted=body.payload;
        if(failOnce){failOnce=false;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'测试提交失败，请重试。'})});}
      }
      return route.continue();
    });
    await page.getByRole('button',{name:'生成我的学习计划'}).click();
    await page.getByRole('alert').filter({hasText:'测试提交失败'}).waitFor();
    assert.equal(await page.getByLabel('你想学什么？').inputValue(),'分数的意义');
    await page.getByRole('button',{name:'生成我的学习计划'}).click();
    await page.getByRole('region',{name:'课堂对话'}).waitFor();
    assert.equal(submitted.grade,'三年级');
    assert.equal(submitted.exam_scope,'');
    assert.equal(submitted.background,'不清楚分母的含义');
    assert.deepEqual(submitted.goals,['跟上课堂']);
    const credential=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.chat.sessions.v1'))[0]);
    let snapshot;
    for(let i=0;i<50;i++){
      const response=await context.request.get(`${base}/api/sessions/${credential.session_id}`,{headers:{Authorization:`Bearer ${credential.token}`}});
      snapshot=(await response.json()).snapshot;
      if(!snapshot.working)break;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    assert.equal(snapshot.profile.intake.grade,'三年级');
    assert.equal(snapshot.profile.intake.source,'student_self_report');
    assert.equal(snapshot.evidence.length,0);
    assert.equal(snapshot.messages.filter(m=>m.agent==='student').length,1);
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('aiteacher.intake.draft.v1')),null);
    await page.reload();await page.getByRole('region',{name:'课堂对话'}).waitFor();
    assert.equal(await page.getByRole('heading',{name:'今天，我们学点什么？'}).count(),0);
    await page.getByRole('button',{name:'新学习会话'}).click();
    await page.getByRole('heading',{name:'今天，我们学点什么？'}).waitFor();
    await page.getByRole('button',{name:'返回当前课堂'}).click();
    await page.getByRole('region',{name:'课堂对话'}).waitFor();
    await page.getByRole('button',{name:'新学习会话'}).click();
    await page.getByRole('button',{name:'想边聊边说？直接聊天'}).click();
    await page.getByRole('textbox',{name:'聊天消息'}).waitFor();
    assert.equal(await page.locator('.conversation-message.student').count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS: desktop/mobile, required fields, conditional questions, draft restore, failure retry, real persistence, session restore, cancel and skip.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
