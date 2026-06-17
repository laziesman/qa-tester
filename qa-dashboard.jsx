import React, { useState, useMemo } from "react";
import {
  Search, ChevronRight, ChevronDown, Check, X, SkipForward, Clock,
  Filter, LayoutGrid, ArrowUpRight, Image as ImageIcon, Maximize2,
} from "lucide-react";

// ---- Design tokens -------------------------------------------------------
// Dark, calm surface. One disciplined semantic palette for test states.
// Display: Space Grotesk for numbers/headers. Body: IBM Plex Sans Thai for
// crisp Thai rendering. Mono utility for IDs (TC-003, #403).
const C = {
  pass: "#3ECF8E",
  fail: "#F2555A",
  skip: "#E5B95C",
  pending: "#5B6472",
  bg: "#0E1116",
  panel: "#151A21",
  panel2: "#1B212A",
  line: "#242C37",
  text: "#E6EAF0",
  dim: "#8A93A2",
  faint: "#5B6472",
};

// ---- Mock data -----------------------------------------------------------
const STATUS = {
  pass: { label: "Pass", color: C.pass, Icon: Check },
  fail: { label: "Fail", color: C.fail, Icon: X },
  skip: { label: "Skip", color: C.skip, Icon: SkipForward },
  pending: { label: "รอตรวจ", color: C.pending, Icon: Clock },
};

const TASKS = [
  { id: "403", title: "ฟอร์มบันทึกประวัติการเปลี่ยนแปลงข้อมูลการทำงานของพนักงาน", pass: 18, fail: 3, skip: 1, pending: 0 },
  { id: "404", title: "ฟอร์มแก้ไขรายการประวัติการเปลี่ยนแปลงที่บันทึกไว้แล้ว", pass: 24, fail: 7, skip: 2, pending: 2 },
  { id: "405", title: "ลบรายการประวัติการเปลี่ยนแปลงที่ไม่ถูกต้อง", pass: 20, fail: 4, skip: 1, pending: 0 },
  { id: "406", title: "หน้าแสดงรายละเอียดของรายการประวัติการทำงานแบบ read-only", pass: 26, fail: 6, skip: 3, pending: 4 },
  { id: "407", title: "หน้าแสดงรายการเอกสารสัญญาทั้งหมดของพนักงาน", pass: 22, fail: 6, skip: 2, pending: 3 },
  { id: "408", title: "ฟอร์มสร้างเอกสารสัญญาใหม่ให้พนักงาน", pass: 28, fail: 7, skip: 4, pending: 5 },
  { id: "409", title: "ฟอร์มแก้ไขเอกสารสัญญาที่บันทึกไว้", pass: 28, fail: 2, skip: 4, pending: 4 },
  { id: "416", title: "อัปเดตข้อมูลปัจจุบันพนักงานเมื่อถึงวันที่มีผล (Cronjob 00:01)", pass: 20, fail: 0, skip: 0, pending: 2 },
];

const TC_DETAIL = {
  "403": [
    {
      id: "TC-003", status: "fail",
      expected: "เมื่อพิมพ์ค้นหาพนักงาน ระบบต้องกรองรายชื่อตามคำค้น",
      actual: "เมื่อพิมพ์ 2 ตัวอักษรใดก็ได้ ระบบจะแสดงพนักงานทั้งหมดออกมา ไม่กรองตามคำค้น",
      shot: "search",
    },
    {
      id: "TC-016", status: "fail",
      expected: "แสดงชื่อแผนก/ฝ่ายของพนักงานให้ถูกต้องตามฐานข้อมูล",
      actual: "การแสดงผลของ แผนก/ฝ่ายใหม่ ไม่ถูกต้อง",
      shot: "dept",
    },
    {
      id: "TC-021", status: "fail",
      expected: "บังคับเลือกประเภทการเปลี่ยนแปลงอย่างน้อย 1 ข้อก่อนบันทึก",
      actual: "กดบันทึกได้โดยไม่เลือกประเภท แต่ขึ้น error หลังบันทึกแล้ว",
      shot: "validate",
    },
  ],
};

// ---- Helpers -------------------------------------------------------------
const total = (t) => t.pass + t.fail + t.skip + t.pending;
const passRate = (t) => Math.round((t.pass / Math.max(total(t), 1)) * 100);

function StackBar({ t, h = 6 }) {
  const sum = total(t);
  const seg = (n) => `${(n / Math.max(sum, 1)) * 100}%`;
  return (
    <div style={{ display: "flex", height: h, borderRadius: h, overflow: "hidden", background: C.line, width: "100%" }}>
      {["pass", "fail", "skip", "pending"].map((k) =>
        t[k] > 0 ? <div key={k} style={{ width: seg(t[k]), background: STATUS[k].color }} /> : null
      )}
    </div>
  );
}

function StatusPill({ status, count }) {
  const s = STATUS[status];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
      padding: "3px 9px", borderRadius: 999, color: s.color,
      background: `${s.color}1A`, border: `1px solid ${s.color}33`,
      fontVariantNumeric: "tabular-nums",
    }}>
      <s.Icon size={12} strokeWidth={3} />
      {count} {s.label}
    </span>
  );
}

// ---- App -----------------------------------------------------------------
export default function App() {
  const [active, setActive] = useState("403");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all"); // all | fail | pending
  const [lightbox, setLightbox] = useState(null);

  const sprint = useMemo(() => {
    const acc = { pass: 0, fail: 0, skip: 0, pending: 0 };
    TASKS.forEach((t) => ["pass", "fail", "skip", "pending"].forEach((k) => (acc[k] += t[k])));
    return acc;
  }, []);
  const sprintTotal = total(sprint);
  const sprintRate = passRate(sprint);

  const visibleTasks = TASKS.filter((t) => {
    if (query && !(`#${t.id} ${t.title}`.toLowerCase().includes(query.toLowerCase()))) return false;
    if (filter === "fail") return t.fail > 0;
    if (filter === "pending") return t.pending > 0;
    return true;
  });

  const activeTask = TASKS.find((t) => t.id === active);
  const detail = TC_DETAIL[active] || [];

  return (
    <div style={{
      display: "flex", height: "100vh", background: C.bg, color: C.text,
      fontFamily: "'IBM Plex Sans Thai', 'Inter', system-ui, sans-serif", fontSize: 14,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-thumb { background: ${C.line}; border-radius: 8px; }
        .num { font-family: 'Space Grotesk', sans-serif; font-variant-numeric: tabular-nums; }
        .mono { font-family: 'IBM Plex Mono', monospace; }
        .row:hover { background: ${C.panel2}; }
        .navitem:hover { background: ${C.panel2}; }
        button { font-family: inherit; cursor: pointer; }
      `}</style>

      {/* ---- Sidebar ---- */}
      <aside style={{ width: 270, background: C.panel, borderRight: `1px solid ${C.line}`, display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: "16px 16px 12px", display: "flex", alignItems: "center", gap: 8, borderBottom: `1px solid ${C.line}` }}>
          <span style={{ width: 8, height: 8, borderRadius: 999, background: C.pass, boxShadow: `0 0 8px ${C.pass}` }} />
          <span style={{ fontWeight: 700, letterSpacing: 0.2 }}>QA Tester</span>
          <LayoutGrid size={15} color={C.faint} style={{ marginLeft: "auto" }} />
        </div>

        <div style={{ padding: 12 }}>
          <div style={{ position: "relative" }}>
            <Search size={14} color={C.faint} style={{ position: "absolute", left: 10, top: 9 }} />
            <input
              value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="ค้นหา task..."
              style={{
                width: "100%", padding: "7px 10px 7px 30px", borderRadius: 8,
                background: C.bg, border: `1px solid ${C.line}`, color: C.text, fontSize: 13, outline: "none",
              }}
            />
          </div>
        </div>

        <div style={{ padding: "0 12px 8px", display: "flex", gap: 6 }}>
          {[["all", "ทั้งหมด"], ["fail", "Fail"], ["pending", "รอตรวจ"]].map(([k, lb]) => (
            <button key={k} onClick={() => setFilter(k)}
              style={{
                flex: 1, padding: "5px 0", fontSize: 12, fontWeight: 600, borderRadius: 7,
                border: `1px solid ${filter === k ? C.line : "transparent"}`,
                background: filter === k ? C.panel2 : "transparent",
                color: filter === k ? C.text : C.dim,
              }}>{lb}</button>
          ))}
        </div>

        <div style={{ padding: "8px 16px 6px", fontSize: 11, fontWeight: 700, letterSpacing: 1, color: C.faint }}>
          SPRINT 5 · HR
        </div>

        <div style={{ overflowY: "auto", flex: 1, padding: "0 8px 12px" }}>
          {visibleTasks.map((t) => {
            const sel = t.id === active;
            return (
              <button key={t.id} className="navitem" onClick={() => setActive(t.id)}
                style={{
                  width: "100%", textAlign: "left", display: "block", padding: "9px 10px",
                  borderRadius: 9, marginBottom: 2, border: "none",
                  background: sel ? C.panel2 : "transparent",
                  boxShadow: sel ? `inset 2px 0 0 ${t.fail > 0 ? C.fail : C.pass}` : "none",
                }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span className="mono" style={{ fontSize: 12, color: sel ? C.text : C.dim }}>#{t.id}</span>
                  <span className="num" style={{
                    marginLeft: "auto", fontSize: 12, fontWeight: 600,
                    color: t.fail > 0 ? C.fail : C.pass,
                  }}>
                    {t.fail > 0 ? `${t.fail} fail` : `${passRate(t)}%`}
                  </span>
                </div>
                <div style={{
                  fontSize: 12, color: C.dim, lineHeight: 1.4, marginBottom: 7,
                  display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden",
                }}>{t.title}</div>
                <StackBar t={t} h={4} />
              </button>
            );
          })}
        </div>
      </aside>

      {/* ---- Main ---- */}
      <main style={{ flex: 1, overflowY: "auto" }}>
        {/* Sprint summary header */}
        <div style={{ padding: "22px 28px", borderBottom: `1px solid ${C.line}`, position: "sticky", top: 0, background: C.bg, zIndex: 5 }}>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 24, marginBottom: 18 }}>
            <div>
              <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, letterSpacing: 0.5, marginBottom: 4 }}>HR · SPRINT 5</div>
              <div style={{ fontSize: 22, fontWeight: 700 }} className="num">Sprint 5</div>
              <div style={{ fontSize: 13, color: C.dim, marginTop: 2 }}>
                {TASKS.length} tasks · <span className="num">{sprintTotal}</span> test cases
              </div>
            </div>

            <div style={{ marginLeft: "auto", textAlign: "right" }}>
              <div className="num" style={{ fontSize: 46, fontWeight: 700, lineHeight: 1, color: sprintRate >= 80 ? C.pass : C.skip }}>
                {sprintRate}<span style={{ fontSize: 20, color: C.dim }}>%</span>
              </div>
              <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>PASS RATE</div>
            </div>
          </div>

          <StackBar t={sprint} h={9} />

          <div style={{ display: "flex", gap: 20, marginTop: 14, flexWrap: "wrap" }}>
            {["pass", "fail", "skip", "pending"].map((k) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ width: 9, height: 9, borderRadius: 3, background: STATUS[k].color }} />
                <span className="num" style={{ fontWeight: 700, fontSize: 15 }}>{sprint[k]}</span>
                <span style={{ fontSize: 13, color: C.dim }}>{STATUS[k].label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Active task detail */}
        <div style={{ padding: "24px 28px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <span className="mono" style={{ fontSize: 14, color: C.dim }}>#{activeTask.id}</span>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{activeTask.title}</h2>
            <ArrowUpRight size={16} color={C.faint} style={{ marginLeft: 4 }} />
          </div>
          <div style={{ display: "flex", gap: 8, margin: "14px 0 22px", flexWrap: "wrap" }}>
            {["pass", "fail", "skip", "pending"].map((k) =>
              activeTask[k] > 0 ? <StatusPill key={k} status={k} count={activeTask[k]} /> : null
            )}
          </div>

          {detail.length === 0 ? (
            <div style={{
              textAlign: "center", padding: "60px 20px", color: C.dim,
              border: `1px dashed ${C.line}`, borderRadius: 14,
            }}>
              <Check size={28} color={C.pass} style={{ marginBottom: 10 }} />
              <div style={{ fontWeight: 600, color: C.text, marginBottom: 4 }}>ไม่มี test case ที่ต้องดูเพิ่มเติม</div>
              <div style={{ fontSize: 13 }}>เลือก task ที่มี fail จากแถบด้านซ้ายเพื่อดูรายละเอียดผลที่ผิดพลาด</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1, color: C.faint }}>
                FAILED CASES ({detail.length})
              </div>
              {detail.map((tc) => (
                <div key={tc.id} style={{
                  background: C.panel, border: `1px solid ${C.line}`, borderRadius: 14,
                  borderLeft: `3px solid ${STATUS[tc.status].color}`, overflow: "hidden",
                }}>
                  <div style={{ display: "flex", gap: 16, padding: 16 }}>
                    {/* text column */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                        <span className="mono" style={{ fontSize: 13, color: STATUS[tc.status].color, fontWeight: 600 }}>{tc.id}</span>
                        <StatusPill status={tc.status} count={""} />
                      </div>
                      <Field label="EXPECTED" value={tc.expected} color={C.dim} />
                      <Field label="ACTUAL (จากผลเทส)" value={tc.actual} color={C.fail} />
                    </div>
                    {/* thumbnail */}
                    <button onClick={() => setLightbox(tc)} style={{
                      flexShrink: 0, width: 150, height: 100, borderRadius: 10, border: `1px solid ${C.line}`,
                      background: C.panel2, position: "relative", overflow: "hidden", padding: 0,
                    }}>
                      <MockShot kind={tc.shot} />
                      <span style={{
                        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                        background: "rgba(0,0,0,0.35)", opacity: 0, transition: "opacity .15s",
                      }}
                        onMouseEnter={(e) => (e.currentTarget.style.opacity = 1)}
                        onMouseLeave={(e) => (e.currentTarget.style.opacity = 0)}>
                        <Maximize2 size={18} color="#fff" />
                      </span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* ---- Lightbox ---- */}
      {lightbox && (
        <div onClick={() => setLightbox(null)} style={{
          position: "fixed", inset: 0, background: "rgba(8,10,14,0.85)", zIndex: 50,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 40,
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            background: C.panel, borderRadius: 16, border: `1px solid ${C.line}`,
            maxWidth: 720, width: "100%", overflow: "hidden",
          }}>
            <div style={{ display: "flex", alignItems: "center", padding: "14px 18px", borderBottom: `1px solid ${C.line}` }}>
              <span className="mono" style={{ color: C.fail, fontWeight: 600 }}>{lightbox.id}</span>
              <button onClick={() => setLightbox(null)} style={{ marginLeft: "auto", background: "none", border: "none", color: C.dim }}>
                <X size={18} />
              </button>
            </div>
            <div style={{ height: 360, background: "#fff", position: "relative" }}>
              <MockShot kind={lightbox.shot} big />
            </div>
            <div style={{ padding: 16, fontSize: 13, color: C.fail }}>{lightbox.actual}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, color }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, color: C.faint, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 13.5, lineHeight: 1.5, color }}>{value}</div>
    </div>
  );
}

// Lightweight mock of a captured screenshot so the layout reads without real images.
function MockShot({ kind, big }) {
  const s = big ? 1 : 0.62;
  return (
    <div style={{ width: "100%", height: "100%", background: "#F4F5F7", padding: 14 * s, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 * s, marginBottom: 10 * s }}>
        <div style={{ width: 18 * s, height: 18 * s, borderRadius: 999, background: "#3ECF8E" }} />
        <div style={{ height: 9 * s, width: 120 * s, background: "#2b2f36", borderRadius: 3 }} />
      </div>
      <div style={{ border: "2px solid #F2555A", borderRadius: 6, padding: 8 * s, marginBottom: 8 * s }}>
        <div style={{ height: 8 * s, width: 60 * s, background: "#F2555A", borderRadius: 3, marginBottom: 6 * s }} />
        <div style={{ height: 10 * s, width: "90%", background: "#dfe2e7", borderRadius: 3 }} />
      </div>
      {big && [0, 1, 2].map((i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid #e6e8ec" }}>
          <div style={{ width: 30, height: 30, borderRadius: 999, background: ["#F39B2D", "#E0464B", "#F39B2D"][i] }} />
          <div>
            <div style={{ height: 9, width: 180, background: "#2b2f36", borderRadius: 3, marginBottom: 5 }} />
            <div style={{ height: 7, width: 90, background: "#c4c8cf", borderRadius: 3 }} />
          </div>
        </div>
      ))}
    </div>
  );
}
