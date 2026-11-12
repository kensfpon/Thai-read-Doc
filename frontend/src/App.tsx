import { useEffect, useState } from "react";

type BackendState = "checking" | "ok" | "unreachable";

const LABELS: Record<BackendState, string> = {
  checking: "กำลังตรวจสอบ backend…",
  ok: "เชื่อมต่อ backend แล้ว",
  unreachable: "ติดต่อ backend ไม่ได้",
};

// Phase 0 placeholder: the real screens (DESIGN.md section 6) arrive in Phase 3.
export function App() {
  const [state, setState] = useState<BackendState>("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => setState(response.ok ? "ok" : "unreachable"))
      .catch(() => setState("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>HART Reader</h1>
      <p role="status">{LABELS[state]}</p>
    </main>
  );
}
