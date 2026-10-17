"""Server-built cards and transactional decision validation. No provider I/O."""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from invoice_referee.domain.policy import ActionAuthorization
from invoice_referee.domain.issues import BusinessIssue,QuestionCard,QuestionAction
from invoice_referee.reconciliation.authority import fingerprint,authorization_basis,grants_for
from invoice_referee.reconciliation.service import Reconciler

LABELS={"RECOGNIZE_COST":"Công nhận chi phí","ISSUE_PAYMENT":"Phát hành yêu cầu chi","ISSUE_COLLECTION":"Phát hành yêu cầu thu","EXCEPT_POLICY":"Chấp nhận ngoại lệ chứng từ"}
def money(amount):return f"{amount:,}".replace(",",".")+" đ"

def with_authorizations(cx,row,input):
    if input is None:return None
    records=tuple(ActionAuthorization.model_validate_json(r["payload_json"])for r in cx.execute("SELECT payload_json FROM case_authority_decisions WHERE tenant=? AND root_id=? ORDER BY decided_at,rowid",(row["tenant"],row["id"])))
    issued={}
    for order in cx.execute("SELECT authority_refs_json,created_at,amount,fulfilled_amount FROM instructions WHERE root_id=? AND tenant=? AND status IN ('ISSUED','PARTIAL','FULFILLED','SUSPENDED','EXECUTION_UNKNOWN')",(row["id"],row["tenant"])):
        for identifier in json.loads(order["authority_refs_json"] or "[]"):
            issued[identifier]=(datetime.fromisoformat(order["created_at"]),max(int(order["amount"])-int(order["fulfilled_amount"]),0))
    records=tuple(d.model_copy(update={"issued_at":issued[d.id][0],"remaining_issued":issued[d.id][1]})if d.id in issued else d for d in records)
    return input.model_copy(update={"authorizations":records})

def current_basis(row,input,issues):
    return "card:"+fingerprint({"version":row["version"],"revision":row["input_revision"],"epoch":row["control_epoch"],"issues":[i.model_dump(mode="json")for i in issues],"scope":input.scope.model_dump(mode="json"),"grants":[g.model_dump(mode="json")for g in input.grants],"cost":authorization_basis(input,"RECOGNIZE_COST"),"money":authorization_basis(input,"ISSUE_PAYMENT")})

def build_card(wf,cx,session,row,issue_id):
    from invoice_referee.workflow.service import UnsupportedCommandError,NotFoundError
    stored=cx.execute("SELECT payload_json,status FROM case_issues WHERE id=? AND root_id=? AND tenant=?",(issue_id,row["id"],row["tenant"])).fetchone()
    if stored is None or stored["status"]!="OPEN":raise NotFoundError("Vấn đề không còn mở trong hồ sơ này.")
    issue=BusinessIssue.model_validate_json(stored["payload_json"])
    input=wf._build_assessment_input(cx,session,row,wf._now_iso())
    if input is None:raise UnsupportedCommandError("Chưa có dữ liệu đủ để lập thẻ. Hãy hoàn tất đọc chứng từ.")
    result=Reconciler().assess(input)
    current=tuple(result.issues)
    fresh=next((i for i in current if i.kind==issue.kind and i.field_or_rule==issue.field_or_rule),None)
    if fresh is None:raise UnsupportedCommandError("Căn cứ đã thay đổi; tải lại hồ sơ và đối soát trước khi xử lý.")
    # Persisted workflow IDs are stable per root; bind their source/meaning to
    # the fresh assessment, not a client-supplied translated message.
    if fingerprint((issue.basis,issue.question,issue.refs))!=fingerprint((fresh.basis,fresh.question,fresh.refs)):
        raise UnsupportedCommandError("Vấn đề đã đổi căn cứ; tải lại kết quả đối soát.")
    visible=tuple(BusinessIssue.model_validate_json(r["payload_json"])for r in cx.execute("SELECT payload_json FROM case_issues WHERE root_id=? AND status='OPEN' ORDER BY rowid",(row["id"],)))
    selected=[i for i in visible if i.kind=="AUTHORITY"] if issue.kind=="AUTHORITY" else [issue]
    actions=[]
    for item in selected:
        if item.kind=="AUTHORITY":
            action=item.field_or_rule
            if action=="RECOGNIZE_COST":amount=result.projection.E.value
            elif action in ("ISSUE_PAYMENT","ISSUE_COLLECTION"):amount=abs(result.projection.S.value) if result.projection.S.state=="KNOWN" else None
            else:continue
        elif item.kind=="POLICY" and item.field_or_rule.endswith(":missing_evidence"):
            action="EXCEPT_POLICY";parts=item.field_or_rule.split(":");amount=wf._exception_expense_amount(cx,row["id"],":".join(parts[:2]))
        else:continue
        if amount is None:continue
        all_grants=grants_for(input,session.actor_id,action)
        limit=max((g.max_amount for g in all_grants),default=None)
        ok=bool(grants_for(input,session.actor_id,action,int(amount))) and row["state"]!="STOPPED" and session.actor_id!=row["employee"] and session.persona in ("approver","accountant")
        reason=None if ok else (f"Cần cấp có quyền cao hơn: số cần quyết định {money(amount)}; quyền hiện tại {money(limit) if limit is not None else 'chưa có'}." if row["state"]!="STOPPED" else "Hồ sơ đã dừng.")
        actions.append(QuestionAction(issue_id=item.id,action=action,label=LABELS[action],scope=row["activity"],amount=int(amount),limit=limit,authorized=ok,unavailable_reason=reason))
    facts=[]
    for key,label in [("E","Chi phí đủ điều kiện"),("A","Ứng thực nhận"),("P","Công ty đã chi bổ sung"),("R","Nhân viên đã hoàn"),("S","Chênh lệch")]:
        value=getattr(result.projection,key)
        facts.append(label+": "+(money(value.value) if value.state=="KNOWN" else "Chưa xác minh"))
    response="DECISION" if actions else "REPLACE_SOURCE"
    if issue.kind=="FACT" and (issue.field_or_rule=="expense:payer" or issue.field_or_rule.endswith(":employee_paid") or issue.field_or_rule.endswith(":exception_reason")):
        response="FACT"
    if issue.kind=="POLICY" and not actions:response="REPLACE_SOURCE"
    if "arithmetic" in issue.field_or_rule or "allocation" in issue.field_or_rule:response="REPLACE_SOURCE"
    if issue.field_or_rule=="ledger:coverage":response="HISTORY"
    corrections=()
    if response=="REPLACE_SOURCE" and issue.kind=="FACT":
        from invoice_referee.workflow.declaration_corrections import options,effective_report
        from invoice_referee.domain.evidence import ReadResult
        raw=cx.execute("SELECT report_json FROM case_evidence_reports WHERE root_id=?",(row["id"],)).fetchone()
        if raw is not None:
            corrections=options(effective_report(cx,row,ReadResult.model_validate_json(raw["report_json"])),issue)
            if corrections:response="CORRECT_DECLARATION"
    required_answer=issue.question
    if actions:
        action_text="; ".join(f"{a.label.lower()} {money(a.amount)}" for a in actions)
        required_answer=f"Bạn có chấp thuận {action_text} cho hồ sơ này không? Quyết định chưa ghi nhận tiền đã chi/thu."
        facts[0]="Quyền tự xử lý của hệ thống: công nhận chi phí tối đa 8.000.000 đ; phát hành yêu cầu chi/thu tối đa 4.000.000 đ."
    elif corrections:
        change=corrections[0].changes[0]
        field_label={"printed_return":"số hoàn lại","printed_reimbursement":"số đề nghị chi thêm","amount":"khoản chi"}.get(change.field,"số kê khai")
        required_answer=f"Giấy kê khai {field_label} {money(change.before)} nhưng căn cứ đối chiếu cho {money(change.after)} (lệch {money(abs(change.before-change.after))}). Bạn điều chỉnh kê khai theo căn cứ này hay cần bổ sung chứng từ?"
        facts[0]="Số trên giấy gốc vẫn được giữ trong lịch sử; số điều chỉnh là kê khai mới của nhân viên."
    refs=tuple(dict.fromkeys(ref for item in selected for ref in item.refs))
    return QuestionCard(issue_id=issue.id,case_version=int(row["version"]),basis_id=current_basis(row,input,visible),kind=issue.kind,scope=row["activity"],title="Quyết định trong phạm vi được cấp" if actions else issue.question,response_kind=response,known_facts=tuple([issue.basis,*facts]),excerpt_refs=refs,required_answer=required_answer,effects="Phản hồi chỉ xử lý vấn đề này. Không ghi nhận tiền đã chi/thu; dữ kiện độc lập vẫn có thể chặn hồ sơ.",owner=issue.owner,actions=tuple(actions),corrections=corrections)

def persist_decision(wf,cx,session,context,row,decision):
    from invoice_referee.workflow.service import UnsupportedCommandError
    wf._require_version(row,context.expected_case_version)
    if row["state"]=="STOPPED":raise UnsupportedCommandError("Hồ sơ đã dừng; không áp dụng quyết định.")
    if not decision.issue_ids or len(set(decision.issue_ids))!=len(decision.issue_ids) or not decision.actions or len(set(decision.actions))!=len(decision.actions):raise UnsupportedCommandError("Chọn đúng vấn đề và hành động; không được rỗng hoặc lặp.")
    card=build_card(wf,cx,session,row,decision.issue_ids[0])
    if card.response_kind!="DECISION":raise UnsupportedCommandError("FACT cần xác minh/sửa căn cứ; không thể phê duyệt để bỏ qua.")
    if decision.basis_id!=card.basis_id or decision.effect_scope!=row["activity"]:raise UnsupportedCommandError("Căn cứ/phạm vi quyết định đã thay đổi. Tải lại thẻ.")
    if set(decision.issue_ids)!={a.issue_id for a in card.actions} or set(decision.actions)!={a.action for a in card.actions}:raise UnsupportedCommandError("Quyết định phải khớp đầy đủ các hành động đang được yêu cầu.")
    if any(not a.authorized for a in card.actions):raise UnsupportedCommandError("Không đủ quyền cho toàn bộ quyết định; cần cấp cao hơn.")
    amounts={a.amount for a in card.actions}
    if decision.amount is not None and (len(amounts)!=1 or decision.amount not in amounts):raise UnsupportedCommandError("Số tiền client không khớp số tiền từng hành động do server xác định.")
    if not decision.reason.strip():raise UnsupportedCommandError("Cần nêu lý do quyết định.")
    input=wf._build_assessment_input(cx,session,row,wf._now_iso());now=wf._now_iso()
    if "EXCEPT_POLICY" in decision.actions:
        if len(card.actions)!=1:raise UnsupportedCommandError("Ngoại lệ chứng từ xử lý từng khoản, không duyệt gộp.")
        parts=card.actions[0].issue_id
        issue=cx.execute("SELECT field_or_rule FROM case_issues WHERE id=? AND root_id=?",(parts,row["id"])).fetchone()
        prefix=":".join(issue["field_or_rule"].split(":")[:2])+":"
        if any(i.kind=="FACT" and i.field_or_rule.startswith(prefix) for i in Reconciler().assess(input).issues):raise UnsupportedCommandError("Khoản chi còn mâu thuẫn dữ kiện; ngoại lệ không bỏ qua FACT.")
        if decision.refs and any(ref not in card.excerpt_refs for ref in decision.refs):
            raise UnsupportedCommandError("Căn cứ ngoại lệ không khớp nguồn đang được đối soát.")
        wf._persist_exception_decisions(cx,session,row,context,decision.model_copy(update={"amount":card.actions[0].amount,"refs":card.excerpt_refs}),now)
    else:
        for action in card.actions:
            grant=grants_for(input,session.actor_id,action.action,action.amount)[0]
            source=cx.execute("SELECT payload_json FROM case_issues WHERE id=? AND root_id=?",(action.issue_id,row["id"])).fetchone()
            issue=BusinessIssue.model_validate_json(source["payload_json"])
            record=ActionAuthorization(id="decision:"+uuid.uuid4().hex,action=action.action,amount=action.amount,activity=row["activity"],actor=session.actor_id,grant_ref=grant.id,grant_fingerprint=fingerprint(grant),basis=authorization_basis(input,action.action),decided_at=datetime.fromisoformat(now),reason=decision.reason,refs=issue.refs)
            cx.execute("INSERT INTO case_authority_decisions(id,tenant,root_id,action,payload_json,decided_at) VALUES(?,?,?,?,?,?)",(record.id,row["tenant"],row["id"],record.action,record.model_dump_json(),now))
    cx.execute("UPDATE cases SET version=version+1,updated_at=? WHERE id=?",(now,row["id"]))
    wf._audit(cx,tenant=session.tenant,root_id=row["id"],session_id=session.session_id,actor=context.actor_id,action="DECIDE",detail=json.dumps({"issue_ids":list(decision.issue_ids),"basis":card.basis_id,"effects":[a.model_dump(mode="json")for a in card.actions],"reason":decision.reason},ensure_ascii=False))
