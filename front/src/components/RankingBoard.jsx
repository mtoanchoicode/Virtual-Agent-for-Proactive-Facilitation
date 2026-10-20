import { useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useChat } from "../hooks/useChat";
import { useT, useLang, itemLabel } from "../i18n";

// Cosmetic icons, keyed by card id (same order as back/app/services/scenario.py ITEMS).
const ICONS = {
  "item-1": "🧭",
  "item-2": "🪞",
  "item-3": "🕸️",
  "item-4": "💧",
  "item-5": "🥫",
  "item-6": "🗺️",
  "item-7": "🛟",
  "item-8": "⛽",
  "item-9": "📻",
  "item-10": "🛍️",
  "item-11": "🦈",
  "item-12": "🧴",
  "item-13": "🪢",
  "item-14": "🍫",
  "item-15": "🎣",
};

const PANEL_WIDTH = 320;

function Card({ id, label, rank, lockedBy }) {
  const t = useT();
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id, disabled: !!lockedBy });

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 10px",
        marginBottom: 6,
        borderRadius: 10,
        background: isDragging ? "rgba(14,165,233,0.22)" : "rgba(30,41,59,0.85)",
        border: lockedBy
          ? "1px dashed rgba(251,191,36,0.6)"
          : "1px solid rgba(148,163,184,0.18)",
        boxShadow: isDragging ? "0 8px 24px rgba(0,0,0,0.45)" : "none",
        opacity: lockedBy ? 0.7 : 1,
        zIndex: isDragging ? 5 : "auto",
        position: "relative",
      }}
    >
      <span
        style={{
          width: 24,
          textAlign: "center",
          fontWeight: 800,
          fontSize: 13,
          color: rank <= 3 ? "#7dd3fc" : "#94a3b8",
        }}
      >
        {rank}
      </span>
      <span style={{ fontSize: 18 }}>{ICONS[id] ?? "📦"}</span>
      <span style={{ flex: 1, fontSize: 13, color: "#e2e8f0", lineHeight: 1.25 }}>
        {label}
        {lockedBy && (
          <span style={{ display: "block", fontSize: 11, color: "#fbbf24" }}>
            {lockedBy} {t("rank.moving", "is moving…")}
          </span>
        )}
      </span>
      <button
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        disabled={!!lockedBy}
        aria-label={`${t("rank.drag", "Drag")} ${label}`}
        title={t("rank.dragTitle", "Drag to reorder (or focus and press Space, then arrow keys)")}
        style={{
          cursor: lockedBy ? "not-allowed" : isDragging ? "grabbing" : "grab",
          touchAction: "none",
          background: "transparent",
          border: "none",
          color: "#94a3b8",
          fontSize: 18,
          padding: "4px 6px",
        }}
      >
        ⠿
      </button>
    </div>
  );
}

export default function RankingBoard() {
  const { board, sessionId, participants, boardDragStart, boardDragEnd, boardMove, boardAgree } = useChat();
  const t = useT();
  const lang = useLang();
  const [open, setOpen] = useState(false);
  const [localOrder, setLocalOrder] = useState(null); // optimistic order until the server answers
  const [unseen, setUnseen] = useState(0);
  const lastVersion = useRef(null);
  const openRef = useRef(open);
  openRef.current = open;

  // Any server state replaces the optimistic order. A rejected move therefore snaps back.
  useEffect(() => {
    setLocalOrder(null);
  }, [board]);

  // Badge: count changes made while the panel is closed.
  useEffect(() => {
    if (!board) return;
    if (lastVersion.current !== null && board.version > lastVersion.current && !openRef.current) {
      setUnseen((n) => n + (board.version - lastVersion.current));
    }
    lastVersion.current = board.version;
  }, [board]);

  useEffect(() => {
    if (open) setUnseen(0);
  }, [open]);

  // Push the rest of the app left while the drawer is open (wide screens only; on narrow
  // screens the drawer overlays instead, since there is no room to shrink).
  const visible = !!board && !!sessionId;
  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const wide = window.matchMedia("(min-width: 900px)").matches;
      root.style.setProperty("--ranking-offset", visible && open && wide ? `${PANEL_WIDTH}px` : "0px");
    };
    apply();
    window.addEventListener("resize", apply);
    return () => {
      window.removeEventListener("resize", apply);
      root.style.setProperty("--ranking-offset", "0px");
    };
  }, [open, visible]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 120, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const labels = useMemo(
    () => Object.fromEntries((board?.items ?? []).map((it) => [it.id, itemLabel(lang, it.id, it.label)])),
    [board?.items, lang],
  );

  if (!board || !sessionId) return null;

  const order = localOrder ?? board.order;
  const iAgreed = board.agreed.includes(sessionId);

  const handleDragStart = ({ active }) => boardDragStart(active.id);
  const handleDragCancel = ({ active }) => boardDragEnd(active.id);
  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) {
      boardDragEnd(active.id);
      return;
    }
    const from = order.indexOf(active.id);
    const to = order.indexOf(over.id);
    setLocalOrder(arrayMove(order, from, to));
    boardMove(active.id, to);
  };

  return (
    <>
      {/* Edge tab: always visible, toggles the drawer */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? t("rank.close", "Close ranking board") : t("rank.open", "Open ranking board")}
        style={{
          position: "fixed",
          top: "42%",
          right: open ? PANEL_WIDTH : 0,
          zIndex: 41,
          transition: "right 0.25s ease",
          writingMode: "vertical-rl",
          padding: "14px 8px",
          borderRadius: "10px 0 0 10px",
          background: board.allAgreed ? "#16a34a" : "rgba(15,23,42,0.92)",
          border: "1px solid rgba(148,163,184,0.25)",
          borderRight: "none",
          color: "#e2e8f0",
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: "0.08em",
          cursor: "pointer",
        }}
      >
        {open ? t("rank.closeTab", "Close ▸") : t("rank.openTab", "◂ Ranking")}
        {!open && unseen > 0 && (
          <span
            style={{
              writingMode: "horizontal-tb",
              marginTop: 8,
              display: "inline-block",
              background: "#f59e0b",
              color: "#111827",
              borderRadius: 999,
              fontSize: 11,
              fontWeight: 800,
              padding: "1px 6px",
            }}
          >
            {unseen}
          </span>
        )}
      </button>

      {/* Drawer */}
      <aside
        aria-hidden={!open}
        style={{
          position: "fixed",
          top: 76,
          bottom: 16,
          right: 0,
          width: `min(${PANEL_WIDTH}px, 92vw)`,
          zIndex: 40,
          transform: open ? "translateX(0)" : "translateX(105%)",
          transition: "transform 0.25s ease",
          display: "flex",
          flexDirection: "column",
          background: "rgba(15,23,42,0.94)",
          backdropFilter: "blur(10px)",
          border: "1px solid rgba(148,163,184,0.2)",
          borderRight: "none",
          borderRadius: "14px 0 0 14px",
          fontFamily: "'DM Sans', sans-serif",
        }}
      >
        <div style={{ padding: "12px 14px 8px" }}>
          <div style={{ fontWeight: 800, color: "#f1f5f9", fontSize: 15 }}>{t("rank.title", "Survival ranking")}</div>
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
            {lang === "vi" ? t("rank.legend", "") : <>▲ most important &nbsp;·&nbsp; ▼ least important</>}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "4px 12px" }}>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <SortableContext items={order} strategy={verticalListSortingStrategy}>
              {order.map((id, i) => {
                const m = board.moving?.[id];
                const lockedBy = m && m.sessionId !== sessionId ? m.name || t("rank.partner", "Partner") : null;
                return <Card key={id} id={id} label={labels[id] ?? id} rank={i + 1} lockedBy={lockedBy} />;
              })}
            </SortableContext>
          </DndContext>
        </div>

        <div style={{ padding: "10px 14px 14px", borderTop: "1px solid rgba(148,163,184,0.15)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {participants.map((p) => {
              const ok = board.agreed.includes(p.sessionId);
              return (
                <span
                  key={p.sessionId}
                  style={{
                    fontSize: 11,
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: ok ? "rgba(34,197,94,0.18)" : "rgba(148,163,184,0.12)",
                    color: ok ? "#86efac" : "#94a3b8",
                    border: `1px solid ${ok ? "rgba(34,197,94,0.4)" : "rgba(148,163,184,0.2)"}`,
                  }}
                >
                  {ok ? "✓ " : ""}
                  {p.name}
                </span>
              );
            })}
          </div>
          {board.allAgreed ? (
            <div style={{ fontSize: 13, fontWeight: 700, color: "#86efac", textAlign: "center" }}>
              {t("rank.bothAgreed", "✓ Both agreed — final ranking")}
            </div>
          ) : null}
          <button
            onClick={() => boardAgree(!iAgreed)}
            style={{
              width: "100%",
              marginTop: 6,
              padding: "9px 12px",
              borderRadius: 10,
              fontWeight: 700,
              fontSize: 13,
              cursor: "pointer",
              color: iAgreed ? "#fde68a" : "#ffffff",
              background: iAgreed
                ? "rgba(251,191,36,0.12)"
                : "linear-gradient(135deg, #0ea5e9, #4f46e5)",
              border: iAgreed ? "1px solid rgba(251,191,36,0.4)" : "1px solid rgba(255,255,255,0.2)",
            }}
          >
            {iAgreed ? t("rank.withdraw", "Withdraw my agreement") : t("rank.agree", "I agree with this order")}
          </button>
          <div style={{ fontSize: 10.5, color: "#64748b", marginTop: 6, textAlign: "center" }}>
            {t("rank.note", "Moving any card clears everyone's agreement.")}
          </div>
        </div>
      </aside>
    </>
  );
}
