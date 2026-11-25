// Use tests/course_library_fixture.py: all planning and teaching calls remain local.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const base=process.env.COURSE_TEST_URL||'http://127.0.0.1:8014',output=path.resolve(__dirname,'../.verification');
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},reducedMotion:'reduce'}),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base);
  async function createCourse(title){await page.getByRole('button',{name:'新建课程',exact:true}).click();await page.getByRole('textbox',{name:'课程名称'}).fill(title);await page.getByRole('button',{name:'创建课程',exact:true}).click();await page.getByRole('heading',{name:title,exact:true}).waitFor();}
  await createCourse('初二数学');
  await page.getByRole('textbox',{name:'大课程学习目标'}).fill('学习一次函数，能看懂图像并解决基础题');
  await page.getByRole('textbox',{name:'学习范围或教材'}).fill('一次函数入门');
  await page.getByRole('textbox',{name:'目前基础'}).fill('分数和方程学过，函数是初学');
  await page.getByRole('button',{name:'生成课程路线'}).click();
  await page.locator('.roadmap-section').nth(2).waitFor();
  await page.getByRole('heading',{name:'补充小课与历史记录',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'开始第一个小课',exact:true}).count(),0);
  const access=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.library.v1'))),cid=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.navigation.v1')).course_id);
  async function api(path){const response=await page.request.get(base+path,{headers:{Authorization:`Bearer ${access.token}`}});assert.ok(response.ok());return response.json();}
  let detail=await api('/api/courses/'+cid),sections=detail.curriculum.sections;
  assert.equal(detail.sessions.length,0);assert.equal(sections.length,3);
  assert.deepEqual(await page.locator('.roadmap-section h3').allTextContents(),['函数的含义','函数的表示','一次函数入门']);
  assert.ok((await page.locator('.roadmap-section').nth(1).innerText()).includes('前置：函数的含义'));
  await page.getByRole('button',{name:'调整规划',exact:true}).waitFor();
  await page.screenshot({path:path.join(output,'curriculum-desktop.png'),fullPage:true});
  await page.getByRole('button',{name:'按顺序开始',exact:true}).click();
  await page.getByRole('region',{name:'课堂对话'}).waitFor();
  await page.getByText('我们按三个小步骤学习，先确认这个计划。',{exact:true}).waitFor();
  assert.equal(await page.getByRole('heading',{name:'今天，我们学点什么？'}).count(),0);
  const nav=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.navigation.v1'))),sid=nav.session_id;
  const first=(await api('/api/sessions/'+sid)).snapshot;
  assert.equal(first.section.id,sections[0].id);assert.equal(first.plan.nodes.length,3);
  await page.getByRole('button',{name:'保存并返回课程',exact:true}).click();
  await page.locator(`[data-section-id="${sections[0].id}"]`).getByText('学习中',{exact:true}).waitFor();
  assert.equal((await api('/api/courses/'+cid)).curriculum.confirmed_sections,0);
  await page.locator(`[data-section-id="${sections[0].id}"]`).getByRole('button',{name:'继续本节'}).click();
  await page.getByRole('region',{name:'课堂对话'}).waitFor();
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.navigation.v1')).session_id),sid);
  assert.equal((await api('/api/courses/'+cid)).sessions.length,1);
  await page.reload();await page.getByRole('region',{name:'课堂对话'}).waitFor();
  await page.getByRole('textbox',{name:'聊天消息'}).fill('开始吧');await page.getByRole('button',{name:'发送',exact:true}).click();
  await page.getByText('函数描述两个量一起变化的关系。一个输入对应一个输出。',{exact:true}).waitFor();
  for(let i=1;i<=3;i++){
   await page.getByRole('button',{name:'我明白了，继续 →'}).click();
   await page.waitForFunction(expected=>document.querySelectorAll('.route-graph li.completed').length===expected,i);
  }
  await page.getByRole('button',{name:'本节节点已确认，回到课程学习下一节'}).click();
  await page.locator(`[data-section-id="${sections[0].id}"]`).getByText('节点已确认',{exact:true}).waitFor();
  detail=await api('/api/courses/'+cid);assert.equal(detail.curriculum.confirmed_sections,1);assert.equal(detail.curriculum.next_section_id,sections[1].id);
  assert.equal(await page.getByRole('button',{name:'调整规划',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'按顺序开始',exact:true}).click();
  await page.getByText('我们按三个小步骤学习，先确认这个计划。',{exact:true}).waitFor();
  const nav2=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.navigation.v1')));
  assert.notEqual(nav2.session_id,sid);
  assert.equal((await api('/api/sessions/'+nav2.session_id)).snapshot.section.position,2);
  const observed=await api('/_observed_sections');assert.ok(observed.some(section=>section?.position===2));
  await page.getByRole('button',{name:'保存并返回课程',exact:true}).click();
  await page.locator('.roadmap-section').nth(2).waitFor();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(output,'curriculum-mobile.png'),fullPage:true});
  await createCourse('数学复习');
  await page.getByRole('textbox',{name:'大课程学习目标'}).fill('数学失败规划');await page.getByRole('button',{name:'生成课程路线'}).click();
  await page.getByRole('alert').filter({hasText:'前置要求'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'大课程学习目标'}).inputValue(),'数学失败规划');
  await page.getByRole('textbox',{name:'大课程学习目标'}).fill('学习一次函数');await page.getByRole('button',{name:'生成课程路线'}).click();
  await page.locator('.roadmap-section').nth(2).waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: course plan cards/order/prerequisites, section-local node planning, session reuse/reload, confirmed progress, next section, mobile and failed-plan retry.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
