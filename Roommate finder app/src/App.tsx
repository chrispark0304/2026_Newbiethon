import { useState, useRef } from 'react'

const PROPERTIES = [
  { id: 1, price: 51, neighborhood: '마포구 합정동', address: '합정로 45', floor: 3, area: 24, year: 2018, deposit: 500, x: 38, y: 42 },
  { id: 2, price: 63, neighborhood: '은평구 녹번동', address: '녹번로 12', floor: 5, area: 30, year: 2021, deposit: 1000, x: 28, y: 28 },
  { id: 3, price: 45, neighborhood: '서대문구 홍제동', address: '홍제천로 88', floor: 2, area: 20, year: 2015, deposit: 300, x: 22, y: 38 },
  { id: 4, price: 72, neighborhood: '용산구 효창동', address: '효창원로 6', floor: 7, area: 34, year: 2020, deposit: 1000, x: 50, y: 58 },
  { id: 5, price: 58, neighborhood: '마포구 망원동', address: '망원로 33', floor: 4, area: 27, year: 2017, deposit: 500, x: 34, y: 52 },
]

// Real-world Seoul subway line colors, used so route lines read like an actual transit map
const LINE_COLORS: Record<string, string> = {
  '2호선': '#00A84D',
  '3호선': '#EF7C1C',
  '4호선': '#00A5DE',
  '5호선': '#996CAC',
  '6호선': '#CD7C2F',
  '9호선': '#BDB092',
  '경의중앙선': '#77C4A3',
}
const BUS_COLOR = '#2563eb'

// One stop along a person's commute. `mode`/`line`/`color` describe the leg *arriving* at this stop
// (the first stop in a route has none, since there's no leg before it).
type Stop = { name: string; x: number; y: number; mode?: 'subway' | 'bus'; line?: string; color?: string }

const subwayLeg = (name: string, x: number, y: number, line: string): Stop => ({ name, x, y, mode: 'subway', line, color: LINE_COLORS[line] })
const busLeg = (name: string, x: number, y: number, line: string): Stop => ({ name, x, y, mode: 'bus', line, color: BUS_COLOR })

const ROUTES: { p1: Stop[]; p2: Stop[]; p1_time: number; p2_time: number }[] = [
  {
    p1: [{ name: '합정', x: 38, y: 42 }, subwayLeg('당산', 44, 49, '2호선'), subwayLeg('여의도', 50, 53, '9호선'), busLeg('강남', 58, 56, '740')],
    p2: [{ name: '합정', x: 38, y: 42 }, subwayLeg('홍대입구', 30, 36, '2호선'), subwayLeg('신촌', 22, 30, '경의중앙선')],
    p1_time: 28, p2_time: 12,
  },
  {
    p1: [{ name: '녹번', x: 28, y: 28 }, subwayLeg('불광', 38, 38, '6호선'), subwayLeg('여의도', 48, 47, '5호선'), busLeg('강남', 58, 56, '472')],
    p2: [{ name: '녹번', x: 28, y: 28 }, subwayLeg('연신내', 24, 32, '3호선'), subwayLeg('홍대입구', 22, 30, '6호선')],
    p1_time: 35, p2_time: 22,
  },
  {
    p1: [{ name: '홍제', x: 22, y: 38 }, subwayLeg('무악재', 30, 43, '3호선'), subwayLeg('충정로', 44, 50, '5호선'), busLeg('강남', 58, 56, '361')],
    p2: [{ name: '홍제', x: 22, y: 38 }, busLeg('홍대입구', 22, 30, '7737')],
    p1_time: 32, p2_time: 8,
  },
  {
    p1: [{ name: '효창공원앞', x: 50, y: 58 }, subwayLeg('삼각지', 54, 57, '6호선'), busLeg('강남', 58, 56, '143')],
    p2: [{ name: '효창공원앞', x: 50, y: 58 }, subwayLeg('공덕', 36, 44, '6호선'), subwayLeg('홍대입구', 22, 30, '2호선')],
    p1_time: 18, p2_time: 20,
  },
  {
    p1: [{ name: '망원', x: 34, y: 52 }, subwayLeg('합정', 40, 53, '6호선'), subwayLeg('당산', 48, 54, '2호선'), busLeg('강남', 58, 56, '472')],
    p2: [{ name: '망원', x: 34, y: 52 }, subwayLeg('합정', 28, 40, '6호선'), subwayLeg('홍대입구', 22, 30, '2호선')],
    p1_time: 24, p2_time: 10,
  },
]

// Shared condition state lifted to App so it persists across screens
type Conditions = {
  p1Work: string; p2Work: string
  p1Price: number[]; p2Price: number[]
  p1Area: number[]; p2Area: number[]
}

function MapBackground() {
  return (
    <svg className="absolute inset-0 w-full h-full" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f5f4f0" />
      {[15, 30, 45, 60, 75].map(v => (
        <g key={v}>
          <line x1={`${v}%`} y1="0" x2={`${v}%`} y2="100%" stroke="#e6e4de" strokeWidth="1" />
          <line x1="0" y1={`${v}%`} x2="100%" y2={`${v}%`} stroke="#e6e4de" strokeWidth="1" />
        </g>
      ))}
      <path d="M 0 42% Q 25% 44% 50% 40% T 100% 38%" stroke="#d8d5cc" strokeWidth="2" fill="none" />
      <path d="M 20% 0 Q 22% 30% 26% 50% T 30% 100%" stroke="#d8d5cc" strokeWidth="2" fill="none" />
      <path d="M 0 65% Q 35% 60% 60% 58% T 100% 55%" stroke="#d8d5cc" strokeWidth="1.5" fill="none" />
      <path d="M 45% 0 Q 48% 35% 50% 60% T 55% 100%" stroke="#d8d5cc" strokeWidth="1.5" fill="none" />
    </svg>
  )
}

// Renders a commute as real transit lines: each leg is colored/styled by its actual
// subway line or bus route, with a thin person-colored halo underneath so it's still
// clear whose commute is whose.
function TransitRoute({ stops, personColor }: { stops: Stop[]; personColor: string }) {
  if (stops.length < 2) return null
  return (
    <>
      {stops.slice(1).map((to, i) => {
        const from = stops[i]
        const d = `M ${from.x}% ${from.y}% L ${to.x}% ${to.y}%`
        const isBus = to.mode === 'bus'
        return (
          <g key={i}>
            <path d={d} stroke={personColor} strokeWidth="7" strokeOpacity="0.22" fill="none" strokeLinecap="round" />
            <path
              d={d}
              stroke={to.color}
              strokeWidth={isBus ? 3 : 4}
              fill="none"
              strokeLinecap="round"
              strokeDasharray={isBus ? '2 5' : undefined}
            />
          </g>
        )
      })}
      {stops.map((s, i) => (
        <circle key={i} cx={`${s.x}%`} cy={`${s.y}%`} r={i === 0 || i === stops.length - 1 ? 5 : 3.5} fill="white" stroke={s.color ?? personColor} strokeWidth="2" />
      ))}
    </>
  )
}

// Small pill labels (e.g. "2호선", "740") placed at each leg's midpoint, HTML overlay
// (not SVG) so the text stays crisp and horizontally readable.
function TransitLegBadges({ stops }: { stops: Stop[] }) {
  return (
    <>
      {stops.slice(1).map((to, i) => {
        if (!to.line) return null
        const from = stops[i]
        const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2
        return (
          <div
            key={i}
            className="absolute z-20 text-[9px] font-600 text-white px-1.5 py-0.5 rounded-full shadow-sm whitespace-nowrap"
            style={{ left: `${mx}%`, top: `${my}%`, transform: 'translate(-50%, -50%)', background: to.color }}
          >
            {to.mode === 'bus' ? `🚌 ${to.line}` : to.line}
          </div>
        )
      })}
    </>
  )
}

function WorkMarker({ x, y, color, label }: { x: number; y: number; color: string; label: string }) {
  return (
    <div className="absolute z-20 flex flex-col items-center gap-1" style={{ left: `${x}%`, top: `${y}%`, transform: 'translate(-50%, -50%)' }}>
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
      <span className="text-[9px] font-500 text-white px-1.5 py-0.5 rounded-full" style={{ background: color }}>{label}</span>
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
function ConditionsDrawer({ cond, setCond, open, onClose }: {
  cond: Conditions; setCond: (c: Conditions) => void; open: boolean; onClose: () => void
}) {
  const [local, setLocal] = useState<Conditions>(cond)

  // Sync local when reopened
  const handleOpen = () => setLocal(cond)

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
              onClick={() => { setCond(local); onClose() }}
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
                <div className="flex items-center gap-2 border border-[#ede9e2] rounded-xl px-3 py-2 bg-[#faf9f7]">
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="6" r="3" stroke="#aaa" strokeWidth="1.2" /><path d="M7 12s4-3.5 4-6a4 4 0 1 0-8 0c0 2.5 4 6 4 6z" stroke="#aaa" strokeWidth="1.2" fill="none" /></svg>
                  <input type="text" value={local[workKey]} onChange={e => setLocal({ ...local, [workKey]: e.target.value })} className="flex-1 text-sm outline-none bg-transparent text-[#333]" />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#aaa]">월세</label>
                  <span className="text-xs text-[#555]">{local[priceKey][0]}만 – {local[priceKey][1]}만</span>
                </div>
                <RangeSlider min={10} max={150} values={local[priceKey]} onChange={v => setLocal({ ...local, [priceKey]: v })} color={color} />
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#aaa]">면적</label>
                  <span className="text-xs text-[#555]">{local[areaKey][0]}평 – {local[areaKey][1]}평</span>
                </div>
                <RangeSlider min={5} max={60} values={local[areaKey]} onChange={v => setLocal({ ...local, [areaKey]: v })} color={color} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

// Screen 1
function InputScreen({ cond, setCond, onSubmit }: { cond: Conditions; setCond: (c: Conditions) => void; onSubmit: () => void }) {
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
                <div className="flex items-center gap-2 border border-[#ede9e2] rounded-xl px-3 py-2.5 bg-[#faf9f7]">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="6" r="3" stroke="#bbb" strokeWidth="1.2" /><path d="M7 12s4-3.5 4-6a4 4 0 1 0-8 0c0 2.5 4 6 4 6z" stroke="#bbb" strokeWidth="1.2" fill="none" /></svg>
                  <input
                    type="text"
                    value={cond[workKey]}
                    onChange={e => setCond({ ...cond, [workKey]: e.target.value })}
                    className="flex-1 text-sm outline-none bg-transparent text-[#333] placeholder-[#ccc]"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#bbb]">월세</label>
                  <span className="text-xs text-[#666]">{cond[priceKey][0]}만 – {cond[priceKey][1]}만</span>
                </div>
                <RangeSlider min={10} max={150} values={cond[priceKey]} onChange={v => setCond({ ...cond, [priceKey]: v })} color={color} />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-xs text-[#bbb]">면적</label>
                  <span className="text-xs text-[#666]">{cond[areaKey][0]}평 – {cond[areaKey][1]}평</span>
                </div>
                <RangeSlider min={5} max={60} values={cond[areaKey]} onChange={v => setCond({ ...cond, [areaKey]: v })} color={color} />
              </div>
            </div>
          ))}
        </div>

        <button
          onClick={onSubmit}
          className="mt-8 px-10 py-3.5 bg-[#2d2a24] text-white text-base font-500 rounded-full hover:bg-[#444] transition-all shadow-md hover:shadow-lg"
        >
          같이 살자 &nbsp;&nbsp;→
        </button>
      </main>
    </div>
  )
}

// Screen 2
function MapScreen({ cond, setCond, onSelect, onHome }: { cond: Conditions; setCond: (c: Conditions) => void; onSelect: (id: number) => void; onHome: () => void }) {
  const [hovered, setHovered] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <div className="h-screen flex flex-col bg-[#faf9f7]">
      <header className="px-5 py-3.5 border-b border-[#ede9e2] bg-white flex items-center justify-between">
        <button onClick={onHome} className="flex items-center gap-2.5 hover:opacity-70 transition-opacity">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="#2d2a24" /></svg>
          <span className="text-sm font-500 text-[#2d2a24]">같이살집</span>
          <span className="text-xs text-[#bbb] ml-1">매물 {PROPERTIES.length}개</span>
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
          {PROPERTIES.map(p => (
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
                <div className="text-sm font-600 text-[#2d2a24]">{p.price}만원<span className="font-400 text-[#bbb] text-xs">/월</span></div>
                <div className="text-xs text-[#999] mt-0.5 truncate">{p.neighborhood}</div>
                <div className="text-xs text-[#bbb] mt-0.5">{p.floor}층 · {p.area}평</div>
              </div>
            </button>
          ))}
        </aside>

        <div className="flex-1 relative">
          <MapBackground />
          <WorkMarker x={58} y={56} color="#16a34a" label={cond.p1Work} />
          <WorkMarker x={22} y={30} color="#7c3aed" label={cond.p2Work} />
          {PROPERTIES.map(p => (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              onMouseEnter={() => setHovered(p.id)}
              onMouseLeave={() => setHovered(null)}
              className="absolute z-30"
              style={{ left: `${p.x}%`, top: `${p.y}%`, transform: 'translate(-50%, -50%)' }}
            >
              <div className={`px-2.5 py-1 text-xs font-600 rounded-full border shadow-sm transition-all ${hovered === p.id ? 'bg-[#2d2a24] text-white border-[#2d2a24] shadow-md' : 'bg-white text-[#2d2a24] border-[#ddd] hover:border-[#999]'}`}>
                {p.price}만
              </div>
            </button>
          ))}
        </div>
      </div>

      <ConditionsDrawer cond={cond} setCond={setCond} open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  )
}

// Screen 3
function DetailScreen({ propertyId, cond, setCond, onBack, onHome }: { propertyId: number; cond: Conditions; setCond: (c: Conditions) => void; onBack: () => void; onHome: () => void }) {
  const p = PROPERTIES.find(x => x.id === propertyId)!
  const route = ROUTES[propertyId - 1]
  const [drawerOpen, setDrawerOpen] = useState(false)

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
            <div className="text-2xl font-600 text-[#2d2a24] mb-0.5">{p.price}만원<span className="text-sm font-400 text-[#bbb]">/월</span></div>
            <div className="text-xs text-[#bbb] mb-5">보증금 {p.deposit}만원</div>

            <div className="grid grid-cols-2 gap-2">
              {[['면적', `${p.area}평`], ['층수', `${p.floor}층`], ['건축년도', `${p.year}년`], ['주소', p.address]].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-[#faf9f7] border border-[#ede9e2] p-3">
                  <div className="text-[10px] text-[#bbb] mb-0.5">{k}</div>
                  <div className="text-sm font-500 text-[#2d2a24]">{v}</div>
                </div>
              ))}
            </div>

            <div className="mt-5 pt-5 border-t border-[#ede9e2] space-y-3.5">
              <div className="text-xs text-[#bbb] mb-1">통근 시간</div>
              {[
                { color: '#16a34a', label: cond.p1Work, stops: route.p1, minutes: route.p1_time },
                { color: '#7c3aed', label: cond.p2Work, stops: route.p2, minutes: route.p2_time },
              ].map(({ color, label, stops, minutes }) => (
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
          <MapBackground />
          <svg className="absolute inset-0 w-full h-full pointer-events-none">
            <TransitRoute stops={route.p1} personColor="#16a34a" />
            <TransitRoute stops={route.p2} personColor="#7c3aed" />
          </svg>
          <TransitLegBadges stops={route.p1} />
          <TransitLegBadges stops={route.p2} />
          <div className="absolute z-20" style={{ left: `${p.x}%`, top: `${p.y}%`, transform: 'translate(-50%, -50%)' }}>
            <div className="w-9 h-9 rounded-full bg-[#2d2a24] flex items-center justify-center shadow-lg">
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><path d="M10 2L3 8v10h5v-5h4v5h5V8L10 2z" fill="white" /></svg>
            </div>
          </div>
          <WorkMarker x={58} y={56} color="#16a34a" label={cond.p1Work} />
          <WorkMarker x={22} y={30} color="#7c3aed" label={cond.p2Work} />
          <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur-sm border border-[#ede9e2] rounded-xl px-3 py-2.5 text-xs space-y-1.5 shadow-sm max-w-[160px]">
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

      <ConditionsDrawer cond={cond} setCond={setCond} open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  )
}

export default function App() {
  const [screen, setScreen] = useState<1 | 2 | 3>(1)
  const [selected, setSelected] = useState(1)
  const [cond, setCond] = useState<Conditions>({
    p1Work: '강남역', p2Work: '홍대입구역',
    p1Price: [30, 70], p2Price: [40, 80],
    p1Area: [15, 35], p2Area: [20, 40],
  })

  const handleSelect = (id: number) => { setSelected(id); setScreen(3) }
  const goHome = () => setScreen(1)

  if (screen === 1) return <InputScreen cond={cond} setCond={setCond} onSubmit={() => setScreen(2)} />
  if (screen === 2) return <MapScreen cond={cond} setCond={setCond} onSelect={handleSelect} onHome={goHome} />
  return <DetailScreen propertyId={selected} cond={cond} setCond={setCond} onBack={() => setScreen(2)} onHome={goHome} />
}
