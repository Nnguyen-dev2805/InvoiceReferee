// Shell only: the automated Verify runner is wired in T11. This deliberately
// shows NO simulated pass/fail — a fabricated verdict would misrepresent the
// harness, so the panel states it is not yet available.
export function VerifyPanel() {
  return (
    <section className="panel" aria-labelledby="verify-heading">
      <h2 id="verify-heading">Bộ kiểm thử tự động (Verify)</h2>
      <p className="muted">
        Bộ kiểm thử Core/Escalation sẽ chạy cùng đường xử lý production. Tính năng này
        chưa được nối trong bản hiện tại; không hiển thị kết quả mô phỏng.
      </p>
    </section>
  );
}
