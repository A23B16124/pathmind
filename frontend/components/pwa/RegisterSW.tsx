"use client"
import { useEffect } from "react"

export function RegisterSW() {
  useEffect(() => {
    if (typeof window === "undefined") return
    if (!("serviceWorker" in navigator)) return
    const onLoad = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {})
    }
    if (document.readyState === "complete") onLoad()
    else window.addEventListener("load", onLoad, { once: true })
    return () => window.removeEventListener("load", onLoad)
  }, [])
  return null
}
