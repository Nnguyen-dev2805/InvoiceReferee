import {useEffect,useState} from "react";
import {errorMessage} from "../api";
import {formatVnd} from "../format";
import type {CaseView,IssueView} from "../types";
import {OcrRegionView} from "./exception_review";
import {getQuestionCard,submitCard,type ServerQuestionCard} from "./question_card_api";
const FIELD_NAMES:Record<string,string>={printed_return:"Số hoàn kê khai",printed_reimbursement:"Số đề nghị chi thêm",printed_total:"Tổng chi phí kê khai",amount:"Khoản chi kê khai"};
export function DecisionCard({issue,caseView,onCase,onSourceSelected,currentRole=""}:{issue:IssueView;caseView:CaseView;onCase:(v:CaseView)=>void;onSourceSelected?:(id:string)=>void;currentRole?:string}){
 const [card,setCard]=useState<ServerQuestionCard|null>(null);
 const [error,setError]=useState<string|null>(null);
 const [reason,setReason]=useState("");const [value,setValue]=useState("");const [accepted,setAccepted]=useState(false);const [busy,setBusy]=useState(false);const [refresh,setRefresh]=useState(0);
 useEffect(()=>{let active=true;setCard(null);setError(null);setReason("");setValue("");setAccepted(false);
  void getQuestionCard(caseView.id,issue.id).then(c=>{if(active)setCard(c);}).catch(e=>{if(active)setError(errorMessage(e));});return()=>{active=false;};
 },[caseView.id,caseView.version,issue.id,currentRole,refresh]);
 async function submit(){
  if(!card)return;setBusy(true);setError(null);
  try{const result=await submitCard(caseView.id,card,reason.trim(),value.trim(),card.corrections[0]?.id);onCase(result.case_view);}
  catch(e){setError(errorMessage(e));}finally{setBusy(false);}
 }
 if(!card)return <div className="p-4 border rounded text-xs">{error?<><p role="alert">{error}</p><button type="button" onClick={()=>setRefresh(n=>n+1)}>Tải lại căn cứ</button></>:"Đang tải căn cứ và quyền xử lý…"}</div>;
 const numeric=issue.field_or_rule.endsWith(":employee_paid");
 const enabled=!busy&&reason.trim().length>=12&&(card.response_kind!=="DECISION"||card.actions.length>0&&card.actions.every(a=>a.authorized))&&(card.response_kind!=="FACT"||value.trim().length>0)&&(card.response_kind!=="CORRECT_DECLARATION"||accepted);
 return <article data-testid={`question-${card.kind}`} className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-xs">
  <div><p className="text-[11px] font-semibold uppercase text-slate-500">{{FACT:"Dữ kiện cần xác minh",POLICY:"Ngoại lệ chính sách",AUTHORITY:"Thẩm quyền phê duyệt"}[card.kind]} · {{employee:"Nhân viên",accountant:"Kế toán",approver:"Người phê duyệt"}[card.owner]??card.owner}</p><h3 className="mt-1 text-sm font-semibold text-slate-900">{card.required_answer}</h3></div>
  <div className="grid gap-2 sm:grid-cols-2">{card.known_facts.map((fact,i)=><p key={i} className="rounded bg-slate-50 px-3 py-2 text-slate-700">{fact}</p>)}</div>
  <section aria-label="Trích dẫn nguồn cho căn cứ" className="space-y-2">
   {card.excerpt_refs.map((ref,i)=><div key={i} className="border-l-2 border-slate-200 pl-3">
    <p className="text-slate-500">{onSourceSelected&&caseView.sources.some(s=>s.id===ref.source_id)?<button type="button" className="font-semibold text-sky-700 underline" onClick={()=>onSourceSelected(ref.source_id)}>{caseView.sources.find(s=>s.id===ref.source_id)?.filename??ref.source_id}</button>:caseView.sources.find(s=>s.id===ref.source_id)?.filename??(ref.source_id.startsWith("declaration:")?"Kê khai điều chỉnh của nhân viên":ref.source_id)} · trang {ref.page??"khai báo"}</p>
    <blockquote className="mt-1 whitespace-pre-wrap text-slate-800">{ref.exact_quote}</blockquote>
    {ref.bbox&&<OcrRegionView caseView={caseView} reference={ref} onSourceSelected={onSourceSelected}/>}
   </div>)}
  </section>
  {card.response_kind==="DECISION"&&<div className="space-y-2 rounded border border-amber-200 bg-amber-50 p-3">{card.actions.map(action=><div key={action.action}><p className="font-semibold">{action.label}: {formatVnd(action.amount)}</p><p>Quyền hiện tại: {action.limit===null?"Chưa có":formatVnd(action.limit)}</p>{action.unavailable_reason&&<p className="text-amber-900">{action.unavailable_reason}</p>}</div>)}</div>}
  {card.response_kind==="CORRECT_DECLARATION"&&<div className="space-y-3 rounded border border-amber-200 p-3">
   <p className="font-semibold">Bản kê khai điều chỉnh — không sửa PDF hoặc xác nhận đã hoàn tiền</p>
   {card.corrections[0]?.changes.map((c,i)=><p key={i}>{FIELD_NAMES[c.field]??c.field}{c.row_id?` (${c.row_id})`:""}: <strong>{formatVnd(c.before)}</strong> → <strong>{formatVnd(c.after)}</strong></p>)}
   <label className="flex gap-2"><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>Tôi chịu trách nhiệm về kê khai điều chỉnh; chứng từ gốc được giữ nguyên trong lịch sử.</label>
  </div>}
  {card.response_kind==="FACT"&&<label className="block space-y-1"><span className="font-medium">{numeric?`Số tiền VND nhân viên trực tiếp thanh toán cho hóa đơn ${issue.field_or_rule.slice(8,-14)}`:"Dữ kiện bổ sung cho đúng khoản này"}</span>{numeric?<input aria-label="Dữ kiện bổ sung" type="number" min="1" step="1" value={value} onChange={e=>setValue(e.target.value)} className="w-full rounded border p-2"/>:<textarea aria-label="Dữ kiện bổ sung" value={value} onChange={e=>setValue(e.target.value)} className="w-full rounded border p-2"/>}</label>}
  {card.response_kind==="REPLACE_SOURCE"?<p className="rounded bg-amber-50 p-3">Cần bổ sung hoặc thay thế chứng từ đúng từ người phát hành. Văn bản “đồng ý” không giải quyết được mâu thuẫn nguồn này.</p>:card.response_kind==="HISTORY"?<p>Chuyển sang tab Sổ cái & Dòng tiền để đối chiếu giao dịch. Không dùng giải trình văn bản để xác nhận tiền.</p>:<>
   <label className="block space-y-1"><span className="font-medium">{card.response_kind==="DECISION"?"Lý do quyết định":card.response_kind==="CORRECT_DECLARATION"?"Lý do điều chỉnh":"Lý do / xác nhận cụ thể"}</span><textarea aria-label={card.response_kind==="DECISION"?"Lý do quyết định":card.response_kind==="CORRECT_DECLARATION"?"Lý do điều chỉnh":"Lý do / xác nhận cụ thể"} value={reason} onChange={e=>setReason(e.target.value)} className="w-full rounded border border-slate-300 p-2"/></label>
   <button type="button" disabled={!enabled} onClick={()=>void submit()} className="rounded bg-slate-950 px-4 py-2 font-semibold text-white disabled:opacity-40">{busy?"Đang áp dụng…":card.response_kind==="DECISION"?"Phê duyệt các hành động trên":card.response_kind==="CORRECT_DECLARATION"?"Lưu bản kê khai điều chỉnh":"Gửi dữ kiện bổ sung"}</button>
  </>}
  <p className="text-[11px] text-slate-500">{card.effects}</p>
  {error&&<p role="alert" className="rounded bg-rose-50 p-2 text-rose-800">{error}</p>}
 </article>;
}
