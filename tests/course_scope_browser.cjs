// Run only with tests/course_library_fixture.py: no external model or live student data.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const base=process.env.COURSE_TEST_URL||'http://127.0.0.1:8014';
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base);
  async function createCourse(title){await page.getByRole('button',{name:'新建课程',exact:true}).click();await page.getByRole('textbox',{name:'课程名称'}).fill(title);await page.getByRole('button',{name:'创建课程',exact:true}).click();await page.getByRole('heading',{name:title,exact:true}).waitFor();}
  await createCourse('初中数学');await page.getByRole('button',{name:'开始第一个小课'}).click();
  await page.getByRole('textbox',{name:'你想学什么？'}).fill('英语语法');
  await page.getByRole('button',{name:'入门理解 从容易懂的地方开始'}).click();await page.getByRole('button',{name:'初中',exact:true}).click();
  await page.getByRole('button',{name:'生成我的学习计划'}).click();
  await page.getByRole('alert').filter({hasText:'超出了「初中数学」的课程范围'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'你想学什么？'}).inputValue(),'英语语法');
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.chat.sessions.v1')||'[]').length),0);
  await page.getByRole('textbox',{name:'你想学什么？'}).fill('一次函数');await page.getByRole('button',{name:'生成我的学习计划'}).click();
  await page.getByText('我们按三个小步骤学习，先确认这个计划。',{exact:true}).waitFor();
  const access=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.library.v1'))),nav=await page.evaluate(()=>JSON.parse(localStorage.getItem('aiteacher.learning.navigation.v1')));
  async function api(path){const response=await page.request.get(base+path,{headers:{Authorization:`Bearer ${access.token}`}});assert.ok(response.ok());return response.json();}
  const before=(await api(`/api/sessions/${nav.session_id}`)).snapshot;
  await page.getByRole('combobox',{name:'对话对象'}).selectOption('lecturer');
  async function send(text){await page.getByRole('textbox',{name:'聊天消息'}).fill(text);await page.getByRole('button',{name:'发送',exact:true}).click();}
  await send('我想学习英语语法');await page.getByRole('alert').filter({hasText:'超出了「初中数学」的课程范围'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'聊天消息'}).inputValue(),'我想学习英语语法');
  assert.equal((await api(`/api/sessions/${nav.session_id}`)).snapshot.revision,before.revision);
  await send('数学课里我想学做饭');await page.getByRole('alert').filter({hasText:'超出了「初中数学」的课程范围'}).waitFor();
  assert.equal((await api(`/api/sessions/${nav.session_id}`)).snapshot.revision,before.revision);
  await send('解释函数里的英文 slope');
  await page.getByText('函数描述两个量一起变化的关系。一个输入对应一个输出。',{exact:true}).waitFor();
  const usage=await api(`/api/sessions/${nav.session_id}/usage`);assert.ok(usage.recent_calls.some(call=>call.agent==='course_guard'));
  const valid=(await api(`/api/sessions/${nav.session_id}`)).snapshot;
  await page.getByRole('combobox',{name:'对话对象'}).selectOption('auto');await send('学习一次函数，偏题测试');
  await page.getByText('course_scope_violation',{exact:false}).waitFor();
  const guarded=(await api(`/api/sessions/${nav.session_id}`)).snapshot;
  assert.deepEqual(guarded.plan,valid.plan);assert.deepEqual(guarded.evidence,valid.evidence);
  assert.equal(guarded.messages.filter(message=>message.agent==='lecturer'&&message.status==='ai').length,valid.messages.filter(message=>message.agent==='lecturer'&&message.status==='ai').length);
  await page.getByRole('button',{name:'课程管理'}).click();await createCourse('初中英语');await page.getByRole('button',{name:'全部课程'}).click();
  const catalog=await api('/api/learning-library'),english=catalog.courses.find(course=>course.title==='初中英语'),math=catalog.courses.find(course=>course.title==='初中数学');
  await page.locator('.course-card-main').filter({hasText:'初中数学'}).click();
  await page.getByRole('combobox',{name:'归类：一次函数'}).selectOption(english.id);
  await page.getByRole('alert').filter({hasText:'超出了「初中英语」的课程范围'}).waitFor();
  assert.equal((await api(`/api/courses/${math.id}`)).course.session_count,1);
  assert.equal((await api(`/api/courses/${english.id}`)).course.session_count,0);
  await page.getByRole('button',{name:'编辑课程信息'}).click();await page.getByRole('textbox',{name:'课程名称'}).fill('初中英语');await page.getByRole('button',{name:'保存修改',exact:true}).click();
  await page.getByRole('dialog').getByRole('alert').filter({hasText:'超出了「初中英语」的课程范围'}).waitFor();
  assert.equal((await api(`/api/courses/${math.id}`)).course.title,'初中数学');
  assert.deepEqual(errors,[]);
  console.log('PASS: wrong-topic intake and direct teaching blocked, terms allowed, AI drift stopped, no progress mutation, incompatible moves/rename blocked, guard usage recorded.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
