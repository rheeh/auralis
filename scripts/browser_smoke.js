// Execute with Tabbit nodejs stdin, against scripts/fake_workspace.py and Vite :5175.
// This is an offline fixture test. Refuse to send production actions elsewhere.
await page.goto('http://127.0.0.1:5175/#/projects/1/workspace?new=1&view=source');
const fixture=await page.evaluate(async()=>{
  const response=await fetch('http://127.0.0.1:18200/test-fixture');return response.json();
});
assert.equal(fixture.fake_models,true);assert.equal(fixture.temporary_storage,true);
const errors=[];page.on('pageerror',error=>errors.push(error.message));
await page.getByPlaceholder('章节或本次改编标题（可选）').fill('固定测试章');
await page.getByPlaceholder('把小说原文粘贴到这里……').fill('小林问：雨停了吗？小周说：还没有，再等一会。');
await page.getByRole('button',{name:'解析原文，进入人物与台本',exact:true}).click();
await page.getByRole('button',{name:'人物设定满意，生成台本',exact:true}).click({timeout:10000});
await page.getByRole('button',{name:'选用此版本，进入逐句制作',exact:true}).click({timeout:10000});
await page.getByRole('button',{name:'生成全部试听',exact:true}).click({timeout:10000});
await expect(page.getByText('音频 2/2',{exact:true})).toBeVisible({timeout:10000});
await page.getByRole('button',{name:'按当前指导重新生成本句',exact:true}).first().click();
await expect(page.locator('main').getByText('版本 2/2',{exact:true})).toBeVisible({timeout:10000});
await page.locator('main').getByText('版本 2/2',{exact:true}).click();
await page.getByRole('option',{name:'版本 1/2',exact:true}).click();
await page.getByRole('button',{name:'04 声音编排',exact:true}).click();
await page.getByRole('button',{name:'快捷加音效',exact:true}).click();
await page.getByRole('dialog').getByRole('button',{name:'＋ 加入',exact:true}).first().click();
await expect(page.getByRole('dialog').getByText(/已加入“环境底噪 01”/)).toBeVisible();
await page.getByRole('dialog').getByRole('button',{name:'Close this dialog'}).click();
await page.getByRole('button',{name:'渲染成片',exact:true}).click();
await expect(page.getByRole('button',{name:'下载 WAV',exact:true})).toBeVisible({timeout:10000});
const wavResponse=page.waitForResponse(r=>r.url().includes('/timeline/render/audio'),{timeout:5000});
await page.getByRole('button',{name:'下载 WAV',exact:true}).click();
const response=await wavResponse;
assert([200,206].includes(response.status()));assert.match(response.headers()['content-type'],/audio\/wav/);
if(response.status()===206)assert.match(response.headers()['content-range'],/^bytes \d+-\d+\/\d+$/);
// Media elements may request a Range concurrently with the download. Validate
// the full file too; accepting 206 alone would not establish a complete WAV.
const complete=await context.request.get(response.url());
assert.equal(complete.status(),200);
const body=await complete.body();assert.equal(body.subarray(0,4).toString(),'RIFF');assert.equal(body.subarray(8,12).toString(),'WAVE');
await page.reload();
await expect(page.getByRole('button',{name:'下载 WAV',exact:true})).toBeVisible({timeout:10000});
assert.deepEqual(errors,[]);
return {passed:true,wavStatus:complete.status(),mediaStatus:response.status(),wavBytes:body.length,errors,text:(await page.locator('main').innerText()).slice(0,850)};
