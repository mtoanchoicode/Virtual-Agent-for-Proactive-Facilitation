import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  pointerWithin,
  rectIntersection,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useChat } from "../hooks/useChat";
import { useT, useLang, itemLabel } from "../i18n";

// Cosmetic icons, keyed by card id (same ids as back/app/services/scenario.py BOARD_ITEMS).
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
const POOL_ID = "pool";
const slotId = (i) => `slot-${i}`;

// Pointer: use the droppable under the pointer. Keyboard (no pointer): fall back to rectangle overlap.
const collisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

// Same rules as back/app/core/board.py place()/unplace(), applied locally until the server answers.
function applyPlace(state, itemId, k) {
  const slots = [...state.slots];
  let pool = [...state.pool];
  const occupant = slots[k];
  if (occupant === itemId) return state;
  if (pool.includes(itemId)) {
    pool = pool.filter((id) => id !== itemId);
    if (occupant) pool.push(occupant);
  } else {
    slots[slots.indexOf(itemId)] = occupant ?? null; // swap, or plain move into an empty slot
  }
  slots[k] = itemId;
  return { slots, pool };
}

function applyUnplace(state, itemId) {
  if (!state.slots.includes(itemId)) return state;
  return { slots: state.slots.map((id) => (id === itemId ? null : id)), pool: [...state.pool, itemId] };
}

function CardBody({ id, label, lockedBy, dragging, overlay, onUnplace }) {
  const t = useT();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 8px",
        borderRadius: 10,
        width: "100%",
        background: overlay ? "rgba(14,165,233,0.30)" : "rgba(30,41,59,0.92)",
        border: lockedBy ? "1px dashed rgba(251,191,36,0.6)" : "1px solid rgba(148,163,184,0.18)",
        boxShadow: overlay ? "0 10px 28px rgba(0,0,0,0.5)" : "none",
        opacity: dragging ? 0.35 : lockedBy ? 0.7 : 1,
        cursor: lockedBy ? "not-allowed" : overlay ? "grabbing" : "grab",
        touchAction: "none",
        boxSizing: "border-box",
      }}
    >
      <span style={{ fontSize: 18 }}>{ICONS[id] ?? "📦"}</span>
      <span style={{ flex: 1, fontSize: 13, color: "#e2e8f0", lineHeight: 1.25 }}>
        {label}
        {lockedBy && (
          <span style={{ display: "block", fontSize: 11, color: "#fbbf24" }}>
            {lockedBy} {t("rank.moving", "is moving…")}
          </span>
        )}
      </span>
      {onUnplace && !lockedBy && !overlay && (
        <button
          // Keep the click from starting a drag.
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
          onClick={onUnplace}
          aria-label={`${t("rank.toPool", "Back to undecided")}: ${label}`}
          title={t("rank.toPool", "Back to undecided")}
          style={{
            background: "transparent",
            border: "none",
            color: "#94a3b8",
            fontSize: 14,
            padding: "2px 4px",
            cursor: "pointer",
          }}
        >
          ↩
        </button>
      )}
      <span aria-hidden style={{ color: "#64748b", fontSize: 16 }}>⠿</span>
    </div>
  );
}

function DraggableCard({ id, label, lockedBy, onUnplace, readOnly = false }) {
  const t = useT();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id, disabled: !!lockedBy || readOnly });
  if (readOnly) {
    // Admin observer: plain card, no drag handle or unplace button.
    return (
      <div style={{ width: "100%", pointerEvents: "none" }}>
        <CardBody id={id} label={label} lockedBy={lockedBy} />
      </div>
    );
  }
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      aria-label={`${t("rank.drag", "Drag")} ${label}`}
      title={t("rank.dragTitle", "Drag into a rank slot or back to undecided (or focus and press Space, then arrow keys)")}
      style={{ width: "100%", outline: "none" }}
    >
      <CardBody id={id} label={label} lockedBy={lockedBy} dragging={isDragging} onUnplace={onUnplace} />
    </div>
  );
}

function Slot({ index, children }) {
  const t = useT();
  const { setNodeRef, isOver } = useDroppable({ id: slotId(index) });
  const rank = index + 1;
  return (
    <div
      ref={setNodeRef}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        minHeight: 46,
        marginBottom: 6,
        padding: 3,
        borderRadius: 12,
        background: isOver ? "rgba(14,165,233,0.16)" : "rgba(15,23,42,0.4)",
        border: isOver ? "1px solid rgba(56,189,248,0.7)" : "1px dashed rgba(148,163,184,0.25)",
        transition: "background 0.12s, border-color 0.12s",
      }}
    >
      <span
        style={{
          width: 22,
          textAlign: "center",
          fontWeight: 800,
          fontSize: 13,
          color: rank <= 3 ? "#7dd3fc" : "#94a3b8",
          flexShrink: 0,
        }}
      >
        {rank}
      </span>
      {children ?? (
        <span style={{ flex: 1, fontSize: 12, color: "#64748b", fontStyle: "italic" }}>
          {t("rank.dropHere", "Drop a card here")}
        </span>
      )}
    </div>
  );
}

function Pool({ children, empty }) {
  const t = useT();
  const { setNodeRef, isOver } = useDroppable({ id: POOL_ID });
  return (
    <div
      ref={setNodeRef}
      style={{
        marginTop: 10,
        padding: 8,
        borderRadius: 12,
        minHeight: 56,
        background: isOver ? "rgba(251,191,36,0.10)" : "rgba(15,23,42,0.55)",
        border: isOver ? "1px solid rgba(251,191,36,0.6)" : "1px solid rgba(148,163,184,0.15)",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 700, color: "#cbd5e1", marginBottom: 2 }}>
        {t("rank.pool", "Undecided")}
      </div>
      <div style={{ fontSize: 10.5, color: "#64748b", marginBottom: 6 }}>
        {empty ? t("rank.poolEmpty", "All cards are placed") : t("rank.poolHint", "Drag each card into a rank once you both agree")}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </div>
  );
}

export default function RankingBoard() {
  const { board, sessionId, participants, boardDragStart, boardDragEnd, boardMove, boardUnplace, boardAgree, isAdmin } =
    useChat();
  const t = useT();
  const lang = useLang();
  const [open, setOpen] = useState(false);
  const [localState, setLocalState] = useState(null); // optimistic {slots, pool} until the server answers
  const [activeId, setActiveId] = useState(null);
  const [unseen, setUnseen] = useState(0);
  const lastVersion = useRef(null);
  const openRef = useRef(open);
  openRef.current = open;

  // Any server state replaces the optimistic one, so a rejected move snaps back and the partner's moves
  // appear live.
  useEffect(() => {
    setLocalState(null);
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
    useSensor(KeyboardSensor),
  );

  const labels = useMemo(
    () => Object.fromEntries((board?.items ?? []).map((it) => [it.id, itemLabel(lang, it.id, it.label)])),
    [board?.items, lang],
  );

  if (!board || !sessionId || !board.slots) return null;

  const state = localState ?? { slots: board.slots, pool: board.pool };
  const complete = state.slots.every(Boolean);
  const iAgreed = board.agreed.includes(sessionId);

  const lockedByOf = (id) => {
    const m = board.moving?.[id];
    return m && m.sessionId !== sessionId ? m.name || t("rank.partner", "Partner") : null;
  };

  const unplace = (id) => {
    setLocalState(applyUnplace(state, id));
    boardUnplace(id);
  };

  const handleDragStart = ({ active }) => {
    setActiveId(active.id);
    boardDragStart(active.id);
  };
  const handleDragCancel = ({ active }) => {
    setActiveId(null);
    boardDragEnd(active.id);
  };
  const handleDragEnd = ({ active, over }) => {
    setActiveId(null);
    const id = active.id;
    const target = over?.id;
    if (typeof target === "string" && target.startsWith("slot-")) {
      const k = Number(target.slice(5));
      if (state.slots[k] !== id) {
        setLocalState(applyPlace(state, id, k));
        boardMove(id, k);
        return;
      }
    } else if (target === POOL_ID && state.slots.includes(id)) {
      setLocalState(applyUnplace(state, id));
      boardUnplace(id);
      return;
    }
    boardDragEnd(id); // dropped nowhere / where it already was: just release the lock
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

        <div style={{ flex: 1, overflowY: "auto", padding: "4px 12px 8px" }}>
          <DndContext
            sensors={sensors}
            collisionDetection={collisionDetection}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            {state.slots.map((id, i) => (
              <Slot key={i} index={i}>
                {id ? (
                  <DraggableCard
                    id={id}
                    label={labels[id] ?? id}
                    lockedBy={lockedByOf(id)}
                    onUnplace={() => unplace(id)}
                    readOnly={isAdmin}
                  />
                ) : null}
              </Slot>
            ))}

            <Pool empty={state.pool.length === 0}>
              {state.pool.map((id) => (
                <DraggableCard key={id} id={id} label={labels[id] ?? id} lockedBy={lockedByOf(id)} readOnly={isAdmin} />
              ))}
            </Pool>

            {/* Rendered on <body>: the drawer is transformed, which would offset a fixed-position overlay. */}
            {createPortal(
              <DragOverlay dropAnimation={null} zIndex={1000}>
                {activeId ? (
                  <div style={{ width: PANEL_WIDTH - 60 }}>
                    <CardBody id={activeId} label={labels[activeId] ?? activeId} overlay />
                  </div>
                ) : null}
              </DragOverlay>,
              document.body,
            )}
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
          {isAdmin ? (
            <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 6, textAlign: "center" }}>
              {t("admin.boardReadOnly", "Admin view — read only")}
            </div>
          ) : (<>
          <button
            onClick={() => boardAgree(!iAgreed)}
            disabled={!complete && !iAgreed}
            title={!complete ? t("rank.needAll", "Place every card before agreeing") : undefined}
            style={{
              width: "100%",
              marginTop: 6,
              padding: "9px 12px",
              borderRadius: 10,
              fontWeight: 700,
              fontSize: 13,
              cursor: !complete && !iAgreed ? "not-allowed" : "pointer",
              opacity: !complete && !iAgreed ? 0.45 : 1,
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
            {complete
              ? t("rank.note", "Moving any card clears everyone's agreement.")
              : t("rank.needAll", "Place every card before agreeing")}
          </div>
          </>)}
        </div>
      </aside>
    </>
  );
}
