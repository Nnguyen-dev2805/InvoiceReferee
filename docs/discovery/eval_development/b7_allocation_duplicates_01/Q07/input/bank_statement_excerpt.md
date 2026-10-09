# Nguồn giả lập — Excerpt phía tài khoản công ty

NamespaceBANK-DEMO-A, bankexportsynthetic, ngày04/10/2026. RawstatusPOSTED chỉ mô tả debit/accountposted, không tựvendoractualreceipt; actualreceiptcurrentevent đọcvendorreceipt trongpacket.

## current-bank-row

BankrefBNK-A44: tài khoảnORG-DEMO-01 debit3.000.000VND tớiVENDOR-AIR-01, memoBOOK-DEMO-01, posted04/10. Không eventIDTX-AIR-001 trongnamespacebank, đó là ref riêngcủafinance.

## other-bank-row

BankrefBNK-A45: cùngpayerORG-DEMO-01/payeeVENDOR-AIR-01, cùngdate04/10 và debit3.000.000VND, memoBOOK-OTHER-99. Là một recordbankkhác, không sourcecopycủaBNK-A44. Quan hệwork đọcfinance-register tươngứng; không ghép theoamount/datealone.
