// Deterministic engineering rehearsal, not LIVE/practitioner scoring.
import {chromium}from "playwright";
import {readFileSync,writeFileSync,mkdirSync}from "node:fs";
import {join,dirname}from "node:path";
import {fileURLToPath}from "node:url";
const ROOT=join(dirname(fileURLToPath(import.meta.url)),"..");
const DIR=join(ROOT,`.runtime/escalation-answerability/browser-output${process.env.RUN_LABEL?"-"+process.env.RUN_LABEL:""}`);mkdirSync(DIR,{recursive:true});
const manifest=JSON.parse(readFileSync(join(ROOT,".runtime/escalation-answerability/browser/manifest.json")));
const browser=await chromium.launch();const summaries=[];
const ports={authority:65201,compound:65202,over:65203,fact:65204,collect:65205,pay:65206,balanced:65207};
for(const name of Object.keys(ports).filter(n=>!process.env.CASE_FILTER||n===process.env.CASE_FILTER)){
 const origin=`http://127.0.0.1:${ports[name]}`;const context=await browser.newContext();await context.addCookies([{name:"invoice_referee_session",value:manifest[name].session,url:origin}]);const page=await context.newPage();
 const summary={name,ok:false,mode:manifest[name].mode,provider_calls:0};
 try{
  await page.goto(origin,{waitUntil:"networkidle"});await page.locator("tbody tr").first().click();
  const detail=async()=>await page.evaluate(async id=>await(await fetch(`/api/cases/${id}`)).json(),manifest[name].root_id);
  if(["collect","pay","balanced"].includes(name)){
   const view=await detail();if(view.issues.length)throw new Error("Routine has issues "+JSON.stringify(view.issues));
   const expected={collect:["COLLECT",760000],pay:["PAY",400000],balanced:[null,0]}[name];
   if(expected[0]){if(view.instructions.length!==1||view.instructions[0].direction!==expected[0]||view.instructions[0].amount!==expected[1])throw new Error("wrong routine money");}
   else if(view.state!=="SETTLED"||view.instructions.length)throw new Error("wrong balance");
   summary.outcome=view.state;summary.instructions=view.instructions;
  }else{
   await page.getByRole("tab",{name:/Vấn đề cần xử lý/}).click();
   const card=page.getByTestId(name==="fact"?"question-FACT":"question-AUTHORITY").first();await card.waitFor({state:"visible"});
   const body=await card.innerText();writeFileSync(join(DIR,`${name}-card.txt`),body);
   await page.screenshot({path:join(DIR,`${name}-before.png`),fullPage:true});
   if(name==="over"){
    if(!body.includes("25.000.000")||!body.includes("20.000.000"))throw new Error("missing ceiling context");
    if(await page.getByRole("button",{name:"Phê duyệt các hành động trên"}).isEnabled())throw new Error("over-limit approval enabled");
    const view=await detail();if(view.instructions.length)throw new Error("over-limit issued money");
   }else{
    if(name==="fact"){
     for(const number of ["3.800.000","2.970.000","830.000","770.000","60.000"]){if(!body.includes(number)&&!body.includes(number.replaceAll(".","")))throw new Error("card missing "+number);}
     await card.getByRole("checkbox").check();await page.getByLabel("Lý do điều chỉnh").fill("Tôi sửa số hoàn kê khai theo ứng và chi đã đối chiếu; không phát sinh thêm khoản chi.");
    }else{
     if(!body.includes("9.000.000"))throw new Error("missing 9m recognition");
     if(name==="compound"&&!body.includes("8.000.000"))throw new Error("missing separate 8m issuance");
     await card.getByLabel("Lý do quyết định").fill("Đã kiểm tra chứng từ và công việc, chấp thuận các hành động trong quyền được cấp.");
    }
    const response=page.waitForResponse(r=>r.request().method()==="POST"&&(r.url().endsWith("/decisions")||r.url().endsWith("/corrections")));
    await card.getByRole("button",{name:name==="fact"?"Lưu bản kê khai điều chỉnh":"Phê duyệt các hành động trên"}).click();
    const r=await response;if(!r.ok())throw new Error(await r.text());
    summary.request={url:r.url(),body:r.request().postDataJSON()};
    await page.reload({waitUntil:"networkidle"});const view=await detail();
    const amount={fact:830000,authority:1000000,compound:8000000}[name];const direction=name==="fact"?"COLLECT":"PAY";
    if(view.issues.length||view.instructions.length!==1||view.instructions[0].direction!==direction||view.instructions[0].amount!==amount)throw new Error("roundtrip failed "+JSON.stringify(view));
    if(view.actual_money.P.value!==0||view.actual_money.R.value!==0||view.state==="SETTLED")throw new Error("decision fabricated money/closure");
    summary.outcome=view.state;summary.instructions=view.instructions;summary.declaration_corrections=view.declaration_corrections;
    writeFileSync(join(DIR,`${name}-after.json`),JSON.stringify(view,null,2));
   }
  }
  await page.screenshot({path:join(DIR,`${name}-after.png`),fullPage:true});summary.ok=true;
 }catch(error){summary.error=String(error);await page.screenshot({path:join(DIR,`${name}-failure.png`),fullPage:true}).catch(()=>{});writeFileSync(join(DIR,`${name}-failure-body.txt`),await page.locator("body").innerText().catch(()=>""));}
 finally{summaries.push(summary);await context.close();writeFileSync(join(DIR,"summary.json"),JSON.stringify(summaries,null,2));}
}
await browser.close();console.log(JSON.stringify(summaries,null,2));process.exit(summaries.every(s=>s.ok)?0:1);
