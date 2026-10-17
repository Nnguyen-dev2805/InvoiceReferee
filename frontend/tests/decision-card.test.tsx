import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach,it,expect,vi} from "vitest";
import {DecisionCard} from "../src/features/decision_card";
import type {CaseView,IssueView} from "../src/types";
const issue={id:"i",kind:"AUTHORITY",field_or_rule:"RECOGNIZE_COST",owner:"approver",status:"OPEN",basis:"Chi phí 9000000",question:"Công nhận 9000000?",refs:[]} as IssueView;
const view={id:"c",version:7,state:"WAITING",activity:"activity:a",sources:[{id:"s",filename:"hoa-don.pdf"}],issues:[issue],instructions:[],actual_money:{},audit:[]} as unknown as CaseView;
const card={issue_id:"i",case_version:7,basis_id:"card:server",kind:"AUTHORITY",scope:"activity:a",title:"Công nhận chi phí",response_kind:"DECISION",known_facts:["Chi phí: 9.000.000 đ"],required_answer:"Công nhận 9000000?",effects:"Không ghi tiền đã chi",owner:"approver",excerpt_refs:[{source_id:"s",page:1,exact_quote:"00000101 · 06/10/2026"}],actions:[{issue_id:"i",action:"RECOGNIZE_COST",label:"Công nhận chi phí",amount:9000000,limit:20000000,authorized:true}],corrections:[]};
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
it("uses server basis and decisions endpoint, keeps source codes intact",async()=>{
 let sent:any=null;
 vi.stubGlobal("fetch",vi.fn(async(url,init)=>{if(String(url).endsWith("/card"))return new Response(JSON.stringify(card));sent={url,body:JSON.parse(init.body),headers:init.headers};return new Response(JSON.stringify({case_view:{...view,version:8}}));}));
 const onCase=vi.fn();render(<DecisionCard issue={issue} caseView={view} onCase={onCase}/>);
 expect(await screen.findByText("00000101 · 06/10/2026")).toBeInTheDocument();
 const user=userEvent.setup();await user.type(screen.getByLabelText("Lý do quyết định"),"Đã kiểm tra đầy đủ chứng từ và đúng công việc");await user.click(screen.getByRole("button",{name:"Phê duyệt các hành động trên"}));
 await waitFor(()=>expect(onCase).toHaveBeenCalledOnce());
 expect(sent.url).toBe("/api/cases/c/decisions");expect(sent.body).toMatchObject({basis_id:"card:server",actions:["RECOGNIZE_COST"],amount:9000000});expect(sent.headers["X-Expected-Version"]).toBe("7");
});
it("does not allow approval beyond current grant",async()=>{
 vi.stubGlobal("fetch",vi.fn(async()=>new Response(JSON.stringify({...card,actions:[{...card.actions[0],authorized:false,amount:25000000,unavailable_reason:"Cần cấp cao hơn"}]}))));
 render(<DecisionCard issue={issue} caseView={view} onCase={()=>{}}/>);
 expect(await screen.findByText("Cần cấp cao hơn")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Phê duyệt các hành động trên"})).toBeDisabled();
});
it("requires an explicit declaration correction rather than silently approving facts",async()=>{
 vi.stubGlobal("fetch",vi.fn(async()=>new Response(JSON.stringify({...card,kind:"FACT",response_kind:"CORRECT_DECLARATION",actions:[],corrections:[{id:"claim:x",label:"Điều chỉnh kê khai",changes:[{field:"printed_return",before:770000,after:830000}]}]}))));
 render(<DecisionCard issue={{...issue,kind:"FACT"}} caseView={view} onCase={()=>{}}/>);
 expect(await screen.findByText(/770.000/)).toBeInTheDocument();expect(screen.getByText(/830.000/)).toBeInTheDocument();
 expect(screen.queryByRole("button",{name:"Phê duyệt các hành động trên"})).toBeNull();
 expect(screen.getByRole("button",{name:"Lưu bản kê khai điều chỉnh"})).toBeDisabled();
});

it("labels employee declaration provenance without offering a false PDF link",async()=>{
 vi.stubGlobal("fetch",vi.fn(async()=>new Response(JSON.stringify({...card,excerpt_refs:[{source_id:"declaration:revision-1",page:null,exact_quote:"Nhân viên điều chỉnh số hoàn"}]}))));
 const select=vi.fn();render(<DecisionCard issue={issue} caseView={view} onCase={()=>{}} onSourceSelected={select}/>);
 expect(await screen.findByText("Kê khai điều chỉnh của nhân viên · trang khai báo")).toBeInTheDocument();
 expect(screen.queryByRole("button",{name:"Kê khai điều chỉnh của nhân viên"})).toBeNull();
 expect(select).not.toHaveBeenCalled();
});
