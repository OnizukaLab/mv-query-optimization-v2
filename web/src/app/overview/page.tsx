"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  getSelectedNodes,
  getSnapshot,
  listQueries,
  listResultSets,
  type ResultSet,
  type SelectedNodes,
} from "@/lib/api";
import { algorithmColor } from "@/lib/colors";
import { layoutPlan, NODE_HEIGHT, NODE_WIDTH, type PlanNode } from "@/lib/plan";
import { categoryOf, categoryStyle, DESCRIPTIONS, useNodeColors } from "@/lib/nodeColors";

const CONCURRENCY = 6;
const MIN_SCALE = 0.01;
const MAX_SCALE = 1.6;
/** The zoom slider moves over integer steps (log scale); float min/max props break hydration. */
const SLIDER_STEPS = 1000;
const scaleToStep = (scale: number) =>
  Math.round((Math.log(scale / MIN_SCALE) / Math.log(MAX_SCALE / MIN_SCALE)) * SLIDER_STEPS);
const stepToScale = (step: number) => MIN_SCALE * (MAX_SCALE / MIN_SCALE) ** (step / SLIDER_STEPS);

/** Node pixel width at which each level of detail appears (semantic zoom). */
const SHOW_TYPE = 50;
const SHOW_TARGET = 110;
const SHOW_STATS = 160;
const SHOW_DETAIL = 230;

const clip = (v: unknown, n: number) => {
  const t = typeof v === "string" ? v : "";
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
};

interface Loaded {
  id: string;
  plan: PlanNode;
}

function nodeIdOf(plan: PlanNode): string | null {
  const v = plan["node_id"];
  return typeof v === "string" ? v : null;
}

/** World-space card geometry (units of the unscaled plan layout). */
const CARD_PAD = 40;
const CARD_HEADER = 70;
const CARD_GAP = 60;

type Layout = ReturnType<typeof layoutPlan>;

type Overlap = "any" | "multi" | "all";

/** An optimizer whose selected nodes are being highlighted. */
interface Pick {
  name: string;
  color: string;
  ids: Set<string>;
  /** Nodes each query actually uses, by query id. */
  used: Map<string, Set<string>>;
}

interface Placed {
  item: Loaded;
  layout: Layout;
  x: number;
  y: number;
  w: number;
  h: number;
}

function PlanCard({
  placed,
  px,
  selected,
  onSelect,
  dragged,
  onOpen,
  active = false,
  dim = true,
  picks = [],
  overlap = "any",
}: {
  placed: Placed;
  px: number;
  selected: string | null;
  onSelect: (nodeId: string | null) => void;
  /** True while the last pointer gesture was a pan, so its click must be ignored. */
  dragged: { current: boolean };
  /** Called when the card itself (not one of its nodes) is clicked. */
  onOpen?: (queryId: string) => void;
  /** Marks the card whose detail popup is open. */
  active?: boolean;
  /** Fade the card when a node is selected that it does not contain. */
  dim?: boolean;
  /** Optimizers whose selected nodes get highlighted (empty: no optimizer highlighting). */
  picks?: Pick[];
  /** Which highlighted nodes stand out: any pick, picked by 2+ optimizers, or by all of them. */
  overlap?: Overlap;
}) {
  const { enabled, colors } = useNodeColors();
  const { item, layout, x, y, w, h } = placed;
  const pos = new Map(layout.nodes.map((n) => [n.id, n.position]));
  const hits = selected ? layout.nodes.filter((n) => nodeIdOf(n.data.plan) === selected).length : 0;

  return (
    <g
      transform={`translate(${x} ${y})`}
      opacity={dim && selected && hits === 0 ? 0.35 : 1}
      onClick={(e) => {
        if (!onOpen) return;
        e.stopPropagation();
        if (!dragged.current) onOpen(item.id);
      }}
      className={onOpen ? "cursor-pointer" : ""}
    >
      <rect
        width={w}
        height={h}
        rx={24}
        className="fill-white dark:fill-zinc-900"
        stroke={active ? "#2a78d6" : hits ? "#f59e0b" : "#a1a1aa"}
        strokeWidth={active ? 16 : hits ? 12 : 4}
      />
      <text x={CARD_PAD} y={CARD_PAD + 28} fontSize={40} fontWeight={600} fill="currentColor">
        {item.id}
        {hits > 0 ? `  ×${hits}` : ""}
      </text>
      <g transform={`translate(${CARD_PAD} ${CARD_HEADER + CARD_PAD / 2})`}>
        {layout.edges.map((e) => {
          const s = pos.get(e.source)!;
          const t = pos.get(e.target)!;
          return (
            <line
              key={e.id}
              x1={s.x + NODE_WIDTH / 2}
              y1={s.y + NODE_HEIGHT}
              x2={t.x + NODE_WIDTH / 2}
              y2={t.y}
              stroke="#a1a1aa"
              strokeWidth={Math.max(3, 1.5 / px)}
            />
          );
        })}
        {layout.nodes.map((n) => {
          const plan = n.data.plan;
          const cat = categoryOf(plan["Node Type"]);
          const nid = nodeIdOf(plan);
          const hit = selected !== null && nid === selected;
          const fill = enabled ? colors[cat] : "#a1a1aa";
          const style = categoryStyle(cat, fill);
          const chosenBy = nid ? picks.filter((pk) => pk.used.get(item.id)?.has(nid)) : [];
          // overlap filter: only nodes chosen by at least `need` of the picked optimizers stand out
          const need = overlap === "all" ? picks.length : overlap === "multi" ? 2 : 1;
          const emphasized = picks.length > 0 && chosenBy.length >= need;
          const faded = picks.length > 0 && !emphasized;
          return (
            <g
              key={n.id}
              onClick={(ev) => {
                ev.stopPropagation();
                if (dragged.current) return;
                if (nid) onSelect(hit ? null : nid);
              }}
              className={nid ? "cursor-pointer" : ""}
            >
              <title>{`${plan["Node Type"]}${plan["Relation Name"] ? ` · ${plan["Relation Name"]}` : ""}`}</title>
              <g opacity={faded ? 0.25 : 1}>
                <rect
                  x={n.position.x}
                  y={n.position.y}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={10}
                  fill={hit ? fill : style.background}
                  stroke={hit ? "#f59e0b" : style.border}
                  strokeWidth={hit ? 14 : 6}
                  style={hit ? { filter: "drop-shadow(0 0 18px #f59e0b)" } : undefined}
                />
                {emphasized && chosenBy.length === 1 && (
                  <rect
                    x={n.position.x}
                    y={n.position.y}
                    width={NODE_WIDTH}
                    height={NODE_HEIGHT}
                    rx={10}
                    fill="none"
                    strokeWidth={16}
                    style={{
                      stroke: chosenBy[0].color,
                      filter: `drop-shadow(0 0 20px ${chosenBy[0].color})`,
                    }}
                  />
                )}
                {emphasized && chosenBy.length > 1 && (
                  <>
                    {/* shared by several optimizers: a dark outer ring, then one border segment per optimizer */}
                    <rect
                      x={n.position.x - 12}
                      y={n.position.y - 12}
                      width={NODE_WIDTH + 24}
                      height={NODE_HEIGHT + 24}
                      rx={18}
                      fill="none"
                      strokeWidth={6}
                      className="stroke-zinc-900 dark:stroke-zinc-100"
                    />
                    {chosenBy.map((pk, i) => (
                      <rect
                        key={pk.name}
                        x={n.position.x}
                        y={n.position.y}
                        width={NODE_WIDTH}
                        height={NODE_HEIGHT}
                        rx={10}
                        fill="none"
                        pathLength={100}
                        strokeWidth={18}
                        strokeDasharray={`${100 / chosenBy.length} ${100 - 100 / chosenBy.length}`}
                        strokeDashoffset={-(i * 100) / chosenBy.length}
                        style={{ stroke: pk.color }}
                      />
                    ))}
                  </>
                )}
                {/* one dot per optimizer that selected this node, so overlaps stay readable */}
                {emphasized &&
                  chosenBy.map((pk, i) => (
                    <circle
                      key={pk.name}
                      cx={n.position.x + NODE_WIDTH - 18 - i * 30}
                      cy={n.position.y + 18}
                      r={12}
                      strokeWidth={3}
                      className="stroke-white dark:stroke-zinc-900"
                      style={{ fill: pk.color }}
                    />
                  ))}
              </g>
              {NODE_WIDTH * px >= SHOW_TYPE && !faded && (
                <NodeText plan={plan} cat={cat} x={n.position.x} y={n.position.y} px={NODE_WIDTH * px} />
              )}
            </g>
          );
        })}
      </g>
    </g>
  );
}

function NodeText({
  plan,
  cat,
  x,
  y,
  px,
}: {
  plan: PlanNode;
  cat: ReturnType<typeof categoryOf>;
  x: number;
  y: number;
  px: number;
}) {
  const target = plan["Relation Name"] ?? plan["Index Name"];
  const cond = plan["Hash Cond"] ?? plan["Merge Cond"] ?? plan["Index Cond"] ?? plan["Join Filter"];
  const rows = `rows ${plan["Actual Rows"] !== undefined ? `${plan["Actual Rows"]} / ` : ""}${plan["Plan Rows"]}`;
  const common = { fill: "currentColor", style: { pointerEvents: "none" as const } };
  // Every showing line must still fit the node box, so the type is clipped when space is tight.
  return (
    <g className="text-zinc-900 dark:text-zinc-100">
      <text x={x + 14} y={y + 26} fontSize={px < SHOW_TARGET ? 24 : 20} fontWeight={600} {...common}>
        {clip(plan["Node Type"], px < SHOW_TARGET ? 14 : 24)}
      </text>
      {px >= SHOW_TARGET && target && (
        <text x={x + 14} y={y + 46} fontSize={16} opacity={0.7} {...common}>
          {clip(target, 28)}
        </text>
      )}
      {px >= SHOW_STATS && (
        <text x={x + 14} y={y + 66} fontSize={15} opacity={0.75} {...common}>
          {`cost ${plan["Total Cost"].toFixed(0)} · ${rows}`}
        </text>
      )}
      {px >= SHOW_DETAIL && (
        <>
          <text x={x + 14} y={y + 82} fontSize={11} opacity={0.6} {...common}>
            {clip(cond ?? DESCRIPTIONS[cat], 42)}
          </text>
        </>
      )}
    </g>
  );
}

/** Popup rectangle in viewport (fixed-position) pixels. */
interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const POPUP_MIN_W = 280;
const POPUP_MIN_H = 200;

/** Edge/corner handles of the popup: which sides a drag on each one moves. */
const HANDLES = [
  { dir: "n", cls: "left-2 right-2 top-0 h-1.5 cursor-ns-resize" },
  { dir: "s", cls: "bottom-0 left-2 right-2 h-1.5 cursor-ns-resize" },
  { dir: "w", cls: "bottom-2 left-0 top-2 w-1.5 cursor-ew-resize" },
  { dir: "e", cls: "bottom-2 right-0 top-2 w-1.5 cursor-ew-resize" },
  { dir: "nw", cls: "left-0 top-0 h-3 w-3 cursor-nwse-resize" },
  { dir: "ne", cls: "right-0 top-0 h-3 w-3 cursor-nesw-resize" },
  { dir: "sw", cls: "bottom-0 left-0 h-3 w-3 cursor-nesw-resize" },
  { dir: "se", cls: "bottom-0 right-0 h-3 w-3 cursor-nwse-resize" },
] as const;

interface View {
  x: number;
  y: number;
  k: number;
}

const clampScale = (k: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, k));

/**
 * Pack cards into rows, centering each row, choosing the wrap width whose bounding box
 * best fills a viewport of the given aspect ratio (so the whole set fits the screen).
 */
function packCards(
  entries: { item: Loaded; layout: Layout; w: number; h: number }[],
  vw: number,
  vh: number,
): { placed: Placed[]; width: number; height: number } {
  if (entries.length === 0) return { placed: [], width: 1, height: 1 };
  const widest = Math.max(...entries.map((e) => e.w));
  const total = entries.reduce((sum, e) => sum + e.w + CARD_GAP, CARD_GAP);
  let best: { placed: Placed[]; width: number; height: number; fit: number } | null = null;
  for (let i = 0; i <= 60; i++) {
    const limit = widest + CARD_GAP * 2 + ((total - widest) * i) / 60;
    const rows: (typeof entries)[] = [[]];
    let rowW = CARD_GAP;
    for (const e of entries) {
      if (rows[rows.length - 1].length && rowW + e.w + CARD_GAP > limit) {
        rows.push([]);
        rowW = CARD_GAP;
      }
      rows[rows.length - 1].push(e);
      rowW += e.w + CARD_GAP;
    }
    const rowWidths = rows.map((r) => r.reduce((sum, e) => sum + e.w + CARD_GAP, CARD_GAP));
    const width = Math.max(...rowWidths);
    const rowHeights = rows.map((r) => Math.max(...r.map((e) => e.h)));
    const height = rowHeights.reduce((sum, h) => sum + h + CARD_GAP, CARD_GAP);
    const fit = Math.min(vw / width, vh / height);
    if (best && fit <= best.fit) continue;
    const placed: Placed[] = [];
    let y = CARD_GAP;
    rows.forEach((r, ri) => {
      let x = (width - rowWidths[ri]) / 2 + CARD_GAP;
      for (const e of r) {
        placed.push({ ...e, x, y: y + (rowHeights[ri] - e.h) / 2 });
        x += e.w + CARD_GAP;
      }
      y += rowHeights[ri] + CARD_GAP;
    });
    best = { placed, width, height, fit };
  }
  return best!;
}

export default function OverviewPage() {
  const [items, setItems] = useState<Loaded[]>([]);
  const [total, setTotal] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 0.05 });
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragged = useRef(false);
  const popupDragged = useRef(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [popupK, setPopupK] = useState(0.3);
  const popupRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const [sets, setSets] = useState<ResultSet[]>([]);
  const [setId, setSetId] = useState<string>("");
  const [chosen, setChosen] = useState<Record<string, SelectedNodes>>({});
  const [algos, setAlgos] = useState<string[]>([]);
  const wanted = useRef<string[] | null>(null);
  const popupAnchor = useRef<{ wx: number; wy: number; cx: number; cy: number } | null>(null);
  const layoutCache = useRef(new Map<string, Layout>());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const queries = await listQueries();
        if (cancelled) return;
        setTotal(queries.length);
        const queue = [...queries];
        const worker = async () => {
          for (let q = queue.shift(); q && !cancelled; q = queue.shift()) {
            const snap = await getSnapshot(q.id);
            if (!cancelled) setItems((prev) => [...prev, { id: q.id, plan: snap.plan }]);
          }
        };
        await Promise.all(Array.from({ length: CONCURRENCY }, worker));
        if (!cancelled) setDone(true);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Result sets for the optimizer highlight; ?set=&algo= (from the Results page) preselects one.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    wanted.current = params.get("algo")?.split(",").filter(Boolean) ?? null;
    listResultSets()
      .then((list) => {
        setSets(list);
        const fromUrl = params.get("set");
        setSetId(list.some((r) => r.id === fromUrl) ? (fromUrl as string) : "");
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!setId) return;
    let cancelled = false;
    getSelectedNodes(setId)
      .then((res) => {
        if (cancelled) return;
        setChosen(res);
        setAlgos((wanted.current ?? []).filter((a) => a in res));
        wanted.current = null;
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [setId]);

  const algoNames = useMemo(() => Object.keys(chosen).filter((a) => a !== "none"), [chosen]);
  const [overlap, setOverlap] = useState<Overlap>("any");
  const picks = useMemo<Pick[]>(
    () =>
      algos
        .filter((a) => chosen[a]?.consistent)
        .map((a) => ({
          name: a,
          color: algorithmColor(a, algoNames),
          ids: new Set(chosen[a].node_ids),
          used: new Map(Object.entries(chosen[a].used ?? {}).map(([q, ns]) => [q, new Set(ns)])),
        })),
    [algos, chosen, algoNames],
  );

  /** Distinct highlighted nodes: chosen by any / 2+ / every picked optimizer. */
  const overlapCounts = useMemo(() => {
    const times = new Map<string, number>();
    picks.forEach((pk) => pk.ids.forEach((id) => times.set(id, (times.get(id) ?? 0) + 1)));
    const counts = [...times.values()];
    return {
      any: counts.length,
      multi: counts.filter((c) => c >= 2).length,
      all: counts.filter((c) => c === picks.length).length,
    };
  }, [picks]);

  // The viewport size is captured once and used for the arrangement; later resizes keep the layout.
  const sizeRef = useRef(size);
  sizeRef.current = size;
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const measure = () => {
      if (!sizeRef.current && el.clientWidth > 0) setSize({ w: el.clientWidth, h: el.clientHeight });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Fixed world layout: independent of zoom/pan; arranged to fill the screen once, centered.
  const world = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const entries = items
      .filter((i) => !f || i.id.includes(f))
      .sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }))
      .map((item) => {
        let layout = layoutCache.current.get(item.id);
        if (!layout) {
          layout = layoutPlan(item.plan);
          layoutCache.current.set(item.id, layout);
        }
        const pw = Math.max(...layout.nodes.map((n) => n.position.x + NODE_WIDTH));
        const ph = Math.max(...layout.nodes.map((n) => n.position.y + NODE_HEIGHT));
        return { item, layout, w: pw + CARD_PAD * 2, h: ph + CARD_HEADER + CARD_PAD * 1.5 };
      });
    return packCards(entries, size?.w ?? 1600, size?.h ?? 900);
  }, [items, filter, size]);

  const fit = useCallback(() => {
    const el = canvasRef.current;
    if (!el) return;
    const k = clampScale(Math.min(el.clientWidth / world.width, el.clientHeight / world.height) * 0.95);
    setView({
      k,
      x: (el.clientWidth - world.width * k) / 2,
      y: (el.clientHeight - world.height * k) / 2,
    });
  }, [world]);

  // Center everything once all plans are in, and again when the filter changes the set.
  useEffect(() => {
    if (done && size) fit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done, filter, size === null]);

  /** Zoom by a factor around a canvas point (default: the canvas center). */
  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    const el = canvasRef.current;
    const px = cx ?? (el?.clientWidth ?? 0) / 2;
    const py = cy ?? (el?.clientHeight ?? 0) / 2;
    setView((v) => {
      const k = clampScale(v.k * factor);
      return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
    });
  }, []);

  // Ctrl/⌘ + wheel (and pinch) zooms at the cursor; plain wheel / two-finger scroll pans.
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const r = el.getBoundingClientRect();
        zoomAt(Math.exp(-Math.max(-50, Math.min(50, e.deltaY)) * 0.01), e.clientX - r.left, e.clientY - r.top);
      } else {
        setView((v) => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  // Drag to pan. A gesture that moved more than a few px must not count as a click.
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const start = { x: e.clientX, y: e.clientY };
    let last = { ...start };
    dragged.current = false;
    const move = (m: PointerEvent) => {
      if (!dragged.current && Math.hypot(m.clientX - start.x, m.clientY - start.y) < 4) return;
      dragged.current = true;
      const dx = m.clientX - last.x;
      const dy = m.clientY - last.y;
      last = { x: m.clientX, y: m.clientY };
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setTimeout(() => (dragged.current = false), 0);
    };
    last = { ...start };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  /** Open a card's popup; the first time, place it at the canvas's bottom-left. */
  const openQuery = (id: string) => {
    setOpenId(id);
    const el = wrapperRef.current;
    if (!rect && el) {
      const r = el.getBoundingClientRect();
      const w = Math.min(440, r.width * 0.42);
      const h = r.height * 0.48;
      setRect({ x: r.left + 12, y: r.bottom - h - 12, w, h });
    }
  };

  /** Drag gesture on the header (move) or an edge/corner handle (resize); `dir` is "move" or a side set. */
  const startPopupDrag = (e: React.PointerEvent, dir: string) => {
    if (e.button !== 0 || !rect) return;
    e.preventDefault();
    const start = { x: e.clientX, y: e.clientY, rect };
    const move = (m: PointerEvent) => {
      const dx = m.clientX - start.x;
      const dy = m.clientY - start.y;
      const r = { ...start.rect };
      if (dir === "move") {
        r.x = start.rect.x + dx;
        r.y = start.rect.y + dy;
      } else {
        if (dir.includes("e")) r.w = Math.max(POPUP_MIN_W, start.rect.w + dx);
        if (dir.includes("s")) r.h = Math.max(POPUP_MIN_H, start.rect.h + dy);
        if (dir.includes("w")) {
          r.w = Math.max(POPUP_MIN_W, start.rect.w - dx);
          r.x = start.rect.x + start.rect.w - r.w;
        }
        if (dir.includes("n")) {
          r.h = Math.max(POPUP_MIN_H, start.rect.h - dy);
          r.y = start.rect.y + start.rect.h - r.h;
        }
      }
      // keep the header reachable inside the window
      r.x = Math.min(Math.max(r.x, 40 - r.w), window.innerWidth - 40);
      r.y = Math.min(Math.max(r.y, 0), window.innerHeight - 32);
      setRect(r);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const openCard = openId ? (world.placed.find((p) => p.item.id === openId) ?? null) : null;

  /** Scale the popup so the whole opened plan fits inside it. */
  const fitPopup = useCallback(() => {
    const el = popupRef.current;
    if (!el || !openCard) return;
    setPopupK(
      clampScale(Math.min(1, (el.clientWidth - 8) / openCard.w, (el.clientHeight - 8) / openCard.h)),
    );
    el.scrollLeft = 0;
    el.scrollTop = 0;
  }, [openCard]);

  const openIdForFit = openCard?.item.id;
  useLayoutEffect(() => {
    if (openIdForFit) fitPopup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openIdForFit]);

  /** Zoom the popup by a factor, keeping the plan point under (cx, cy) fixed on screen. */
  const popupZoomAt = (factor: number, cx?: number, cy?: number) => {
    const el = popupRef.current;
    if (el) {
      const x = cx ?? el.clientWidth / 2;
      const y = cy ?? el.clientHeight / 2;
      popupAnchor.current = {
        wx: (el.scrollLeft + x) / popupK,
        wy: (el.scrollTop + y) / popupK,
        cx: x,
        cy: y,
      };
    }
    setPopupK(clampScale(popupK * factor));
  };

  useLayoutEffect(() => {
    const el = popupRef.current;
    const a = popupAnchor.current;
    if (!el || !a) return;
    el.scrollLeft = a.wx * popupK - a.cx;
    el.scrollTop = a.wy * popupK - a.cy;
    popupAnchor.current = null;
  }, [popupK]);

  // Trackpad pinch / Ctrl+scroll zooms the popup at the cursor; plain scroll pans it natively.
  const popupZoomRef = useRef(popupZoomAt);
  popupZoomRef.current = popupZoomAt;
  useEffect(() => {
    const el = popupRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      popupZoomRef.current(Math.exp(-Math.max(-50, Math.min(50, e.deltaY)) * 0.01), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [openIdForFit]);

  const selectedInfo = useMemo(() => {
    if (!selected) return null;
    let sample: PlanNode | null = null;
    const queries: string[] = [];
    for (const it of items) {
      const stack = [it.plan];
      let found = false;
      while (stack.length) {
        const n = stack.pop()!;
        if (nodeIdOf(n) === selected) {
          sample ??= n;
          found = true;
        }
        n.Plans?.forEach((c) => stack.push(c));
      }
      if (found) queries.push(it.id);
    }
    return { sample, queries };
  }, [selected, items]);

  return (
    <div className="flex h-screen flex-col gap-3 p-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-semibold">Plan overview</h1>
        <span className="text-sm text-zinc-500">
          {items.length}
          {total ? ` / ${total}` : ""} plans loaded
        </span>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <button className="rounded border px-2" onClick={() => zoomAt(1 / 1.25)} aria-label="Zoom out">
            −
          </button>
          <input
            type="range"
            min={0}
            max={SLIDER_STEPS}
            step={1}
            value={scaleToStep(view.k)}
            onChange={(e) => zoomAt(stepToScale(Number(e.target.value)) / view.k)}
            aria-label="Zoom"
          />
          <button className="rounded border px-2" onClick={() => zoomAt(1.25)} aria-label="Zoom in">
            +
          </button>
          <span className="w-12 tabular-nums text-zinc-500">{Math.round(view.k * 100)}%</span>
          <button
            className="rounded border px-2"
            onClick={fit}
            title="Back to the default view: everything centered and fitted to the screen"
          >
            Reset view
          </button>
        </div>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by id"
          className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700"
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-zinc-500">Highlight selected nodes of</span>
        <select
          value={setId}
          onChange={(e) => {
            setSetId(e.target.value);
            setChosen({});
            setAlgos([]);
          }}
          className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
        >
          <option value="">(none)</option>
          {sets.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
        {setId && algoNames.length > 0 && !algoNames.some((a) => chosen[a].consistent) && (
          <span className="text-amber-600">
            This result set was produced for a different workload than the JOB plans shown here, so its nodes
            cannot be mapped. Pick a JOB result set (e.g. job_*).
          </span>
        )}
        {algoNames.map((a) => {
          const on = algos.includes(a);
          const bad = !chosen[a].consistent;
          return (
            <button
              key={a}
              disabled={bad}
              onClick={() => setAlgos(on ? algos.filter((x) => x !== a) : [...algos, a])}
              title={
                bad
                  ? "This result was produced with a different workload/node numbering; it cannot be mapped onto these plans"
                  : `${chosen[a].count} views selected`
              }
              className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs disabled:opacity-40 ${
                on ? "border-zinc-500" : "border-zinc-300 text-zinc-400 dark:border-zinc-700"
              }`}
            >
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{
                  background: on ? algorithmColor(a, algoNames) : "transparent",
                  outline: `1px solid ${algorithmColor(a, algoNames)}`,
                }}
              />
              {a}
              <span className="text-zinc-500">{chosen[a].count}</span>
            </button>
          );
        })}
        {picks.length >= 2 && (
          <div className="ml-2 flex items-center gap-1 text-xs" role="group" aria-label="Overlap filter">
            <span className="text-zinc-500">Show</span>
            {(
              [
                ["any", "all selected"],
                ["multi", "chosen by 2+"],
                ["all", "chosen by all"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setOverlap(key)}
                className={`rounded-full border px-2 py-0.5 ${
                  overlap === key
                    ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                    : "border-zinc-300 dark:border-zinc-700"
                }`}
              >
                {label} <span className="tabular-nums opacity-70">{overlapCounts[key]}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-md border border-zinc-200 p-2 text-sm dark:border-zinc-800">
        {selectedInfo?.sample ? (
          <>
            <b>{selectedInfo.sample["Node Type"]}</b>
            {selectedInfo.sample["Relation Name"] ? ` · ${selectedInfo.sample["Relation Name"]}` : ""} — in{" "}
            {selectedInfo.queries.length} queries: {selectedInfo.queries.join(", ")}
            <button className="ml-3 text-zinc-500 underline" onClick={() => setSelected(null)}>
              clear
            </button>
          </>
        ) : (
          <span className="text-zinc-500">
            Click a node to highlight the same node in every query. Drag or scroll to pan, Ctrl/⌘ + scroll
            (or pinch) to zoom at the cursor; zoom in to read node details.
          </span>
        )}
      </div>

      <div ref={wrapperRef} className="relative min-h-0 flex-1">
      <div
        ref={canvasRef}
        className="h-full cursor-grab overflow-hidden rounded-md border border-zinc-200 active:cursor-grabbing dark:border-zinc-800"
        onPointerDown={onPointerDown}
      >
        <svg
          width="100%"
          height="100%"
          onClick={() => !dragged.current && setSelected(null)}
          className="select-none"
        >
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
            {world.placed.map((p) => (
              <PlanCard
                key={p.item.id}
                placed={p}
                px={view.k}
                selected={selected}
                onSelect={setSelected}
                dragged={dragged}
                picks={picks}
                overlap={overlap}
                onOpen={openQuery}
                active={p.item.id === openId}
              />
            ))}
          </g>
        </svg>
      </div>

      {openCard && rect && (
        <div
          className="fixed z-50 flex flex-col rounded-lg border border-zinc-300 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
          style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }}
        >
          {HANDLES.map((h) => (
            <div
              key={h.dir}
              className={`absolute z-10 ${h.cls}`}
              onPointerDown={(e) => startPopupDrag(e, h.dir)}
            />
          ))}
          <div
            className="flex cursor-move items-center gap-2 border-b border-zinc-200 px-3 py-1.5 text-sm dark:border-zinc-800"
            onPointerDown={(e) => {
              if (!(e.target as HTMLElement).closest("button, a")) startPopupDrag(e, "move");
            }}
          >
            <b>{openCard.item.id}</b>
            <a href={`/queries/${openCard.item.id}`} className="text-zinc-500 underline">
              Open page
            </a>
            <div className="ml-auto flex items-center gap-1">
              <button className="rounded border px-2" onClick={() => popupZoomAt(1 / 1.25)} aria-label="Zoom out popup">
                −
              </button>
              <span className="w-10 text-center tabular-nums text-zinc-500">{Math.round(popupK * 100)}%</span>
              <button className="rounded border px-2" onClick={() => popupZoomAt(1.25)} aria-label="Zoom in popup">
                +
              </button>
              <button className="rounded border px-2" onClick={fitPopup} title="Fit the whole plan in the popup">
                Fit
              </button>
              <button className="ml-2 rounded px-2 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800" onClick={() => setOpenId(null)} aria-label="Close">
                ✕
              </button>
            </div>
          </div>
          <div ref={popupRef} className="min-h-0 flex-1 overflow-auto">
            <svg width={openCard.w * popupK} height={openCard.h * popupK} viewBox={`0 0 ${openCard.w} ${openCard.h}`} className="select-none">
              <PlanCard
                placed={{ ...openCard, x: 0, y: 0 }}
                px={popupK}
                selected={selected}
                onSelect={setSelected}
                dragged={popupDragged}
                dim={false}
                picks={picks}
                overlap={overlap}
              />
            </svg>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
