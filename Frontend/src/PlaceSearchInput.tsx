import { useEffect, useRef, useState } from 'react'

// 백엔드가 카카오 '키워드로 장소 검색'을 대신 불러주는 프록시.
// 카카오맵 JS SDK는 여기서 로드하지 않는다 — 화면에 실제 지도를 붙이는 작업(그쪽에서
// SDK를 로드/설정함)과 완전히 분리해서 충돌 없이 병행할 수 있게 하기 위해서다.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000'

export type PlaceHit = { name: string; address: string; lat: number; lng: number }

/**
 * 직장/학교 등 "이름만 입력해서는 좌표를 알 수 없는" 위치 입력 필드.
 * 두 글자 이상 입력하면 debounce 후 /api/places를 호출해 후보를 드롭다운으로 보여주고,
 * 사용자가 후보 하나를 고르면 그때 실제 좌표(lat/lng)를 상위로 넘긴다.
 * 자유 텍스트만 입력하고 후보를 고르지 않으면 좌표는 비어 있는 채로 남는다 — 그래야
 * "장소명만 입력해서는 소용없다"는 문제가 실제로 해결된다.
 */
export function PlaceSearchInput({
  value,
  onChange,
  onSelectPlace,
  dense = false,
  placeholder,
}: {
  value: string
  onChange: (text: string) => void
  onSelectPlace: (place: PlaceHit) => void
  dense?: boolean
  placeholder?: string
}) {
  const [results, setResults] = useState<PlaceHit[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const requestSeq = useRef(0)

  // Close the dropdown on outside click.
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  // Debounced search whenever the typed text changes.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = value.trim()
    if (q.length < 2) {
      setResults([])
      setLoading(false)
      return
    }
    const seq = ++requestSeq.current
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await fetch(`${API_BASE}/api/places?query=${encodeURIComponent(q)}&limit=5`)
        if (!res.ok) throw new Error(String(res.status))
        const data = await res.json()
        if (seq !== requestSeq.current) return // a newer keystroke already superseded this
        setResults(data.results ?? [])
        setOpen(true)
      } catch {
        if (seq === requestSeq.current) setResults([])
      } finally {
        if (seq === requestSeq.current) setLoading(false)
      }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [value])

  return (
    <div className="relative" ref={wrapRef}>
      <div
        className={`flex items-center gap-2 border border-[#ede9e2] rounded-xl px-3 bg-[#faf9f7] ${dense ? 'py-2' : 'py-2.5'}`}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="6" r="3" stroke="#bbb" strokeWidth="1.2" />
          <path d="M7 12s4-3.5 4-6a4 4 0 1 0-8 0c0 2.5 4 6 4 6z" stroke="#bbb" strokeWidth="1.2" fill="none" />
        </svg>
        <input
          type="text"
          value={value}
          placeholder={placeholder}
          onChange={e => { onChange(e.target.value); setOpen(true) }}
          onFocus={() => { if (results.length) setOpen(true) }}
          className="flex-1 text-sm outline-none bg-transparent text-[#333] placeholder-[#ccc]"
        />
      </div>

      {open && (loading || results.length > 0) && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-white border border-[#ede9e2] rounded-xl shadow-lg max-h-56 overflow-y-auto">
          {loading && <div className="px-3 py-2 text-xs text-[#bbb]">검색 중…</div>}
          {!loading && results.map((r, i) => (
            <button
              key={`${r.name}-${i}`}
              type="button"
              onClick={() => { onSelectPlace(r); onChange(r.name); setOpen(false) }}
              className="w-full text-left px-3 py-2 hover:bg-[#f7f5f0] transition-colors"
            >
              <div className="text-sm text-[#2d2a24]">{r.name}</div>
              {r.address && <div className="text-[10px] text-[#bbb] mt-0.5 truncate">{r.address}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
