// Run only against tests/course_library_fixture.py (no external model calls).
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const base=process.env.COURSE_TEST_URL||'http://127.0.0.1:8014';
const output=path.resolve(__dirname,'../.verification');
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce'}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  async function api(url,body,token,method=body?'POST':'GET'){
   const response=await context.request.fetch(base+url,{method,headers:token?{Authorization:`Bearer ${token}`}:{},...(body?{data:body}:{})});
   assert.ok(response.ok(),`${method} ${url}: ${response.status()}`);return response.json();
  }
  const old=await api('/api/sessions',{mode:'chat'});
  await api(`/api/sessions/${old.session_id}/events`,{expected_revision:0,idempotency_key:crypto.randomUUID(),type:'chat_intake',payload:{topic:'一次函数',goals:['入门理解'],stage:'初中',grade:'初二'}},old.token);
  await page.addInitScript(credential=>localStorage.setItem('aiteacher.chat.sessions.v1',JSON.stringify([{session_id:credential.session_id,token:credential.token,title:'一次函数'}])),old);
  // The seeded legacy credential should only be installed once per browser context.
  await page.goto(base);
  await page.getByRole('heading',{name:'未分类的小课'}).waitFor();
  await page.locator(`[data-session-id="${old.session_id}"]`).getByRole('heading',{name:'一次函数',exact:true}).waitFor();
  async function newCourse(title){await page.getByRole('button',{name:'新建课程',exact:true}).click();await page.getByRole('textbox',{name:'课程名称'}).fill(title);await page.getByRole('textbox',{name:'课程说明'}).fill('跟上学校进度，把基础学扎实。');await page.getByRole('button',{name:'创建课程',exact:true}).click();await page.getByRole('heading',{name:title,exact:true}).waitFor();}
  await newCourse('初二数学');
  await page.getByRole('button',{name:'开始第一个小课'}).click();
  await page.getByRole('textbox',{name:'你想学什么？'}).fill('二元一次方程');
  await page.getByRole('button',{name:'入门理解 从容易懂的地方开始'}).click();
  await page.getByRole('button',{name:'初中',exact:true}).click();
  await page.getByRole('combobox',{name:'具体年级'}).selectOption('初二');
  await page.getByRole('button',{name:'生成我的学习计划'}).click();
  await page.getByText('我们按三个小步骤学习，先确认这个计划。',{exact:true}).waitFor();
  const library=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.library.v1')));
  const nav=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.navigation.v1'))),sid=nav.session_id;
  const recorded=await api('/_observed_courses');assert.ok(recorded.some(course=>course?.title==='初二数学'));
  await page.getByRole('textbox',{name:'聊天消息'}).fill('开始吧');await page.getByRole('button',{name:'发送',exact:true}).click();
  await page.getByText('函数描述两个量一起变化的关系。一个输入对应一个输出。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'我明白了，继续 →'}).click();
  await page.getByText('按照教学大纲，进入第 2 个节点：',{exact:false}).waitFor();
  const before=(await api(`/api/sessions/${sid}`,null,library.token)).snapshot;
  await page.getByRole('button',{name:'课程管理'}).click();
  await page.locator(`[data-session-id="${sid}"]`).getByRole('heading',{name:'二元一次方程',exact:true}).waitFor();
  await page.locator(`[data-session-id="${sid}"]`).getByRole('button',{name:/二元一次方程/}).click();
  await page.getByRole('region',{name:'课堂对话'}).waitFor();
  assert.equal(await page.locator('.conversation-message').count(),before.messages.length);
  await page.reload();await page.getByRole('region',{name:'课堂对话'}).waitFor();
  const restored=(await api(`/api/sessions/${sid}`,null,library.token)).snapshot;
  assert.deepEqual(restored.plan,before.plan);assert.equal(restored.revision,before.revision);
  await page.getByRole('button',{name:'课程管理'}).click();await page.getByRole('button',{name:'全部课程'}).click();
  const catalog=await api('/api/learning-library',null,library.token),cid=catalog.courses[0].id;
  await page.getByRole('combobox',{name:'归类：一次函数'}).selectOption(cid);
  await page.locator('.course-card').getByText('2 个小课',{exact:true}).waitFor();
  await page.locator('.course-card-main').filter({hasText:'初二数学'}).click();
  await page.locator(`[data-session-id="${old.session_id}"]`).waitFor();
  assert.equal(await page.locator('.lesson-card').count(),2);
  await page.getByRole('button',{name:'编辑课程信息'}).click();
  await page.getByRole('textbox',{name:'课程名称'}).fill('初二数学 · 上学期');
  await page.getByRole('button',{name:'保存修改',exact:true}).click();
  await page.getByRole('heading',{name:'初二数学 · 上学期',exact:true}).waitFor();
  await page.screenshot({path:path.join(output,'course-detail-desktop.png'),fullPage:true});
  await page.locator(`[data-session-id="${old.session_id}"]`).getByRole('button',{name:/一次函数/}).click();
  await page.getByRole('region',{name:'课堂对话'}).waitFor();
  await page.getByRole('button',{name:'结束并保存'}).click();
  await page.getByText('本次学习已保存。',{exact:false}).waitFor();
  await page.getByRole('button',{name:'课程管理'}).click();
  await page.locator(`[data-session-id="${old.session_id}"]`).getByText('已结束',{exact:true}).waitFor();
  await newCourse('数学复习');await page.getByRole('button',{name:'全部课程'}).click();
  const courses=(await api('/api/learning-library',null,library.token)).courses;
  const revision=courses.find(course=>course.title==='数学复习');
  await page.locator('.course-card-main').filter({hasText:'初二数学 · 上学期'}).click();
  await page.getByRole('combobox',{name:'归类：一次函数'}).selectOption(revision.id);
  await page.waitForFunction(()=>document.querySelectorAll('.lesson-card').length===1);
  assert.equal((await api(`/api/sessions/${old.session_id}`,null,library.token)).snapshot.completed,true);
  await page.getByRole('button',{name:'全部课程'}).click();
  await page.getByRole('heading',{name:'我的课程'}).waitFor();
  await page.screenshot({path:path.join(output,'course-library-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(output,'course-library-mobile.png'),fullPage:true});
  await page.locator('.course-card-main').filter({hasText:'数学复习'}).click();
  await page.getByRole('heading',{name:'数学复习',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(output,'course-detail-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: legacy import, course creation, course-aware teaching, continue/reload, grouping, editing, ended records, moves, desktop/mobile and capability restoration.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
