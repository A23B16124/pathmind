"use client"

import { useState } from "react"
import { type ToolKind, type PathMindSymbol, PATHMIND_SYMBOLS } from "./AnnotationTypes"

interface AnnotationToolbarProps {
  tool: ToolKind
  setTool: (t: ToolKind) => void
  color: string
  setColor: (c: string) => void
  strokeWidth: number
  setStrokeWidth: (w: number) => void
  selectedSymbol: PathMindSymbol | null
  setSelectedSymbol: (s: PathMindSymbol | null) => void
  shapeCount: number
  onUndo: () => void
  onClear: () => void
  disabled: boolean
}

const TOOLS: { id: ToolKind; label: string; icon: React.ReactNode; desc: string }[] = [
  {
    id: "select",
    label: "Naviguer",
    desc: "Pan / zoom (annotation off)",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M3 3l3.5 9.5L8 9l3 1L3 3z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" fill="none" />
      </svg>
    ),
  },
  {
    id: "pen",
    label: "Stylo",
    desc: "Tracé libre",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M11 2l3 3-8.5 8.5L2 14l.5-3.5L11 2z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill="none" />
      </svg>
    ),
  },
  {
    id: "arrow",
    label: "Flèche",
    desc: "Pointer une zone",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M2 8h11M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" fill="none" />
      </svg>
    ),
  },
  {
    id: "measure",
    label: "Mesurer",
    desc: "Distance en µm",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M2 11l9-9M2 11h2M2 11v-2M11 2l2 2-2 2M2 11l-1 1 1 1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    ),
  },
  {
    id: "rect",
    label: "Rect",
    desc: "Rectangle",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="3" y="4" width="10" height="8" stroke="currentColor" strokeWidth="1.3" fill="none" />
      </svg>
    ),
  },
  {
    id: "circle",
    label: "Cercle",
    desc: "Cercle",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.3" fill="none" />
      </svg>
    ),
  },
  {
    id: "text",
    label: "Texte",
    desc: "Saisir une étiquette",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M3 4V3h10v1M8 3v10M5 13h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" fill="none" />
      </svg>
    ),
  },
  {
    id: "symbol",
    label: "Symbole",
    desc: "Symboles PathMind",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.3" fill="none" />
        <path d="M8 5v4M8 11v.01" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "eraser",
    label: "Gomme",
    desc: "Supprimer un tracé",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M3 13l3-3 6 6h-3L3 13zM6 10l4-4 3 3-4 4M9 5l3-3 1 1-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill="none" />
      </svg>
    ),
  },
]

const COLORS = [
  { id: "yellow", value: "#ffea00", label: "Jaune fluo" },
  { id: "magenta", value: "#ff00d4", label: "Magenta" },
  { id: "cyan", value: "#00f0ff", label: "Cyan" },
  { id: "green", value: "#00ff88", label: "Vert fluo" },
  { id: "orange", value: "#ff7a00", label: "Orange" },
  { id: "red", value: "#ff2d55", label: "Rouge fluo" },
]

const STROKES = [
  { value: 1.5, label: "Fin" },
  { value: 2.5, label: "Med" },
  { value: 4, label: "Épais" },
]

export function AnnotationToolbar({
  tool,
  setTool,
  color,
  setColor,
  strokeWidth,
  setStrokeWidth,
  selectedSymbol,
  setSelectedSymbol,
  shapeCount,
  onUndo,
  onClear,
  disabled,
}: AnnotationToolbarProps) {
  const [symbolMenuOpen, setSymbolMenuOpen] = useState(false)

  return (
    <div
      className={`bg-[var(--paper)]/97 border border-[var(--rule-strong)] flex items-center gap-1 px-1.5 py-1.5 shadow-lg ${
        disabled ? "opacity-60 pointer-events-none" : ""
      }`}
    >
      {/* Tool group */}
      <div className="flex items-center gap-0.5">
        {TOOLS.map((t) => {
          const active = tool === t.id
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                if (t.id === "symbol") {
                  setSymbolMenuOpen((v) => !v)
                  setTool("symbol")
                  if (!selectedSymbol) setSelectedSymbol(PATHMIND_SYMBOLS[0])
                } else {
                  setSymbolMenuOpen(false)
                  setTool(t.id)
                }
              }}
              title={`${t.label} — ${t.desc}`}
              className={`relative w-8 h-8 grid place-items-center border ${
                active
                  ? "bg-[var(--ink)] text-[var(--paper)] border-[var(--ink)]"
                  : "bg-transparent text-[var(--ink-soft)] border-[var(--rule)] hover:bg-[var(--paper-2)] hover:border-[var(--ink-soft)]"
              }`}
            >
              {t.icon}
            </button>
          )
        })}
      </div>

      <div className="w-px h-6 bg-[var(--rule)]" />

      {/* Color group */}
      <div className="flex items-center gap-1">
        {COLORS.map((c) => {
          const active = color === c.value
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => setColor(c.value)}
              title={c.label}
              className={`w-6 h-6 grid place-items-center border ${
                active ? "border-[var(--ink)] ring-1 ring-[var(--ink)] ring-offset-1 ring-offset-[var(--paper)]" : "border-[var(--rule)]"
              }`}
            >
              <span className="block w-3.5 h-3.5 rounded-full" style={{ background: c.value }} />
            </button>
          )
        })}
      </div>

      <div className="w-px h-6 bg-[var(--rule)]" />

      {/* Stroke width */}
      <div className="flex items-center gap-0.5">
        {STROKES.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => setStrokeWidth(s.value)}
            title={`Trait ${s.label}`}
            className={`w-7 h-8 grid place-items-center border ${
              strokeWidth === s.value
                ? "bg-[var(--ink)] border-[var(--ink)]"
                : "bg-transparent border-[var(--rule)] hover:bg-[var(--paper-2)]"
            }`}
          >
            <span
              className="block rounded-full"
              style={{
                width: 14,
                height: Math.max(2, s.value),
                background: strokeWidth === s.value ? "var(--paper)" : "var(--ink-soft)",
              }}
            />
          </button>
        ))}
      </div>

      <div className="w-px h-6 bg-[var(--rule)]" />

      {/* Actions */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onUndo}
          disabled={shapeCount === 0}
          title="Annuler le dernier tracé"
          className="h-8 px-2.5 text-[10px] font-mono uppercase tracking-widest border border-[var(--rule)] text-[var(--ink-soft)] hover:bg-[var(--paper-2)] disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Annuler
        </button>
        <button
          type="button"
          onClick={() => {
            if (shapeCount > 0 && confirm("Effacer toutes les annotations de cette lame ?")) onClear()
          }}
          disabled={shapeCount === 0}
          title="Tout effacer (cette lame)"
          className="h-8 px-2.5 text-[10px] font-mono uppercase tracking-widest border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--paper)] disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Tout effacer
        </button>
        <span className="font-mono text-[10px] text-[var(--muted)] px-1">
          {shapeCount} tracé{shapeCount > 1 ? "s" : ""}
        </span>
      </div>

      {/* Symbol palette popover */}
      {symbolMenuOpen && (
        <div className="absolute top-[calc(100%+6px)] right-0 z-30 bg-[var(--paper)] border border-[var(--rule-strong)] shadow-2xl p-3 w-[300px]">
          <div className="smcaps mb-2">Symboles PathMind</div>
          <div className="grid grid-cols-2 gap-1.5">
            {PATHMIND_SYMBOLS.map((sym) => {
              const active = selectedSymbol?.id === sym.id
              return (
                <button
                  key={sym.id}
                  type="button"
                  onClick={() => {
                    setSelectedSymbol(sym)
                    setSymbolMenuOpen(false)
                  }}
                  className={`flex items-center gap-2 px-2 py-1.5 border text-left ${
                    active
                      ? "border-[var(--ink)] bg-[var(--paper-2)]"
                      : "border-[var(--rule)] hover:bg-[var(--paper-2)]"
                  }`}
                  title={sym.description}
                >
                  <span
                    className="w-6 h-6 rounded-full grid place-items-center font-mono font-bold text-[12px] shrink-0"
                    style={{ background: "rgba(244,241,234,0.95)", color: sym.color, border: `1.5px solid ${sym.color}` }}
                  >
                    {sym.glyph}
                  </span>
                  <div className="min-w-0">
                    <div className="font-serif text-[12px] font-semibold text-[var(--ink)] truncate">{sym.label}</div>
                    <div className="font-mono text-[9.5px] text-[var(--muted)] truncate">{sym.description}</div>
                  </div>
                </button>
              )
            })}
          </div>
          {selectedSymbol && (
            <div className="mt-2.5 pt-2.5 border-t border-[var(--rule)] flex items-center justify-between">
              <span className="font-mono text-[10px] text-[var(--muted)]">
                Actif · cliquez sur la lame pour placer
              </span>
              <button
                type="button"
                onClick={() => {
                  setSelectedSymbol(null)
                  setTool("select")
                  setSymbolMenuOpen(false)
                }}
                className="font-mono text-[10px] uppercase tracking-widest text-[var(--accent)] hover:underline"
              >
                Désactiver
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
