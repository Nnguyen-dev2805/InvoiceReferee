"""Generate the25 current demo contexts from the reviewed README and source PDFs.

Authoring only: no application database, providers, gold or financial outputs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
from invoice_referee.domain.organization import OrganizationContext

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data/demo"
AS_OF = "2026-10-17T23:59:59+07:00"
START = "2026-10-01T00:00:00+07:00"
END = "2026-12-31T23:59:59+07:00"
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
APPROVER = "employee:approver"
TRAVEL = {3,16,19,20,24,25}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing symlink output: {path}")
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def shared_context() -> dict:
    return dict(tenant="tenant:demo",organization_id="tenant:demo",company_name=COMPANY,
                company_tax_id="0319999996",profile="WORK_EXPENSE",data_origin="SIMULATED",
                records=["Danh tính, quyền và chính sách công ty là dữ liệu mô phỏng độc lập với chứng từ chi phí."],
                people=[dict(id=EMPLOYEE,name="NGUYỄN MINH AN"),
                        dict(id=ACCOUNTANT,name="Trần Thị B (kế toán)"),
                        dict(id=APPROVER,name="Lê Văn C (người quyết định)")])


def grants(scope: str) -> list[dict]:
    definitions=[("recognize","system:referee",["RECOGNIZE_COST"],8_000_000),
                 ("issue","system:referee",["ISSUE_PAYMENT","ISSUE_COLLECTION"],4_000_000),
                 ("approver",APPROVER,["AUTHORIZE_ACTIVITY","RECOGNIZE_COST","EXCEPT_POLICY",
                                        "ISSUE_PAYMENT","ISSUE_COLLECTION","OVERRIDE"],20_000_000),
                 ("accountant",ACCOUNTANT,["CONFIRM_FINANCIAL_FACT","RECORD_ACTUAL","STOP","RESUME"],120_000_000)]
    return [dict(id=f"grant:{scope}:{name}",version="uc03-v1",actor=actor,actions=actions,
                 scope=scope,max_amount=limit,effective_from=START,effective_to=END,
                 allowed_profiles=["TRAVEL","WORK_EXPENSE"])
            for name,actor,actions,limit in definitions]


def policies() -> tuple[list[dict],list[dict]]:
    base=[]; category=[]
    for profile in ("TRAVEL","WORK_EXPENSE"):
        base.append(dict(id=f"policy:uc03:{profile}",version="uc03-v1",profile=profile,
                         effective_from=START,effective_to=END,rules=["EMPLOYEE_PAID_INVOICE_BOUNDED"]))
        category.append(dict(id=f"category:uc03:{profile}",version="uc03-v1",profile=profile,
                             effective_from=START,effective_to=END,
                             per_item_caps={"CLIENT_MEAL":5_000_000,"WORK_CLIENT_MEAL":5_000_000,"TAXI":2_000_000},
                             submission_window_days=30,excluded_categories=["PERSONAL"]))
    return base,category


def generate(output: Path = DEMO) -> dict:
    if output.is_symlink():
        raise ValueError("Refusing symlink output")
    output=output.resolve()
    if output.exists() and output!=DEMO.resolve() and any(output.iterdir()) and not (output/".uc03-context-managed").exists():
        raise ValueError("Refusing non-empty unmanaged output")
    readme=(DEMO/"README.md").read_text()
    rows=re.findall(r'^\| \[TC(\d{2})\]\((\.\./tham-khao/uc-03/[^)]+/)\) \| ([^|]+) \| ([^|]+) \|',readme,re.M)
    if [int(row[0]) for row in rows]!=list(range(1,26)):
        raise ValueError("README must identify exactly TC01 through TC25")
    common=shared_context()
    common["policies"],common["category_policies"]=policies()
    common["grants"]=grants("tenant:demo")
    common["activities"]=[]
    common["ledger"]=[]
    common["coverages"]=[]
    common["witnesses"]=[]
    common["financial_as_of"]=AS_OF
    manifest=dict(schema_version="uc03-contexts/v1",data_origin="SIMULATED",assessment_at=AS_OF,
                  company_tax_id="0319999996",cases=[],
                  notes=["Context giả lập là precondition, không là kết quả OCR/ngân hàng.",
                         "Context chung nạp25 khoản ứng, mỗi khoản/lịch sử thuộc đúng một activity; context riêng vẫn dùng cho test cô lập.",
                         "Mốc hoạt động 10/10 là lịch công việc giả lập; không tạo trip_start/trip_end từ ngày hóa đơn.",
                         "Quyền kế toán120 triệu chỉ ghi nhận sự kiện tiền đã xảy ra; không cho duyệt chi phí vượt20 triệu.",
                         "company_tax_id được lưu/đọc qua context; không thay thế việc kiểm gate MST trong ứng dụng."])
    for number,relative,_cost,advance_text in rows:
        index=int(number); case_id=f"TC{number}"; activity_id=f"activity:tc{number}"
        source=(DEMO/relative).resolve()
        if source.parent != (ROOT/"data/tham-khao/uc-03").resolve():
            raise ValueError("Source outside the25-case reference directory")
        text="\n".join(page.extract_text() or "" for page in PdfReader(source/"report_hoan_ung.pdf").pages)
        purpose=re.search(r'Nội dung:\s*([^\n]+)',text)
        declared=re.search(r'Số tiền đã tạm ứng:\s*([\d.]+)',text)
        amount=int(Decimal(advance_text.strip().replace(",","."))*1_000_000)
        if not purpose or not declared or int(declared[1].replace(".",""))!=amount:
            raise ValueError(f"README/source advance or purpose mismatch: {case_id}")
        profile="TRAVEL" if index in TRAVEL else "WORK_EXPENSE"
        activity=dict(activity_id=activity_id,name=f"{case_id} — {purpose[1]}",purpose=purpose[1],
                      occurred_at="2026-10-10T09:00:00+07:00",profile=profile,status="AUTHORIZED",
                      references=[f"TU-{case_id}"],
                      authorization=dict(id=f"auth:{case_id}",actor=APPROVER,
                          reason="Phạm vi quyết toán giả lập; không phê duyệt tính hợp lệ từng khoản chi."))
        common["activities"].append(deepcopy(activity))
        ctx=shared_context(); ctx["profile"]=profile; ctx["activity"]=activity
        ctx["policies"],ctx["category_policies"]=policies()
        ctx["grants"]=grants(activity_id)
        ctx["financial_as_of"]=AS_OF
        ctx["ledger"]=[dict(id=f"advance:tc{number}",external_key=f"transfer:FT-{case_id}-0001",
                            kind="ADVANCE_RECEIVED",scope=activity_id,payer=COMPANY,payee=EMPLOYEE,amount=amount,
                            event_at="2026-10-05T09:00:00+07:00",recorded_at="2026-10-05T10:00:00+07:00",
                            verification_state="CONFIRMED",allocation_state="ALLOCATED",
                            reverses_event_id=None)]
        ctx["coverage"]=dict(employee=EMPLOYEE,activity=activity_id,start=START,as_of=AS_OF,
                             fund_ids=["company:bank-demo"],
                             flow_kinds=["ADVANCE_RECEIVED","REIMBURSEMENT_RECEIVED","EMPLOYEE_RETURN",
                                         "REVERSAL","OBSERVED_UNALLOCATED"],
                             opening_by_fund={"company:bank-demo":0},ledger_version=f"ledger:{case_id}:initial-v1",
                             witness_keys=[f"coverage:{case_id}"])
        ctx["witnesses"]=[dict(record_key=f"advance:tc{number}",actor=ACCOUNTANT,scope=activity_id,
                               observed_at="2026-10-05T10:00:00+07:00",
                               quote=f"Fixture độc lập: công ty đã ứng thực nhận {amount} VND cho Nguyễn Minh An, {activity_id}; không suy từ giấy quyết toán."),
                          dict(record_key=f"coverage:{case_id}",actor=ACCOUNTANT,scope=activity_id,observed_at=AS_OF,
                               quote=f"Sổ hồ sơ giả lập {activity_id}: đúng một khoản ứng {amount} VND; đầu kỳ0; chưa chi bổ sung, chưa hoàn, chưa đảo và chưa có khoản chưa phân bổ đến {AS_OF}.")]
        common["ledger"].extend(deepcopy(ctx["ledger"]))
        common["coverages"].append(deepcopy(ctx["coverage"]))
        common["witnesses"].extend(deepcopy(ctx["witnesses"]))
        ui=deepcopy(ctx);ui["ledger"]=[];ui["coverage"]=None;ui["witnesses"]=[]
        folder=Path("cases")/source.name
        if not (output/folder).resolve().is_relative_to(output):
            raise ValueError("Refusing output directory symlink outside context pack")
        for name,payload in (("context.json",ctx),("context-ui.json",ui)):
            normalized=json.loads(OrganizationContext.model_validate_json(json.dumps(payload,ensure_ascii=False)).model_dump_json())
            normalized.pop("budget_amount",None)
            normalized.pop("budgets",None)
            write_json(output/folder/name,normalized)
        files=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
               for p in sorted(source.glob("*.pdf"))]
        manifest["cases"].append(dict(case_id=case_id,context=str(folder/"context.json"),
                                     context_ui=str(folder/"context-ui.json"),profile=profile,
                                     requires_predecessor="TC01" if index==12 else None,
                                     sources=files,
                                     prerequisites=["TC12 cần hồ sơ khác đã tiêu thụ invoice của TC01; không dùng boolean duplicate."] if index==12 else []))
    normalized_common=json.loads(OrganizationContext.model_validate_json(json.dumps(common,ensure_ascii=False)).model_dump_json())
    normalized_common.pop("budget_amount",None)
    normalized_common.pop("budgets",None)
    write_json(output/"company-context.json",normalized_common)
    write_json(output/"manifest.json",manifest)
    # Keep the existing TC01 PDF generator and transfer/cash runbooks compatible.
    tc01=json.loads((output/manifest["cases"][0]["context"]).read_text())
    write_json(output/"tc01-company-context.json",tc01)
    receipts=output/"tc01-chung-tu-ung"
    if receipts.is_dir():
        for label,method,reference,fund in (("chuyen-khoan","transfer","FT-TC01-0001","company:bank-demo"),
                                          ("tien-mat","cash","PC-TC01-0001","company:cash-demo")):
            variant=deepcopy(tc01)
            variant["ledger"][0]["external_key"]=f"{method}:{reference}"
            variant["coverage"]["fund_ids"]=[fund]
            variant["coverage"]["opening_by_fund"]={fund:0}
            write_json(receipts/f"context-{label}.json",variant)
        receipt_manifest=receipts/"manifest.json"
        if receipt_manifest.is_file():
            existing=json.loads(receipt_manifest.read_text())
            for name in ("context-chuyen-khoan.json","context-tien-mat.json"):
                existing["files"][name]=hashlib.sha256((receipts/name).read_bytes()).hexdigest()
            write_json(receipt_manifest,existing)
    (output/".uc03-context-managed").write_text("UC03 context pack v1\n")
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=DEMO)
    args=parser.parse_args()
    result=generate(args.output)
    print(f"Generated {len(result['cases'])} cases, 50 scoped contexts and one common catalog; no PDF/gold/DB changes.")
