// Built UI smoke: isolated browser storage; no course writes or model calls.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'D:/vibe coding/DeepTutor/web/node_modules/playwright');
const root=path.resolve(__dirname,'..'),base=process.env.MATERIALS_TEST_URL||'http://materials.test',dist=path.join(root,'dist');
const catalog=JSON.parse(fs.readFileSync(path.join(root,'backend/resources/textbooks/catalog.json'),'utf8'));
for(const book of catalog.books){const eid=book.term===1?'pep-2022-topic':'public-mirror-archive';book.local_editions=[{edition_id:eid,label:book.term===1?'2022 年专题存档（历史参考）':'公开镜像存档（旧版参考）',format:book.term===1?'image_pdf':'source_pdf',page_count:120,bytes:20000000,read_url:`/api/materials/${book.id}/editions/${eid}/pdf`,download_url:`/api/materials/${book.id}/editions/${eid}/pdf?download=true`,source_url:book.term===1?'https://bp.pep.com.cn/xsjc2022/index.html':'https://github.com/ardorleo/keben'}];}
const output=path.join(root,'.verification');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1050},reducedMotion:'reduce'}),errors=[],writes=[];
  let failNext=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>localStorage.setItem('aiteacher.learning.library.v1',JSON.stringify({library_id:'materials-ui-test',token:'fixture-only'})));
  await page.route(`${base}/**`,async route=>{
   const req=route.request(),url=new URL(req.url());
   if(url.pathname.startsWith('/api/')){
    if(req.method()!=='GET')writes.push(url.pathname);
    if(url.pathname==='/api/learning-library')return route.fulfill({json:{courses:[],unassigned_sessions:[]}});
    if(url.pathname==='/api/materials'){
     if(failNext){failNext=false;return route.fulfill({status:503,json:{detail:'fixture unavailable'}});}
     return base==='http://materials.test'?route.fulfill({json:{...catalog,total:catalog.books.length,local_book_count:12}}):route.continue();
    }
    return route.fulfill({status:404,json:{detail:'Unexpected test API request'}});
   }
   if(base!=='http://materials.test')return route.continue();
   const file=path.resolve(dist,'.'+(url.pathname==='/'?'/index.html':url.pathname));
   if(!file.startsWith(dist+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   return route.fulfill({body:fs.readFileSync(file),contentType:{'.html':'text/html','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf'}[path.extname(file)]||'application/octet-stream'});
  });
  await page.goto(base);
  await page.getByRole('button',{name:'资料库',exact:true}).click();
  await page.locator('.textbook-card').nth(11).waitFor();
  assert.equal(await page.locator('.textbook-card').count(),12);
  const links=await page.locator('.textbook-card a').evaluateAll(elements=>elements.map(el=>({href:el.href,target:el.target,rel:el.rel})));
  for(const link of links){if(link.href.startsWith('https://')){assert.equal(link.target,'_blank');assert.ok(link.rel.includes('noopener'));}else assert.ok(link.href.startsWith(base+'/api/materials/'));}
  assert.equal(await page.getByRole('link',{name:'本地阅读',exact:true}).count(),12);
  assert.equal(await page.getByRole('link',{name:'下载 PDF',exact:true}).count(),12);
  await page.getByRole('combobox',{name:'筛选年级'}).selectOption('3');
  assert.equal(await page.locator('.textbook-card').count(),2);
  await page.getByRole('combobox',{name:'筛选册次'}).selectOption('2');
  assert.equal(await page.locator('.textbook-card').count(),1);
  assert.equal(await page.getByRole('link',{name:'官方在线阅读',exact:true}).getAttribute('href'),'https://book.pep.com.cn/1221001302251/');
  await page.getByRole('textbox',{name:'搜索教材名称'}).fill('英语');
  await page.getByRole('heading',{name:'没有找到匹配的教材'}).waitFor();
  await page.getByRole('button',{name:'查看全部',exact:true}).click();
  await page.locator('.textbook-card').nth(11).waitFor();
  await page.screenshot({path:path.join(output,'materials-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(output,'materials-mobile.png'),fullPage:true});
  await page.reload();await page.locator('.textbook-card').nth(11).waitFor();
  await page.getByRole('button',{name:'返回课程中心',exact:true}).click();
  // Historical semester bookmarks remain readable; the new school portal is UI-only.
  await page.evaluate(()=>localStorage.setItem('aiteacher.learning.navigation.v1',JSON.stringify({view:'primary'})));
  await page.reload();await page.getByRole('heading',{name:'你想补哪一学期？'}).waitFor();
  for(const book of catalog.books){
   await page.getByRole('button',{name:book.grade_label+book.volume,exact:true}).click();
   await page.getByRole('button',{name:/查看本学期教材资料/}).click();
   const card=page.locator('.textbook-card');await card.waitFor();
   assert.equal(await card.count(),1);assert.equal(await card.getAttribute('data-material-id'),book.id);
   assert.equal(await card.getByRole('link',{name:'官方在线阅读',exact:true}).getAttribute('href'),book.reader_url);
   const localRead=await card.getByRole('link',{name:'本地阅读',exact:true}).getAttribute('href');
   assert.equal(localRead,book.local_editions[0].read_url);
   assert.equal(await card.getByRole('link',{name:'下载 PDF',exact:true}).getAttribute('href'),localRead+'?download=true');
   if(base!=='http://materials.test'){
    for(const suffix of ['', '?download=true']){
     const response=await page.request.get(base+localRead+suffix,{headers:{Range:'bytes=0-15'}});
     assert.equal(response.status(),206);assert.ok(response.headers()['content-type'].includes('application/pdf'));
     assert.ok((await response.body()).toString().startsWith('%PDF-'));
     assert.ok(response.headers()['content-disposition'].startsWith(suffix?'attachment':'inline'));
    }
   }
   if(book.grade===3&&book.term===1){
    await page.reload();await page.locator('.textbook-card').waitFor();
    assert.equal(await page.locator('.textbook-card').getAttribute('data-material-id'),book.id);
    await page.getByText('历史参考来源',{exact:true}).click();
    assert.equal(await page.getByRole('link',{name:'2022 年专题存档（历史参考）'}).getAttribute('href'),book.historical_references[0].reader_url);
    await page.screenshot({path:path.join(output,'materials-semester-mobile.png'),fullPage:true});
   }
   await page.getByRole('button',{name:'返回课本入口',exact:true}).click();
   await page.getByRole('heading',{name:book.grade_label+' · '+book.volume,exact:true}).waitFor();
   await page.getByRole('heading',{name:'章节目录待接入'}).waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.getByRole('button',{name:'全部年级',exact:true}).click();
  }
  failNext=true;await page.getByRole('button',{name:'教材资料库',exact:true}).click();
  await page.getByRole('alert').waitFor();
  await page.getByRole('button',{name:'重新加载',exact:true}).click();
  await page.locator('.textbook-card').nth(11).waitFor();
  await page.getByRole('button',{name:'返回年级列表',exact:true}).click();
  await page.getByRole('heading',{name:'你想补哪一学期？'}).waitFor();
  await page.getByRole('button',{name:'课程中心',exact:true}).click();
  await page.getByRole('region',{name:'学科课程入口'}).waitFor();
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log('PASS: 12 references and local PDF entries, filters, all semester mappings, source links, refresh/back navigation, error retry, mobile layout; no course or model writes. Live mode also verifies 24 PDF range/read/download responses.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
