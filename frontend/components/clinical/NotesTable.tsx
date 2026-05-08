"use client"

import { useState, useEffect, useCallback } from "react"

export interface Note {
  id: string
  caseId: string
  slideIndex: number
  slideName: string
  // Optional pin coordinates in normalized image space (0..1)
  pinX?: number
  pinY?: number
  text: string
  author: string
  createdAt: number
  updatedAt: number
  category: "observation" | "diagnostic" | "question" | "todo"
}

const CATEGORY_LABEL: Record<Note["category"], string> = {
  observation: "Observation",
  diagnostic: "Diagnostic",
  question: "Question",
  todo: "À faire",
}

const CATEGORY_COLOR: Record<Note["category"], string> = {
  observation: "var(--ink-soft)",
  diagnostic: "var(--accent)",
  question: "var(--warn)",
  todo: "var(--ok)",
}

const STORAGE_KEY = "pathmind:notes:v1"

function loadNotes(): Note[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as Note[]
  } catch {
    return []
  }
}

function saveNotes(notes: Note[]) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(notes))
}

export function useNotes(caseId: string | undefined) {
  const [notes, setNotes] = useState<Note[]>([])

  useEffect(() => {
    setNotes(loadNotes())
  }, [])

  const all = notes
  const forCase = caseId ? notes.filter((n) => n.caseId === caseId) : []

  const add = useCallback((n: Omit<Note, "id" | "createdAt" | "updatedAt">) => {
    const id = `note-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const now = Date.now()
    const note: Note = { ...n, id, createdAt: now, updatedAt: now }
    setNotes((prev) => {
      const next = [note, ...prev]
      saveNotes(next)
      return next
    })
    return note
  }, [])

  const update = useCallback((id: string, patch: Partial<Note>) => {
    setNotes((prev) => {
      const next = prev.map((n) => (n.id === id ? { ...n, ...patch, updatedAt: Date.now() } : n))
      saveNotes(next)
      return next
    })
  }, [])

  const remove = useCallback((id: string) => {
    setNotes((prev) => {
      const next = prev.filter((n) => n.id !== id)
      saveNotes(next)
      return next
    })
  }, [])

  return { notes: forCase, all, add, update, remove }
}

interface NotesTableProps {
  caseId: string | undefined
  caseLabel: string | undefined
  slideIndex: number
  slideName: string
  notes: Note[]
  onAdd: (note: Omit<Note, "id" | "createdAt" | "updatedAt">) => void
  onUpdate: (id: string, patch: Partial<Note>) => void
  onRemove: (id: string) => void
  onJumpToPin: (note: Note) => void
}

export function NotesTable({
  caseId,
  caseLabel,
  slideIndex,
  slideName,
  notes,
  onAdd,
  onUpdate,
  onRemove,
  onJumpToPin,
}: NotesTableProps) {
  const [draft, setDraft] = useState("")
  const [draftCategory, setDraftCategory] = useState<Note["category"]>("observation")
  const [filterSlide, setFilterSlide] = useState<"all" | "current">("all")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingText, setEditingText] = useState("")

  const visibleNotes =
    filterSlide === "current" ? notes.filter((n) => n.slideIndex === slideIndex) : notes

  const handleAdd = () => {
    if (!caseId || !draft.trim()) return
    onAdd({
      caseId,
      slideIndex,
      slideName,
      text: draft.trim(),
      author: "Praticien",
      category: draftCategory,
    })
    setDraft("")
  }

  const handleExport = () => {
    if (!notes.length) return
    const lines: string[] = []
    lines.push(`# Notes — ${caseLabel ?? caseId}`)
    lines.push(`# Exporté le ${new Date().toLocaleString("fr-FR")}`)
    lines.push("")
    for (const n of notes) {
      lines.push(`## [${CATEGORY_LABEL[n.category]}] ${n.slideName}`)
      lines.push(`Date : ${new Date(n.createdAt).toLocaleString("fr-FR")}`)
      if (n.pinX != null && n.pinY != null) {
        lines.push(`Pin : x=${n.pinX.toFixed(3)}, y=${n.pinY.toFixed(3)}`)
      }
      lines.push("")
      lines.push(n.text)
      lines.push("")
      lines.push("---")
      lines.push("")
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `notes-${caseId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!caseId) {
    return (
      <div className="border border-[var(--rule-strong)] bg-[var(--paper)] p-6">
        <div className="smcaps mb-2">Notes du praticien</div>
        <div className="text-sm text-[var(--muted)] font-serif italic">
          Sélectionnez un cas pour commencer à prendre des notes.
        </div>
      </div>
    )
  }

  return (
    <div className="border border-[var(--rule-strong)] bg-[var(--paper)] flex flex-col">
      {/* Header */}
      <div className="px-5 py-4 border-b border-[var(--rule-strong)] flex items-center justify-between gap-3">
        <div>
          <div className="smcaps">Carnet de bord clinique</div>
          <div className="font-serif text-[18px] font-semibold tracking-tight">
            Notes du praticien
            <span className="ml-2.5 font-mono text-[11px] text-[var(--muted)]">
              {notes.length} entrée{notes.length > 1 ? "s" : ""}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="flex border border-[var(--rule-strong)]">
            <button
              type="button"
              onClick={() => setFilterSlide("all")}
              className={`h-7 px-2.5 text-[10px] font-mono uppercase tracking-widest ${
                filterSlide === "all"
                  ? "bg-[var(--ink)] text-[var(--paper)]"
                  : "bg-transparent text-[var(--muted)] hover:text-[var(--ink)]"
              }`}
            >
              Tout
            </button>
            <button
              type="button"
              onClick={() => setFilterSlide("current")}
              className={`h-7 px-2.5 text-[10px] font-mono uppercase tracking-widest border-l border-[var(--rule-strong)] ${
                filterSlide === "current"
                  ? "bg-[var(--ink)] text-[var(--paper)]"
                  : "bg-transparent text-[var(--muted)] hover:text-[var(--ink)]"
              }`}
            >
              Lame {slideIndex + 1}
            </button>
          </div>
          <button
            type="button"
            onClick={handleExport}
            disabled={!notes.length}
            className="h-7 px-2.5 text-[10px] font-mono uppercase tracking-widest border border-[var(--rule-strong)] hover:bg-[var(--paper-2)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Exporter .md
          </button>
        </div>
      </div>

      {/* Composer */}
      <div className="px-5 py-4 border-b border-[var(--rule-strong)] bg-[var(--paper-2)]/50">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--muted)]">
            Nouvelle note · {slideName}
          </div>
          <div className="flex gap-1">
            {(Object.keys(CATEGORY_LABEL) as Note["category"][]).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setDraftCategory(c)}
                className={`h-6 px-2 text-[10px] font-mono uppercase tracking-widest border ${
                  draftCategory === c
                    ? "border-[var(--ink)] bg-[var(--ink)] text-[var(--paper)]"
                    : "border-[var(--rule)] text-[var(--muted)] hover:text-[var(--ink)]"
                }`}
              >
                {CATEGORY_LABEL[c]}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Saisissez votre observation, hypothèse diagnostique ou question..."
            rows={3}
            className="flex-1 resize-none bg-[var(--paper)] border border-[var(--rule-strong)] px-3 py-2 text-[13px] font-serif text-[var(--ink)] placeholder:text-[var(--muted)] focus:outline-none focus:ring-1 focus:ring-[var(--ink)]"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                handleAdd()
              }
            }}
          />
          <button
            type="button"
            onClick={handleAdd}
            disabled={!draft.trim()}
            className="self-stretch px-4 text-[11px] font-mono uppercase tracking-widest bg-[var(--accent)] text-[var(--paper)] disabled:opacity-30 disabled:cursor-not-allowed hover:opacity-90"
          >
            Ajouter
          </button>
        </div>
        <div className="text-[10px] font-mono text-[var(--muted)] mt-1.5">
          Astuce : ⌘+Entrée pour ajouter · cliquez sur la lame pour épingler une note à un point précis
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 min-h-0">
        {visibleNotes.length === 0 ? (
          <div className="px-5 py-10 text-center text-[var(--muted)] font-serif italic text-sm">
            Aucune note pour le moment. Commencez à annoter.
          </div>
        ) : (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-[var(--rule-strong)] bg-[var(--paper-2)]">
                <th className="text-left px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] w-[88px]">
                  Cat.
                </th>
                <th className="text-left px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] w-[108px]">
                  Lame
                </th>
                <th className="text-left px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">
                  Annotation
                </th>
                <th className="text-left px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] w-[120px]">
                  Horodatage
                </th>
                <th className="text-right px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] w-[84px]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleNotes.map((n) => {
                const isEditing = editingId === n.id
                return (
                  <tr
                    key={n.id}
                    className="border-b border-[var(--rule)] hover:bg-[var(--paper-2)]/40 align-top"
                  >
                    <td className="px-4 py-3">
                      <span
                        className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest"
                        style={{ color: CATEGORY_COLOR[n.category] }}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full"
                          style={{ background: CATEGORY_COLOR[n.category] }}
                        />
                        {CATEGORY_LABEL[n.category]}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-mono text-[11px] text-[var(--ink-soft)] truncate">
                        {n.slideName}
                      </div>
                      {n.pinX != null && n.pinY != null && (
                        <button
                          type="button"
                          onClick={() => onJumpToPin(n)}
                          className="mt-1 text-[10px] font-mono text-[var(--accent)] hover:underline"
                        >
                          Voir épingle
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <textarea
                          value={editingText}
                          onChange={(e) => setEditingText(e.target.value)}
                          rows={3}
                          className="w-full resize-none bg-[var(--paper)] border border-[var(--rule-strong)] px-2 py-1.5 text-[12px] font-serif text-[var(--ink)] focus:outline-none focus:ring-1 focus:ring-[var(--ink)]"
                          autoFocus
                        />
                      ) : (
                        <div className="font-serif text-[13px] text-[var(--ink)] leading-snug whitespace-pre-wrap">
                          {n.text}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-[var(--muted)] whitespace-nowrap">
                      {new Date(n.createdAt).toLocaleString("fr-FR", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                      {n.updatedAt !== n.createdAt && (
                        <div className="text-[10px] italic">modifié</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1.5">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                if (editingText.trim()) {
                                  onUpdate(n.id, { text: editingText.trim() })
                                }
                                setEditingId(null)
                              }}
                              className="h-6 px-2 text-[10px] font-mono uppercase tracking-widest border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--paper)]"
                            >
                              OK
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingId(null)}
                              className="h-6 px-2 text-[10px] font-mono uppercase tracking-widest border border-[var(--rule)] text-[var(--muted)]"
                            >
                              Annul.
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingId(n.id)
                                setEditingText(n.text)
                              }}
                              className="h-6 px-2 text-[10px] font-mono uppercase tracking-widest border border-[var(--rule-strong)] text-[var(--ink-soft)] hover:bg-[var(--ink)] hover:text-[var(--paper)]"
                            >
                              Éditer
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                if (confirm("Supprimer cette note ?")) onRemove(n.id)
                              }}
                              className="h-6 px-2 text-[10px] font-mono uppercase tracking-widest border border-[var(--rule-strong)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--paper)]"
                            >
                              Suppr.
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
