import {newCommandId,request} from "../api";
import type {CommandResultView,EvidenceRefView} from "../types";
export interface ServerQuestionCard {
 issue_id:string;case_version:number;basis_id:string;kind:"FACT"|"POLICY"|"AUTHORITY";scope:string;title:string;
 response_kind:"FACT"|"DECISION"|"CORRECT_DECLARATION"|"REPLACE_SOURCE"|"HISTORY";
 known_facts:string[];excerpt_refs:EvidenceRefView[];required_answer:string;effects:string;owner:string;
 actions:Array<{issue_id:string;action:string;label:string;scope:string;amount:number;limit:number|null;authorized:boolean;unavailable_reason:string|null}>;
 corrections:Array<{id:string;label:string;changes:Array<{field:string;row_id:string|null;before:number;after:number}>}>;
}
export const getQuestionCard=(root:string,issue:string)=>request<ServerQuestionCard>(`/api/cases/${root}/issues/${issue}/card`);
export function submitCard(root:string,card:ServerQuestionCard,reason:string,value:string,correctionId?:string){
 let path:string;let body:unknown;
 if(card.response_kind==="DECISION"){
  const amounts=new Set(card.actions.map(a=>a.amount));
  path=`/api/cases/${root}/decisions`;
  body={issue_ids:card.actions.map(a=>a.issue_id),basis_id:card.basis_id,actions:card.actions.map(a=>a.action),effect_scope:card.scope,amount:amounts.size===1?card.actions[0].amount:null,reason};
 }else if(card.response_kind==="CORRECT_DECLARATION"){
  path=`/api/cases/${root}/issues/${card.issue_id}/corrections`;
  body={basis_id:card.basis_id,correction_id:correctionId,reason};
 }else{
  path=`/api/cases/${root}/answers`;
  body={issue_id:card.issue_id,basis_id:card.basis_id,answer_kind:"FACT",value,reason};
 }
 return request<CommandResultView>(path,body,newCommandId(),card.case_version);
}
