import { useState, useRef, useEffect, Fragment } from 'react'
import { fetchCommute, searchListings } from './api'
import type { ApiStop, Commute, Listing, PathSegment, SortBy } from './api'

type LatLng = { lat: number; lng: number }

// Real-world Seoul subway line colors, used so route lines read like an actual transit map
const LINE_COLORS: Record<string, string> = {
  '1호선': '#0052A4', '2호선': '#00A84D', '3호선': '#EF7C1C', '4호선': '#00A5DE',
  '5호선': '#996CAC', '6호선': '#CD7C2F', '7호선': '#747F00', '8호선': '#E6186C',
  '9호선': '#BDB092', '경의중앙선': '#77C4A3', '경춘선': '#0C8E72', '수인분당선': '#F0B000',
  '신분당선': '#D4003B', '공항철도': '#0090D2', '서해선': '#81A914', '경강선': '#003DA5',
  '인천1호선': '#7CA8D5', '인천2호선': '#ED8B00', '우이신설선': '#B0CE18', '신림선': '#6789CA',
  '김포골드라인': '#A17800', '용인에버라인': '#509F22', '의정부경전철': '#FDA600', 'GTX-A': '#9A6292',
}
const BUS_COLOR = '#2563eb'

// One stop along a person's commute. `mode`/`line`/`color` describe the leg *arriving* at this stop
// (the first stop in a route has none, since there's no leg before it).
type Stop = LatLng & { name: string; mode?: 'subway' | 'bus'; line?: string; color?: string }

/** 백엔드 stop → 화면 Stop. 노선 색만 여기서 입힌다. */
const toStop = (s: ApiStop): Stop => ({
  name: s.name,
  lat: s.lat,
  lng: s.lng,
  mode: s.mode,
  line: s.line,
  color: s.mode === 'bus' ? BUS_COLOR : (s.line ? LINE_COLORS[s.line] ?? '#999' : undefined),
})

const eok = (manwon: number) =>
  manwon >= 10000 ? `${(manwon / 10000).toFixed(manwon % 10000 === 0 ? 0 : 1)}억` : `${manwon.toLocaleString()}만`

/**
 * 슬라이더로 거르는 값은 **환산월세**(월세 + 보증금 이자)다.
 * 보증금 1.2억 / 월세 18만짜리를 "18만원/월"로 찍으면 "30~70으로 골랐는데 왜 18만?"이 된다.
 * 그래서 큰 숫자는 환산월세로 올리고, 실제 계약 조건은 아래 줄에 둔다.
 */
const priceLabel = (p: Listing) => `월 ${p.monthlyEquivalent}만원 상당`

/** 지도 마커처럼 좁은 자리에 쓰는 짧은 표기. */
const shortPrice = (p: Listing) => `월 ${p.monthlyEquivalent}만`

/** 실제 계약 조건. 전세면 보증금만, 월세면 보증금/월세. */
const termsLabel = (p: Listing) =>
  p.leaseType === '전세'
    ? `전세 ${eok(p.deposit)}`
    : `보증금 ${eok(p.deposit)} / 월세 ${p.price}만`

type Conditions = {
  p1Work: string; p2Work: string
  p1Price: number[]; p2Price: number[]
  p1Area: number[]; p2Area: number[]
}

// ---------- Kakao Maps wiring ----------
// Kakao's SDK is loaded from index.html with `autoload=false`, so we kick off
// `kakao.maps.load` ourselves once the script tag has landed on `window.kakao`.
function useKakaoReady() {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const w = window as any
    let cancelled = false
    const tryLoad = () => {
      if (w.kakao?.maps) {
        w.kakao.maps.load(() => { if (!cancelled) setReady(true) })
        return true
      }
      return false
    }
    if (!tryLoad()) {
      const id = setInterval(() => { if (tryLoad()) clearInterval(id) }, 100)
      return () => { cancelled = true; clearInterval(id) }
    }
    return () => { cancelled = true }
  }, [])
  return ready
}

// Given free text like "강남역", resolves it to coordinates via Kakao's keyword place search.
function geocodeKeyword(keyword: string): Promise<LatLng | null> {
  return new Promise(resolve => {
    const kakao = (window as any).kakao
    if (!keyword?.trim() || !kakao?.maps?.services) return resolve(null)
    const places = new kakao.maps.services.Places()
    places.keywordSearch(keyword, (data: any[], status: string) => {
      if (status === kakao.maps.services.Status.OK && data[0]) {
        resolve({ lat: parseFloat(data[0].y), lng: parseFloat(data[0].x) })
      } else {
        resolve(null)
      }
    })
  })
}

type PlaceHit = { name: string; address: string; lat: number; lng: number }

// Text input with a live Kakao keyword-search dropdown underneath — type "고려대학교",
// "스타벅스 역삼점", any place or business name, and pick the exact match instead of
// hoping the first geocoder guess is right.
function WorkSearchInput({ value, onChange, onPick, picked }: {
  value: string; onChange: (text: string) => void; onPick: (text: string, coord: LatLng) => void
  /** 드롭다운에서 실제로 고른 값인지. 직접 친 글자는 첫 검색결과로 추측 지오코딩된다. */
  picked: boolean
}) {
  const [results, setResults] = useState<PlaceHit[]>([])
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const kakao = (window as any).kakao
    if (!value.trim() || !kakao?.maps?.services) { setResults([]); return }
    const t = setTimeout(() => {
      const places = new kakao.maps.services.Places()
      places.keywordSearch(value, (data: any[], status: string) => {
        if (status === kakao.maps.services.Status.OK) {
          setResults(data.slice(0, 6).map(d => ({ name: d.place_name, address: d.road_address_name || d.address_name, lat: parseFloat(d.y), lng: parseFloat(d.x) })))
        } else {
          setResults([])
        }
      })
    }, 250)
    return () => clearTimeout(t)
  }, [value])

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  return (
    <div className="relative" ref={boxRef}>
      <div className={`flex items-center gap-2 border rounded-xl px-3 py-2.5 bg-[#faf9f7] transition-colors ${picked ? 'border-[#ede9e2]' : 'border-[#e3d3cb]'}`}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="6" r="3" stroke="#bbb" strokeWidth="1.2" /><path d="M7 12s4-3.5 4-6a4 4 0 1 0-8 0c0 2.5 4 6 4 6z" stroke="#bbb" strokeWidth="1.2" fill="none" /></svg>
        <input
          type="text"
          value={value}
          onChange={e => { onChange(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="예: 고려대학교, 강남역, 스타벅스 역삼점"
          className="flex-1 text-sm outline-none bg-transparent text-[#333] placeholder-[#ccc]"
        />
        {picked && (
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-label="위치 확정됨">
            <path d="M2.5 7.3l3 3 6-6.6" stroke="#16a34a" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
      {!picked && value.trim() && (
        <p className="mt-1.5 px-1 text-[11px] leading-snug text-[#b08276]">
          목록에서 골라 주세요. 그냥 두면 첫 검색 결과로 추측합니다.
        </p>
      )}
      {open && results.length > 0 && (
        <div className="absolute z-50 left-0 right-0 mt-1.5 bg-white border border-[#ede9e2] rounded-xl shadow-lg max-h-56 overflow-y-auto">
          {results.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => { onPick(r.name, { lat: r.lat, lng: r.lng }); setOpen(false) }}
              className="w-full text-left px-3 py-2 hover:bg-[#f7f5f0] border-b border-[#f0ece6] last:border-0"
            >
              <div className="text-sm text-[#2d2a24]">{r.name}</div>
              <div className="text-xs text-[#aaa] truncate">{r.address}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Fills its parent (must be `relative`) with a live Kakao map, auto-fit to `fitPoints`.
// Children are provided via render-prop once the map instance exists, so overlays/
// polylines never try to attach before there's a map to attach to.
//
// The tile layer, an optional dimming wash, and our own marker layer are three
// stacked siblings (not nested) — that's what lets `dim` fade only the map tiles
// while `KakaoOverlay` markers (rendered in the top layer, positioned by hand via
// the map's projection) stay fully crisp on top of the wash.
function KakaoMap({ fitPoints, level = 6, dim, children }: { fitPoints: LatLng[]; level?: number; dim?: boolean; children: (map: any) => React.ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<any>(null)
  const ready = useKakaoReady()

  useEffect(() => {
    if (!ready || !containerRef.current || map) return
    const kakao = (window as any).kakao
    const center = fitPoints[0] ?? { lat: 37.5665, lng: 126.9780 }
    setMap(new kakao.maps.Map(containerRef.current, { center: new kakao.maps.LatLng(center.lat, center.lng), level }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready])

  useEffect(() => {
    if (!map || fitPoints.length === 0) return
    const kakao = (window as any).kakao
    if (fitPoints.length === 1) {
      map.setCenter(new kakao.maps.LatLng(fitPoints[0].lat, fitPoints[0].lng))
      return
    }
    const bounds = new kakao.maps.LatLngBounds()
    fitPoints.forEach(p => bounds.extend(new kakao.maps.LatLng(p.lat, p.lng)))
    map.setBounds(bounds, 48)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, JSON.stringify(fitPoints)])

  return (
    <div className="absolute inset-0 w-full h-full overflow-hidden">
      <div ref={containerRef} className="absolute inset-0 w-full h-full bg-[#f5f4f0]" />
      {dim && <div className="absolute inset-0 pointer-events-none" style={{ background: 'rgba(255,255,255,0.78)' }} />}
      <div className="absolute inset-0 pointer-events-none">{map && children(map)}</div>
    </div>
  )
}

// A marker pinned to a lat/lng, positioned by hand via the map's projection instead of
// kakao.maps.CustomOverlay. CustomOverlay would physically move our content into Kakao's
// own tile-layer DOM, which is exactly the layer `dim` fades — rendering it ourselves in
// the marker layer above the wash is what keeps markers crisp while the map fades.
function KakaoOverlay({ map, lat, lng, zIndex, children }: { map: any; lat: number; lng: number; zIndex?: number; children: React.ReactNode }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)

  // Kakao's center_changed/zoom_changed only fire once a pan or zoom *settles* — during
  // the animated transition itself they stay silent, so a marker driven by those events
  // alone visibly freezes mid-zoom/mid-drag and then jumps at the end. Tracking every
  // frame instead keeps it glued to its geo point throughout the whole animation.
  useEffect(() => {
    const kakao = (window as any).kakao
    const latlng = new kakao.maps.LatLng(lat, lng)
    let raf: number
    let last: { x: number; y: number } | null = null
    const tick = () => {
      const p = map.getProjection().containerPointFromCoords(latlng)
      if (!last || last.x !== p.x || last.y !== p.y) {
        last = { x: p.x, y: p.y }
        setPos(last)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [map, lat, lng])

  if (!pos) return null
  return (
    <div className="absolute pointer-events-auto" style={{ left: pos.x, top: pos.y, transform: 'translate(-50%, -50%)', zIndex }}>
      {children}
    </div>
  )
}

function KakaoPolyline({ map, path, color, width = 4, opacity = 0.9, dashed = false }: {
  map: any; path: LatLng[]; color: string; width?: number; opacity?: number; dashed?: boolean
}) {
  useEffect(() => {
    const kakao = (window as any).kakao
    const line = new kakao.maps.Polyline({
      path: path.map(p => new kakao.maps.LatLng(p.lat, p.lng)),
      strokeWeight: width,
      strokeColor: color,
      strokeOpacity: opacity,
      strokeStyle: dashed ? 'shortdash' : 'solid',
    })
    line.setMap(map)
    return () => line.setMap(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, JSON.stringify(path), color, width, opacity, dashed])
  return null
}

// Reports the map's current zoom level to a parent, so it can switch between
// individual markers and clustered circles as the user zooms in/out.
function KakaoZoomWatcher({ map, onChange }: { map: any; onChange: (level: number) => void }) {
  useEffect(() => {
    const kakao = (window as any).kakao
    const handler = () => onChange(map.getLevel())
    handler()
    kakao.maps.event.addListener(map, 'zoom_changed', handler)
    return () => kakao.maps.event.removeListener(map, 'zoom_changed', handler)
  }, [map])
  return null
}

// Reports whether the map is currently moving — zooming *or* panning. Kakao's
// zoom_changed/center_changed events only fire once a transition settles, so instead
// we watch level+center every frame: any change means "moving", and we hold that for a
// short settle window afterward (covers Kakao's own zoom transition and any pan
// momentum) before declaring it idle again. Used to hide every marker while the map is
// in motion and pop them all back in together once it stops, instead of each marker
// trailing the map at its own pace.
function MapMotionWatcher({ map, onChange }: { map: any; onChange: (moving: boolean) => void }) {
  useEffect(() => {
    let raf: number
    let lastLevel = map.getLevel()
    let lastLat = map.getCenter().getLat()
    let lastLng = map.getCenter().getLng()
    let idleFrames = 0
    let moving = false
    const SETTLE_FRAMES = 22 // ~350ms at 60fps
    const tick = () => {
      const level = map.getLevel()
      const center = map.getCenter()
      const lat = center.getLat(), lng = center.getLng()
      const changed = level !== lastLevel || lat !== lastLat || lng !== lastLng
      lastLevel = level; lastLat = lat; lastLng = lng
      if (changed) {
        idleFrames = 0
        if (!moving) { moving = true; onChange(true) }
      } else if (moving) {
        idleFrames++
        if (idleFrames > SETTLE_FRAMES) { moving = false; onChange(false) }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [map])
  return null
}

// Renders a commute as real transit lines on the Kakao map: each leg is colored/styled by
// its actual subway line or bus route, with a thin person-colored halo underneath so it's
// still clear whose commute is whose. Also drops badges (e.g. "2호선", "🚌 740") at each
// leg's midpoint and small station dots along the way.
function segColor(seg: PathSegment): string {
  if (seg.mode === 'bus') return BUS_COLOR
  if (seg.mode === 'walk') return '#9aa0a6'
  return seg.line ? LINE_COLORS[seg.line] ?? '#999' : '#999'
}

function TransitRoute({ map, stops, personColor, path }: {
  map: any; stops: Stop[]; personColor: string
  /** 카카오가 준 실제 선로 좌표. 없으면(자체 엔진 결과) 정류장을 직선으로 잇는다. */
  path?: PathSegment[]
}) {
  if (stops.length < 2) return null

  // 실제 선로 좌표가 있으면 그걸로 그린다. 도보 구간은 점선 회색.
  const drawn = path?.length
    ? path.map((seg, i) => {
        const pts = seg.points.map(([lat, lng]) => ({ lat, lng }))
        if (pts.length < 2) return null
        const walk = seg.mode === 'walk'
        return (
          <Fragment key={`p${i}`}>
            {!walk && <KakaoPolyline map={map} path={pts} color={personColor} width={9} opacity={0.2} />}
            <KakaoPolyline
              map={map} path={pts} color={segColor(seg)}
              width={walk ? 3 : 5} dashed={walk || seg.mode === 'bus'}
              opacity={walk ? 0.75 : 0.95}
            />
            {seg.line && (
              <KakaoOverlay map={map} {...pts[Math.floor(pts.length / 2)]} zIndex={30}>
                <div className="text-[9px] font-600 text-white px-1.5 py-0.5 rounded-full shadow-sm whitespace-nowrap" style={{ background: segColor(seg) }}>
                  {seg.mode === 'bus' ? `🚌 ${seg.line}` : seg.line}
                </div>
              </KakaoOverlay>
            )}
          </Fragment>
        )
      })
    : stops.slice(1).map((to, i) => {
        const from = stops[i]
        const straight = [{ lat: from.lat, lng: from.lng }, { lat: to.lat, lng: to.lng }]
        const isBus = to.mode === 'bus'
        return (
          <Fragment key={i}>
            <KakaoPolyline map={map} path={straight} color={personColor} width={8} opacity={0.22} />
            <KakaoPolyline map={map} path={straight} color={to.color!} width={isBus ? 3 : 4} dashed={isBus} />
            {to.line && (
              <KakaoOverlay map={map} lat={(from.lat + to.lat) / 2} lng={(from.lng + to.lng) / 2} zIndex={30}>
                <div className="text-[9px] font-600 text-white px-1.5 py-0.5 rounded-full shadow-sm whitespace-nowrap" style={{ background: to.color }}>
                  {isBus ? `🚌 ${to.line}` : to.line}
                </div>
              </KakaoOverlay>
            )}
          </Fragment>
        )
      })

  return (
    <>
      {drawn}
      {stops.map((s, i) => (
        <KakaoOverlay key={i} map={map} lat={s.lat} lng={s.lng} zIndex={15}>
          <div
            className="rounded-full bg-white"
            style={{ width: i === 0 || i === stops.length - 1 ? 10 : 7, height: i === 0 || i === stops.length - 1 ? 10 : 7, border: `2px solid ${s.color ?? personColor}` }}
          />
        </KakaoOverlay>
      ))}
    </>
  )
}

function WorkMarker({ map, lat, lng, color, label }: { map: any; lat: number; lng: number; color: string; label: string }) {
  return (
    <KakaoOverlay map={map} lat={lat} lng={lng} zIndex={20}>
      <div className="flex flex-col items-center gap-1">
        <div className="w-8 h-8 rounded-full flex items-center justify-center shadow-md" style={{ background: color }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            {/* tall building */}
            <rect x="1" y="1" width="7" height="12" rx="0.3" stroke="white" strokeWidth="1.1" />
            <rect x="2.5" y="2.5" width="1.5" height="1.5" fill="white" />
            <rect x="5" y="2.5" width="1.5" height="1.5" fill="white" />
            <rect x="2.5" y="5" width="1.5" height="1.5" fill="white" />
            <rect x="5" y="5" width="1.5" height="1.5" fill="white" />
            <rect x="2.5" y="7.5" width="1.5" height="1.5" fill="white" />
            <rect x="5" y="7.5" width="1.5" height="1.5" fill="white" />
            {/* short building */}
            <rect x="8.5" y="5" width="4.5" height="8" rx="0.3" stroke="white" strokeWidth="1.1" />
            <rect x="9.5" y="6.5" width="1.5" height="1.5" fill="white" />
            <rect x="9.5" y="9" width="1.5" height="1.5" fill="white" />
            {/* ground line */}
            <line x1="0.5" y1="13" x2="13.5" y2="13" stroke="white" strokeWidth="1.1" strokeLinecap="round" />
          </svg>
        </div>
        <span className="text-[9px] font-500 text-white px-1.5 py-0.5 rounded-full whitespace-nowrap" style={{ background: color }}>{label}</span>
      </div>
    </KakaoOverlay>
  )
}

// An inline notice for things the user can fix (conflicting conditions, a backend
// that isn't running). Warm brick rather than alarm red — nothing here is broken,
// the form just needs another pass.
const SORT_TABS: { key: SortBy; label: string; hint: string }[] = [
  { key: 'recommended', label: '추천', hint: '가격·면적·통근을 함께 본 종합 점수' },
  { key: 'commute', label: '통근', hint: '더 오래 걸리는 쪽이 짧은 순' },
  { key: 'balanced', label: '공평', hint: '두 사람 통근시간이 비슷한 순' },
  { key: 'price', label: '가격', hint: '월 부담액이 적은 순' },
  { key: 'area', label: '넓이', hint: '전용면적이 넓은 순' },
]

// 정렬은 백엔드에서 자르기 전에 적용된다. 받아 온 목록을 다시 정렬하면
// "추천 150건 중 싼 것"이 되어 "제일 싼 것"과 다르다.
function SortTabs({ value, onChange, disabled }: {
  value: SortBy; onChange: (v: SortBy) => void; disabled: boolean
}) {
  return (
    <div className="sticky top-0 z-10 flex gap-0.5 border-b border-[#ede9e2] bg-white/95 px-2 py-2 backdrop-blur-sm">
      {SORT_TABS.map(t => (
        <button
          key={t.key}
          type="button"
          title={t.hint}
          disabled={disabled}
          aria-pressed={value === t.key}
          onClick={() => value !== t.key && onChange(t.key)}
          className={`flex-1 rounded-lg py-1.5 text-[12px] transition-colors disabled:opacity-50 ${
            value === t.key
              ? 'bg-[#2d2a24] font-600 text-white'
              : 'text-[#888] hover:bg-[#f5f2ed] hover:text-[#2d2a24]'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="notice-in flex items-start gap-2.5 rounded-2xl border border-[#ecd9d1] bg-[#fdf6f3] px-4 py-3 text-left"
    >
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" className="mt-0.5 flex-shrink-0" aria-hidden="true">
        <circle cx="8" cy="8" r="6.6" stroke="#c08574" strokeWidth="1.2" />
        <path d="M8 4.9v3.6" stroke="#c08574" strokeWidth="1.4" strokeLinecap="round" />
        <circle cx="8" cy="11" r="0.75" fill="#c08574" />
      </svg>
      <p className="text-[13px] leading-relaxed text-[#8a5548]">{children}</p>
    </div>
  )
}

function RangeSlider({ min, max, values, onChange, color }: {
  min: number; max: number; values: number[]; onChange: (v: number[]) => void; color: string
}) {
  const pct = (v: number) => ((v - min) / (max - min)) * 100
  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef<'lo' | 'hi' | null>(null)

  const getVal = (clientX: number) => {
    const rect = trackRef.current!.getBoundingClientRect()
    return Math.round(Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * (max - min) + min)
  }

  const onMouseDown = (thumb: 'lo' | 'hi') => (e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = thumb
    const move = (ev: MouseEvent) => {
      const v = getVal(ev.clientX)
      if (dragging.current === 'lo') onChange([Math.min(v, values[1] - 1), values[1]])
      else onChange([values[0], Math.max(v, values[0] + 1)])
    }
    const up = () => { dragging.current = null; window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  return (
    <div className="relative h-6 flex items-center select-none" ref={trackRef}>
      <div className="absolute left-0 right-0 h-[3px] rounded-full" style={{ background: '#e8e4de' }}>
        <div className="absolute h-full rounded-full" style={{ left: `${pct(values[0])}%`, width: `${pct(values[1]) - pct(values[0])}%`, background: color, opacity: 0.7 }} />
      </div>
      {(['lo', 'hi'] as const).map(thumb => (
        <div
          key={thumb}
          className="absolute w-[18px] h-[18px] rounded-full bg-white shadow-md cursor-grab active:cursor-grabbing z-10"
          style={{ left: `${pct(thumb === 'lo' ? values[0] : values[1])}%`, transform: 'translateX(-50%)', border: `2px solid ${color}` }}
          onMouseDown={onMouseDown(thumb)}
        />
      ))}
    </div>
  )
}

// Floating edit drawer that slides up from bottom on screens 2 & 3
function ConditionsDrawer({ cond, setCond, open, onClose, onPickWork }: {
  cond: Conditions; setCond: (c: Conditions) => void; open: boolean; onClose: () => void
  onPickWork: (key: 'p1Work' | 'p2Work', text: string, coord: LatLng) => void
}) {
  const [local, setLocal] = useState<Conditions>(cond)
  // Coordinates picked from the dropdown while the drawer is open, staged here (like
  // every other field) until "다시 검색" is clicked.
  const [localCoords, setLocalCoords] = useState<Partial<Record<'p1Work' | 'p2Work', LatLng>>>({})

  // Sync local when reopened
  const handleOpen = () => { setLocal(cond); setLocalCoords({}) }

  const confirm = () => {
    setCond(local)
    for (const [key, coord] of Object.entries(localCoords) as [('p1Work' | 'p2Work'), LatLng][]) {
      onPickWork(key, local[key], coord)
    }
    onClose()
  }

  return (
    <>
      {/* Backdrop */}
      {open && <div className="fixed inset-0 z-30 bg-black/20 backdrop-blur-[2px]" onClick={onClose} />}
      {/* Drawer */}
      <div
        className="fixed bottom-0 left-0 right-0 z-40 bg-white rounded-t-2xl shadow-2xl transition-transform duration-300"
        style={{ transform: open ? 'translateY(0)' : 'translateY(100%)', maxHeight: '80vh', overflow: 'auto' }}
        onTransitionEnd={() => { if (open) handleOpen() }}
      >
        <div className="px-5 pt-4 pb-2 flex items-center justify-between border-b border-[#ede9e2]">
          <span className="text-sm font-500 text-[#555]">조건 수정</span>
          <div className="flex gap-2">
            <button
              onClick={confirm}
              className="px-4 py-1.5 bg-[#111] text-white text-xs font-500 rounded-full hover:bg-[#333] transition-colors"
            >
              다시 검색
            </button>
            <button onClick={onClose} className="p-1.5 text-[#aaa] hover:text-[#555] transition-colors">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 p-5">
          {[
            { key: 'p1', label: '사람 1', color: '#16a34a', workKey: 'p1Work' as const, priceKey: 'p1Price' as const, areaKey: 'p1Area' as const },
            { key: 'p2', label: '사람 2', color: '#7c3aed', workKey: 'p2Work' as const, priceKey: 'p2Price' as const, areaKey: 'p2Area' as const },
          ].map(({ label, color, workKey, priceKey, areaKey }) => (
            <div key={label} className="flex flex-col gap-4">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                <span className="text-xs font-500 text-[#888]">{label}</span>
              </div>
              <div>
                <label className="text-xs text-[#aaa] block mb-1.5">직장 위치</label>
                <WorkSearchInput
                  value={local[workKey]}
                  onChange={text => setLocal({ ...local, [workKey]: text })}
                  onPick={(text, coord) => { setLocal({ ...local, [workKey]: text }); setLocalCoords({ ...localCoords, [workKey]: coord }) }}
                  picked={!!localCoords[workKey] || local[workKey] === cond[workKey]}
                />
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#aaa]">월 부담액</label>
                  <span className="text-xs text-[#555]">월 {local[priceKey][0]}만 – {local[priceKey][1]}만</span>
                </div>
                <RangeSlider min={10} max={150} values={local[priceKey]} onChange={v => setLocal({ ...local, [priceKey]: v })} color={color} />
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#aaa]">면적</label>
                  <span className="text-xs text-[#555]">{local[areaKey][0]}평 – {local[areaKey][1]}평</span>
                </div>
                <RangeSlider min={5} max={35} values={local[areaKey]} onChange={v => setLocal({ ...local, [areaKey]: v })} color={color} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

// Screen 1
function InputScreen({ cond, setCond, onSubmit, onPickWork, loading, error, pickedWorks }: {
  cond: Conditions; setCond: (c: Conditions) => void; onSubmit: () => void
  onPickWork: (key: 'p1Work' | 'p2Work', text: string, coord: LatLng) => void
  loading: boolean; error: string | null
  /** 드롭다운에서 직접 고른 직장. 여기 없으면 첫 검색결과로 추측된 값이다. */
  pickedWorks: Record<'p1Work' | 'p2Work', boolean>
}) {
  return (
    <div className="min-h-screen flex flex-col bg-[#faf9f7]">
      <header className="px-8 pt-7 pb-5">
        <div className="flex items-center gap-2">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="#2d2a24" /></svg>
          <span className="text-sm font-500 text-[#2d2a24]">같이살집</span>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 py-8">
        <p className="text-[13px] text-[#aaa] mb-2 tracking-wide">함께 살 곳을 찾아볼게요</p>
        <h1 className="text-3xl font-600 text-[#2d2a24] mb-10 text-center">같이 살래?</h1>

        <div className="w-full max-w-2xl grid grid-cols-2 gap-4">
          {[
            { label: '사람 1', color: '#16a34a', workKey: 'p1Work' as const, priceKey: 'p1Price' as const, areaKey: 'p1Area' as const },
            { label: '사람 2', color: '#7c3aed', workKey: 'p2Work' as const, priceKey: 'p2Price' as const, areaKey: 'p2Area' as const },
          ].map(({ label, color, workKey, priceKey, areaKey }) => (
            <div key={label} className="bg-white rounded-2xl border border-[#ede9e2] p-6 flex flex-col gap-5 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
                <span className="text-xs font-500 text-[#aaa] tracking-wider">{label}</span>
              </div>

              <div>
                <label className="text-xs text-[#bbb] block mb-1.5">직장 위치</label>
                <WorkSearchInput
                  value={cond[workKey]}
                  onChange={text => setCond({ ...cond, [workKey]: text })}
                  onPick={(text, coord) => onPickWork(workKey, text, coord)}
                  picked={pickedWorks[workKey]}
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#bbb]">월 부담액</label>
                  <span className="text-xs text-[#666]">월 {cond[priceKey][0]}만 – {cond[priceKey][1]}만</span>
                </div>
                <RangeSlider min={10} max={150} values={cond[priceKey]} onChange={v => setCond({ ...cond, [priceKey]: v })} color={color} />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#bbb]">면적</label>
                  <span className="text-xs text-[#666]">{cond[areaKey][0]}평 – {cond[areaKey][1]}평</span>
                </div>
                <RangeSlider min={5} max={35} values={cond[areaKey]} onChange={v => setCond({ ...cond, [areaKey]: v })} color={color} />
              </div>
            </div>
          ))}
        </div>

        <button
          onClick={onSubmit}
          disabled={loading}
          className="mt-8 px-10 py-3.5 bg-[#2d2a24] text-white text-base font-500 rounded-full hover:bg-[#444] transition-all shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[#2d2a24]"
        >
          {loading ? '찾는 중…' : <>같이 살자 &nbsp;&nbsp;→</>}
        </button>

        {error && <div className="mt-5 w-full max-w-[440px]"><Notice>{error}</Notice></div>}
      </main>
    </div>
  )
}

// 지도를 줄였을 때(레벨 숫자가 커질 때) 낱개 가격 대신 구 단위로 묶어서 평균가를 보여준다.
// 숫자가 클수록 더 많이 축소해야 묶인다.
const CLUSTER_LEVEL = 7

type Cluster = { gu: string; members: Listing[]; lat: number; lng: number; avgPrice: number }

const groupAvg = (gu: string, members: Listing[]): Cluster => ({
  gu,
  members,
  lat: members.reduce((s, m) => s + m.lat, 0) / members.length,
  lng: members.reduce((s, m) => s + m.lng, 0) / members.length,
  // 개별 마커가 환산월세(shortPrice)를 보여주므로 평균도 같은 축이어야 한다.
  // 월세만 섞어 쓰면 클러스터 "45만"이 확대 시 "월 73만"으로 튄다.
  avgPrice: Math.round(members.reduce((s, m) => s + m.monthlyEquivalent, 0) / members.length),
})

// 구 단위로 묶되, 매물이 1건뿐인 구는 따로 두지 않고 가장 가까운(중심점 기준) 다른
// 그룹에 흡수시킨다 — 화면에 외딴 낱개 원이 하나만 떠 있는 걸 막는다.
function clusterByGu(listings: Listing[]): Cluster[] {
  const byGu = new Map<string, Listing[]>()
  for (const p of listings) {
    const gu = p.neighborhood.split(' ')[0] || p.neighborhood
    if (!byGu.has(gu)) byGu.set(gu, [])
    byGu.get(gu)!.push(p)
  }
  const groups = [...byGu.entries()].map(([gu, members]) => groupAvg(gu, members))
  const multi = groups.filter(g => g.members.length > 1)
  const singles = groups.filter(g => g.members.length === 1)
  if (multi.length === 0) return groups // 전부 낱개뿐이면 합칠 대상이 없다

  const dist2 = (a: Cluster, b: Cluster) => (a.lat - b.lat) ** 2 + (a.lng - b.lng) ** 2
  const merged = new Map(multi.map(g => [g.gu, [...g.members]]))
  for (const single of singles) {
    const nearest = multi.reduce((best, g) => (dist2(single, g) < dist2(single, best) ? g : best), multi[0])
    merged.get(nearest.gu)!.push(single.members[0])
  }
  return [...merged.entries()].map(([gu, members]) => groupAvg(gu, members))
}

function PriceBubble({ p, map, hovered, onSelect, setHovered }: {
  p: Listing; map: any; hovered: number | null; onSelect: (id: number) => void; setHovered: (id: number | null) => void
}) {
  return (
    <KakaoOverlay map={map} lat={p.lat} lng={p.lng} zIndex={hovered === p.id ? 31 : 30}>
      <button onClick={() => onSelect(p.id)} onMouseEnter={() => setHovered(p.id)} onMouseLeave={() => setHovered(null)}>
        <div className={`px-2.5 py-1 text-xs font-600 rounded-full border shadow-sm transition-all whitespace-nowrap ${hovered === p.id ? 'bg-[#2d2a24] text-white border-[#2d2a24] shadow-md' : 'bg-white text-[#2d2a24] border-[#ddd] hover:border-[#999]'}`}>
          {shortPrice(p)}
        </div>
      </button>
    </KakaoOverlay>
  )
}

// Screen 2
function MapScreen({ cond, setCond, onSelect, onHome, workCoords, onPickWork, listings, total, loading, error, sortBy, onSortChange }: {
  cond: Conditions; setCond: (c: Conditions) => void; onSelect: (id: number) => void; onHome: () => void; workCoords: { p1: LatLng; p2: LatLng }
  onPickWork: (key: 'p1Work' | 'p2Work', text: string, coord: LatLng) => void
  listings: Listing[]; total: number; loading: boolean; error: string | null
  sortBy: SortBy; onSortChange: (v: SortBy) => void
}) {
  const [hovered, setHovered] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(CLUSTER_LEVEL)
  const [moving, setMoving] = useState(false)
  // 매물이 아직 없으면 직장 두 곳만으로 지도를 맞춘다.
  const fitPoints = [workCoords.p1, workCoords.p2, ...listings.map(p => ({ lat: p.lat, lng: p.lng }))]
  const clusters = clusterByGu(listings)
  const clustered = zoomLevel >= CLUSTER_LEVEL

  return (
    <div className="h-screen flex flex-col bg-[#faf9f7]">
      <header className="px-5 py-3.5 border-b border-[#ede9e2] bg-white flex items-center justify-between">
        <button onClick={onHome} className="flex items-center gap-2.5 hover:opacity-70 transition-opacity">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="#2d2a24" /></svg>
          <span className="text-sm font-500 text-[#2d2a24]">같이살집</span>
          <span className="text-xs text-[#bbb] ml-1">
            {loading
              ? '불러오는 중…'
              : total > listings.length
                ? `매물 ${listings.length}개 · 조건 충족 ${total.toLocaleString()}개`
                : `매물 ${listings.length}개`}
          </span>
        </button>
        <button
          onClick={() => setDrawerOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[#ede9e2] text-xs text-[#666] hover:border-[#bbb] transition-colors bg-white"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="4" cy="3" r="1.2" stroke="currentColor" strokeWidth="1.1" /><circle cx="8" cy="9" r="1.2" stroke="currentColor" strokeWidth="1.1" /><line x1="4" y1="4.2" x2="4" y2="11" stroke="currentColor" strokeWidth="1.1" /><line x1="4" y1="0" x2="4" y2="1.8" stroke="currentColor" strokeWidth="1.1" /><line x1="8" y1="7.8" x2="8" y2="0" stroke="currentColor" strokeWidth="1.1" /><line x1="8" y1="11" x2="8" y2="10.2" stroke="currentColor" strokeWidth="1.1" /></svg>
          조건 수정
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-[240px] border-r border-[#ede9e2] overflow-y-auto scroll-hide flex-shrink-0 bg-white">
          <SortTabs value={sortBy} onChange={onSortChange} disabled={loading} />
          {error && <div className="p-3"><Notice>{error}</Notice></div>}
          {!error && !loading && listings.length === 0 && (
            <p className="px-4 py-6 text-[13px] leading-relaxed text-[#999]">
              조건에 맞는 매물이 없어요.<br />가격이나 평수 범위를 넓혀보세요.
            </p>
          )}
          {listings.map(p => (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              onMouseEnter={() => setHovered(p.id)}
              onMouseLeave={() => setHovered(null)}
              className={`w-full text-left px-4 py-4 border-b border-[#f0ece6] flex gap-3 transition-colors ${hovered === p.id ? 'bg-[#f7f5f0]' : ''}`}
            >
              <div className="w-9 h-9 rounded-xl bg-[#f0ece6] flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="#aaa" /></svg>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-600 text-[#2d2a24]">{priceLabel(p)}</div>
                <div className="text-[11px] text-[#aaa] mt-0.5 truncate">{termsLabel(p)}</div>
                <div className="text-xs text-[#999] mt-0.5 truncate">{p.neighborhood}</div>
                <div className="text-xs text-[#bbb] mt-0.5">{p.floor}층 · {p.area}평</div>
                <div className="text-[10px] text-[#bbb] mt-1 truncate">
                  통근 {p.commuteMinutes[0]}분 · {p.commuteMinutes[1]}분
                  {p.nearestStation && ` · ${p.nearestStation.name} 도보 ${p.nearestStation.walkMin}분`}
                </div>
              </div>
            </button>
          ))}
        </aside>

        <div className="flex-1 relative">
          <KakaoMap fitPoints={fitPoints} dim>
            {map => (
              <>
                <KakaoZoomWatcher map={map} onChange={setZoomLevel} />
                <MapMotionWatcher map={map} onChange={setMoving} />
                {!moving && <WorkMarker map={map} lat={workCoords.p1.lat} lng={workCoords.p1.lng} color="#16a34a" label={cond.p1Work} />}
                {!moving && <WorkMarker map={map} lat={workCoords.p2.lat} lng={workCoords.p2.lng} color="#7c3aed" label={cond.p2Work} />}
                {!moving && (clustered
                  ? clusters.map(c => c.members.length > 1 ? (
                      <KakaoOverlay key={c.gu} map={map} lat={c.lat} lng={c.lng} zIndex={30}>
                        <button
                          onClick={() => {
                            const kakao = (window as any).kakao
                            const bounds = new kakao.maps.LatLngBounds()
                            c.members.forEach(m => bounds.extend(new kakao.maps.LatLng(m.lat, m.lng)))
                            map.setBounds(bounds, 48)
                            // 클러스터 안 매물끼리 너무 가까우면 setBounds가 과하게 확대해버린다.
                            // 최소한 동네 정도는 보이는 수준으로 붙잡아 준다.
                            if (map.getLevel() < CLUSTER_LEVEL - 3) map.setLevel(CLUSTER_LEVEL - 3)
                          }}
                          className="flex flex-col items-center justify-center rounded-full shadow-md text-[#555] hover:brightness-95 transition-all"
                          style={{
                            width: 64 + Math.min(c.members.length, 12) * 3,
                            height: 64 + Math.min(c.members.length, 12) * 3,
                            background: '#e5e5e5',
                          }}
                        >
                          <div className="text-sm font-700 leading-tight">월 {c.avgPrice}만</div>
                          <div className="text-[10px] text-[#888] leading-tight mt-0.5">{c.gu} · {c.members.length}건</div>
                        </button>
                      </KakaoOverlay>
                    ) : (
                      <PriceBubble key={c.members[0].id} p={c.members[0]} map={map} hovered={hovered} onSelect={onSelect} setHovered={setHovered} />
                    ))
                  : listings.map(p => (
                      <PriceBubble key={p.id} p={p} map={map} hovered={hovered} onSelect={onSelect} setHovered={setHovered} />
                    )))}
              </>
            )}
          </KakaoMap>
        </div>
      </div>

      <ConditionsDrawer cond={cond} setCond={setCond} open={drawerOpen} onClose={() => setDrawerOpen(false)} onPickWork={onPickWork} />
    </div>
  )
}

// Screen 3
function DetailScreen({ listing, cond, setCond, onBack, onHome, workCoords, onPickWork }: {
  listing: Listing; cond: Conditions; setCond: (c: Conditions) => void; onBack: () => void; onHome: () => void; workCoords: { p1: LatLng; p2: LatLng }
  onPickWork: (key: 'p1Work' | 'p2Work', text: string, coord: LatLng) => void
}) {
  const p = listing
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [commute, setCommute] = useState<Commute | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)

  // 경로는 이 화면에 들어올 때만 부른다(명세의 lazy 호출). 목록 단계에서는 시간만 온다.
  useEffect(() => {
    let alive = true
    setCommute(null)
    setRouteError(null)
    fetchCommute(p.id, workCoords.p1, workCoords.p2)
      .then(c => { if (alive) setCommute(c) })
      .catch(e => { if (alive) setRouteError(String(e?.message ?? e)) })
    return () => { alive = false }
  }, [p.id, workCoords.p1.lat, workCoords.p1.lng, workCoords.p2.lat, workCoords.p2.lng])

  // 경로가 오기 전에는 목록에서 받은 통근시간만 보여 준다.
  const legs = [
    { color: '#16a34a', label: cond.p1Work, stops: (commute?.p1.stops ?? []).map(toStop), minutes: commute?.p1.minutes ?? p.commuteMinutes[0], path: commute?.p1.path },
    { color: '#7c3aed', label: cond.p2Work, stops: (commute?.p2.stops ?? []).map(toStop), minutes: commute?.p2.minutes ?? p.commuteMinutes[1], path: commute?.p2.path },
  ]
  const fitPoints = [
    { lat: p.lat, lng: p.lng }, workCoords.p1, workCoords.p2,
    ...legs.flatMap(l => l.stops.map(s => ({ lat: s.lat, lng: s.lng }))),
    // 선로가 정류장 밖으로 휘는 구간까지 화면에 담기도록 폴리라인 양 끝도 넣는다.
    ...legs.flatMap(l => (l.path ?? []).flatMap(seg =>
      seg.points.length ? [seg.points[0], seg.points[seg.points.length - 1]] : []
    ).map(([lat, lng]) => ({ lat, lng }))),
  ]

  return (
    <div className="h-screen flex flex-col bg-[#faf9f7]">
      <header className="px-5 py-3.5 border-b border-[#ede9e2] bg-white flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onHome} className="flex items-center hover:opacity-70 transition-opacity" aria-label="처음으로">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="#2d2a24" /></svg>
          </button>
          <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-[#999] hover:text-[#2d2a24] transition-colors">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            목록
          </button>
          <span className="text-[#ddd]">·</span>
          <span className="text-sm font-500 text-[#2d2a24]">{p.neighborhood}</span>
        </div>
        <button
          onClick={() => setDrawerOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[#ede9e2] text-xs text-[#666] hover:border-[#bbb] transition-colors bg-white"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="4" cy="3" r="1.2" stroke="currentColor" strokeWidth="1.1" /><circle cx="8" cy="9" r="1.2" stroke="currentColor" strokeWidth="1.1" /><line x1="4" y1="4.2" x2="4" y2="11" stroke="currentColor" strokeWidth="1.1" /><line x1="4" y1="0" x2="4" y2="1.8" stroke="currentColor" strokeWidth="1.1" /><line x1="8" y1="7.8" x2="8" y2="0" stroke="currentColor" strokeWidth="1.1" /><line x1="8" y1="11" x2="8" y2="10.2" stroke="currentColor" strokeWidth="1.1" /></svg>
          조건 수정
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-[260px] border-r border-[#ede9e2] overflow-y-auto scroll-hide flex-shrink-0 bg-white flex flex-col">
          <div className="aspect-[4/3] bg-[#ede9e2] flex items-center justify-center border-b border-[#ede9e2]">
            <svg width="44" height="44" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="#ccc" /></svg>
          </div>

          <div className="p-5 flex-1">
            <div className="text-2xl font-600 text-[#2d2a24] mb-0.5">{priceLabel(p)}</div>
            <div className="text-sm text-[#777]">{termsLabel(p)}</div>
            <div className="text-xs text-[#bbb] mt-1 mb-5">
              보증금을 연 5.5%로 환산한 월 부담액입니다{p.buildingName && ` · ${p.buildingName}`}
            </div>

            <div className="grid grid-cols-2 gap-2">
              {[['면적', `${p.area}평`], ['층수', `${p.floor}층`], ['건축년도', `${p.year}년`], ['주소', p.address]].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-[#faf9f7] border border-[#ede9e2] p-3">
                  <div className="text-[10px] text-[#bbb] mb-0.5">{k}</div>
                  <div className="text-sm font-500 text-[#2d2a24]">{v}</div>
                </div>
              ))}
            </div>

            <div className="mt-5 pt-5 border-t border-[#ede9e2] space-y-3.5">
              <div className="text-xs text-[#bbb] mb-1">
                통근 시간
                {!commute && !routeError && <span className="ml-1 text-[#ccc]">경로 불러오는 중…</span>}
                {routeError && <span className="ml-1 text-[#b08276]">경로를 불러오지 못했어요</span>}
              </div>
              {legs.map(({ color, label, stops, minutes }) => (
                <div key={label} className="flex items-start gap-2.5">
                  <span className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ background: color }} />
                  <div className="flex-1">
                    <div className="flex justify-between items-baseline">
                      <span className="text-xs font-500 text-[#444]">{label}</span>
                      <span className="text-xs font-600" style={{ color }}>{minutes}분</span>
                    </div>
                    <div className="text-[10px] text-[#bbb] mt-0.5">{stops.map(s => s.name).join(' → ')}</div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {stops.slice(1).map((s, i) => s.line && (
                        <span key={i} className="text-[8px] font-600 text-white px-1.5 py-0.5 rounded-full" style={{ background: s.color }}>
                          {s.mode === 'bus' ? `🚌 ${s.line}` : s.line}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>

        <div className="flex-1 relative">
          <KakaoMap fitPoints={fitPoints}>
            {map => (
              <>
                {legs.map(l => l.stops.length > 1 && (
                  <TransitRoute key={l.color} map={map} stops={l.stops} personColor={l.color} path={l.path} />
                ))}
                <KakaoOverlay map={map} lat={p.lat} lng={p.lng} zIndex={25}>
                  <div className="w-9 h-9 rounded-full bg-[#2d2a24] flex items-center justify-center shadow-lg">
                    <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="white" /></svg>
                  </div>
                </KakaoOverlay>
                <WorkMarker map={map} lat={workCoords.p1.lat} lng={workCoords.p1.lng} color="#16a34a" label={cond.p1Work} />
                <WorkMarker map={map} lat={workCoords.p2.lat} lng={workCoords.p2.lng} color="#7c3aed" label={cond.p2Work} />
              </>
            )}
          </KakaoMap>
          <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur-sm border border-[#ede9e2] rounded-xl px-3 py-2.5 text-xs space-y-1.5 shadow-sm max-w-[160px] pointer-events-none">
            {[['#16a34a', '사람 1 경로'], ['#7c3aed', '사람 2 경로']].map(([color, label]) => (
              <div key={label} className="flex items-center gap-2">
                <div className="w-5 h-0.5 rounded-full" style={{ background: color, opacity: 0.4 }} />
                <span className="text-[#666]">{label}</span>
              </div>
            ))}
            <div className="border-t border-[#ede9e2] pt-1.5 flex items-center gap-2">
              <svg width="20" height="4" className="flex-shrink-0"><line x1="0" y1="2" x2="20" y2="2" stroke="#999" strokeWidth="3" strokeLinecap="round" /></svg>
              <span className="text-[#666]">지하철</span>
            </div>
            <div className="flex items-center gap-2">
              <svg width="20" height="4" className="flex-shrink-0"><line x1="0" y1="2" x2="20" y2="2" stroke="#999" strokeWidth="2.5" strokeDasharray="2 3" strokeLinecap="round" /></svg>
              <span className="text-[#666]">버스</span>
            </div>
          </div>
        </div>
      </div>

      <ConditionsDrawer cond={cond} setCond={setCond} open={drawerOpen} onClose={() => setDrawerOpen(false)} onPickWork={onPickWork} />
    </div>
  )
}

// Fallback coordinates for the default work locations, used until Kakao's geocoder
// resolves the current input (or if it ever fails to find a match).
const DEFAULT_P1_COORD: LatLng = { lat: 37.4975555, lng: 127.0268078 } // 강남역
const DEFAULT_P2_COORD: LatLng = { lat: 37.5567647, lng: 126.9237401 } // 홍대입구역

export default function App() {
  const [screen, setScreen] = useState<1 | 2 | 3>(1)
  const [selected, setSelected] = useState<number | null>(null)
  const [cond, setCond] = useState<Conditions>({
    p1Work: '강남역', p2Work: '홍대입구역',
    // 서울 연립다세대는 중앙값 11평 · 90퍼센타일 19평이다. 기본값을 데이터에 맞춘다.
    p1Price: [30, 70], p2Price: [40, 80],
    p1Area: [7, 18], p2Area: [8, 20],
  })
  const [listings, setListings] = useState<Listing[]>([])
  const [total, setTotal] = useState(0)
  const [sortBy, setSortBy] = useState<SortBy>('recommended')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [workCoords, setWorkCoords] = useState<{ p1: LatLng; p2: LatLng }>({ p1: DEFAULT_P1_COORD, p2: DEFAULT_P2_COORD })
  const kakaoReady = useKakaoReady()
  // Remembers the last text that was resolved via an explicit dropdown pick (with its
  // exact coordinate), so the debounced fallback geocoder below doesn't immediately
  // re-search and possibly jump the marker to a different, less precise match.
  const lastPicked = useRef<{ p1Work?: { text: string; coord: LatLng }; p2Work?: { text: string; coord: LatLng } }>({})

  const [pickedWorks, setPickedWorks] = useState<Record<'p1Work' | 'p2Work', boolean>>({ p1Work: true, p2Work: true })

  const handlePickWork = (key: 'p1Work' | 'p2Work', text: string, coord: LatLng) => {
    lastPicked.current = { ...lastPicked.current, [key]: { text, coord } }
    setPickedWorks(w => ({ ...w, [key]: true }))
    setCond(c => ({ ...c, [key]: text }))
    setWorkCoords(w => ({ ...w, [key === 'p1Work' ? 'p1' : 'p2']: coord }))
  }

  // Re-geocode whenever either work-location text changes (debounced so we don't
  // fire a request on every keystroke), unless that exact text was just set by an
  // explicit dropdown pick above.
  useEffect(() => {
    if (!kakaoReady) return
    const t = setTimeout(async () => {
      const needP1 = lastPicked.current.p1Work?.text !== cond.p1Work
      const needP2 = lastPicked.current.p2Work?.text !== cond.p2Work
      if (!needP1 && !needP2) return
      const [p1, p2] = await Promise.all([
        needP1 ? geocodeKeyword(cond.p1Work) : Promise.resolve(lastPicked.current.p1Work!.coord),
        needP2 ? geocodeKeyword(cond.p2Work) : Promise.resolve(lastPicked.current.p2Work!.coord),
      ])
      setWorkCoords({ p1: p1 ?? DEFAULT_P1_COORD, p2: p2 ?? DEFAULT_P2_COORD })
    }, 400)
    return () => clearTimeout(t)
  }, [kakaoReady, cond.p1Work, cond.p2Work])

  /** 직장 좌표 + 조건으로 매물을 검색한다. 직장 텍스트는 이미 카카오 SDK가 좌표로 바꿔 놨다. */
  const runSearch = async (c: Conditions, w: { p1: LatLng; p2: LatLng }, sort: SortBy = sortBy): Promise<boolean> => {
    setLoading(true)
    setError(null)
    try {
      const r = await searchListings(
        { workLat: w.p1.lat, workLng: w.p1.lng, priceMin: c.p1Price[0], priceMax: c.p1Price[1], areaMin: c.p1Area[0], areaMax: c.p1Area[1] },
        { workLat: w.p2.lat, workLng: w.p2.lng, priceMin: c.p2Price[0], priceMax: c.p2Price[1], areaMin: c.p2Area[0], areaMax: c.p2Area[1] },
        { p1Name: c.p1Work, p2Name: c.p2Work },
        sort,
      )
      setListings(r.listings)
      setTotal(r.total)
      return true
    } catch (e: any) {
      setError(String(e?.message ?? e))
      setListings([])
      setTotal(0)
      return false
    } finally {
      setLoading(false)
    }
  }

  // 조건 서랍에서 값을 바꾸면 재검색한다(1번 화면에서는 "같이 살자"를 눌러야 검색).
  const updateCond = (c: Conditions) => {
    setCond(c)
    setError(null)                       // 조건을 고치는 중이면 이전 오류는 치운다
    if (screen !== 1) void runSearch(c, workCoords)
  }

  // 정렬은 백엔드에서 자르기 전에 적용되므로 재요청해야 한다.
  const changeSort = (v: SortBy) => {
    setSortBy(v)
    void runSearch(cond, workCoords, v)
  }

  const goHome = () => setScreen(1)
  const selectedListing = listings.find(l => l.id === selected) ?? null

  if (screen === 1) {
    // 조건이 모순이면(평수 범위가 안 겹치는 등) 2번 화면으로 넘기지 않고 여기서 알린다.
    const submit = async () => {
      if (await runSearch(cond, workCoords)) setScreen(2)
    }
    // 직장 텍스트를 직접 고치면 "확정" 표시를 푼다. 드롭다운에서 다시 골라야 확정된다.
    const setCondFromInput = (c: Conditions) => {
      setPickedWorks(w => ({
        p1Work: c.p1Work === cond.p1Work ? w.p1Work : false,
        p2Work: c.p2Work === cond.p2Work ? w.p2Work : false,
      }))
      updateCond(c)
    }
    return (
      <InputScreen
        cond={cond} setCond={setCondFromInput} onSubmit={() => void submit()} onPickWork={handlePickWork}
        loading={loading} error={error} pickedWorks={pickedWorks}
      />
    )
  }
  if (screen === 2 || !selectedListing) {
    return (
      <MapScreen
        cond={cond} setCond={updateCond} onSelect={id => { setSelected(id); setScreen(3) }} onHome={goHome}
        workCoords={workCoords} onPickWork={handlePickWork}
        listings={listings} total={total} loading={loading} error={error}
        sortBy={sortBy} onSortChange={changeSort}
      />
    )
  }
  return (
    <DetailScreen
      listing={selectedListing} cond={cond} setCond={updateCond} onBack={() => setScreen(2)} onHome={goHome}
      workCoords={workCoords} onPickWork={handlePickWork}
    />
  )
}
