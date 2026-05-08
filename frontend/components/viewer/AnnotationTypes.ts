// Pure types/constants shared by the annotation system. No DOM / OSD imports
// here, so this module is safe to load during SSR.

export type ToolKind =
  | "select"
  | "pen"
  | "arrow"
  | "rect"
  | "circle"
  | "measure"
  | "text"
  | "symbol"
  | "eraser"

export interface PathMindSymbol {
  id: string
  label: string
  glyph: string
  color?: string
  description: string
}

export const PATHMIND_SYMBOLS: PathMindSymbol[] = [
  { id: "atypia", label: "Atypie", glyph: "!", color: "#ff2d55", description: "Atypie cellulaire à confirmer" },
  { id: "mitose", label: "Mitose", glyph: "M", color: "#ff00d4", description: "Mitose / activité mitotique" },
  { id: "necrose", label: "Nécrose", glyph: "N", color: "#ffea00", description: "Foyer de nécrose" },
  { id: "lvi", label: "LVI", glyph: "V", color: "#ff7a00", description: "Invasion lymphovasculaire" },
  { id: "pni", label: "PNI", glyph: "P", color: "#ff7a00", description: "Invasion périnerveuse" },
  { id: "marge", label: "Marge", glyph: "X", color: "#ff2d55", description: "Marge limite / atteinte" },
  { id: "tumor", label: "Tumeur", glyph: "T", color: "#ff00d4", description: "Foyer tumoral" },
  { id: "stroma", label: "Stroma", glyph: "S", color: "#00ff88", description: "Stroma desmoplastique" },
  { id: "ihc", label: "IHC", glyph: "I", color: "#00f0ff", description: "Cible pour IHC" },
  { id: "review", label: "Revue", glyph: "?", color: "#ffea00", description: "À discuter / second avis" },
]

export interface Shape {
  id: string
  caseId: string
  slideIndex: number
  type: ToolKind
  // IMAGE pixel coords (native WSI pixel space)
  points?: { x: number; y: number }[]
  start?: { x: number; y: number }
  end?: { x: number; y: number }
  text?: string
  symbol?: PathMindSymbol
  color: string
  strokeWidth: number
  createdAt: number
}
