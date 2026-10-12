// Demo persona picker: avatar + name + role badge with a native select overlay.
// Extracted from App.tsx; props-only. Demo role selection is not authenticated
// company identity.
import { getInitials, roleLabel } from '../displayText';
import type { DemoRole } from '../types';

export interface PersonaOption {
  actorRef: string;
  label: string;
}

interface PersonaPickerProps {
  role: DemoRole;
  selectedPersonName: string | null;
  selectedActorRef: string;
  people: PersonaOption[];
  onChange: (actorRef: string) => void;
}

export function PersonaPicker({
  role, selectedPersonName, selectedActorRef, people, onChange,
}: PersonaPickerProps) {
  return (
    <div className="profile-chip" title="Nhấp để chuyển đổi vai trò người dùng">
      <label htmlFor="demo-person" className="sr-only">
        Người dùng demo
      </label>
      <div className={`profile-avatar profile-avatar-${role.toLowerCase()}`}>
        {getInitials(selectedPersonName || '')}
      </div>
      <div className="profile-info">
        <span className="profile-name">{selectedPersonName || 'Chưa chọn'}</span>
        <span className={`profile-role-badge badge-role-${role.toLowerCase()}`}>
          {roleLabel(role)}
        </span>
      </div>
      <svg
        className="profile-caret"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
      <select
        id="demo-person"
        className="profile-select-overlay"
        value={selectedActorRef}
        onChange={(e) => {
          onChange(e.target.value);
          e.target.blur();
        }}
        title="Chọn vai trò người dùng"
      >
        {people.length === 0 && (
          <option value="">Chưa tải được người dùng demo.</option>
        )}
        {people.map(({ actorRef, label }) => (
          <option key={actorRef} value={actorRef}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
}
