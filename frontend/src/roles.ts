// Role workspaces (plan R6, UX01): each persona sees only its own panels.
//
// This is a UI convenience, not a permission: the backend still denies any
// action the actor's grants do not cover. The mapping keeps the demo honest —
// an employee does not get the accountant's money-recording form, and the
// accountant does not get the employee's intake form.

export type Persona = "employee" | "accountant" | "approver";

export type Panel =
  | "intake"
  | "questions"
  | "approval"
  | "execution"
  | "controls"
  | "dossier";

const WORKSPACES: Record<Persona, Panel[]> = {
  employee: ["intake", "questions", "dossier"],
  accountant: ["approval", "execution", "controls", "dossier"],
  approver: ["approval", "questions", "controls", "dossier"],
};

export function roleWorkspaces(persona: Persona | string): Panel[] {
  return WORKSPACES[persona as Persona] ?? ["dossier"];
}
