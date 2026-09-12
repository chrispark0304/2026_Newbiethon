// 백엔드 연동 클라이언트.
// 명세: BACKEND_INTEGRATION.md / 구현 현황: BACKEND_STATUS.md

const BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export type Geo = { name: string; lat: number; lng: number }

export type Listing = {
  id: number
  price: number // 만원/월 (전세는 0)
  deposit: number // 만원
  neighborhood: string
  address: string
  floor: number
  area: number // 평
  year: number
  lat: number
  lng: number
  // 명세 밖 부가 필드
  leaseType: '전세' | '월세'
  monthlyEquivalent: number // 환산월세(만원)
  buildingName: string
  nearestStation: { name: string; lines: string[]; walkMin: number } | null
  commuteMinutes: [number, number]
  jointScore: number
}

export type ApiStop = {
  name: string
  lat: number
  lng: number
  mode?: 'subway' | 'bus'
  line?: string
}

export type CommuteLeg = {
  minutes: number
  stops: ApiStop[]
  path: [number, number][][] // 구간별 폴리라인 [[lat, lng], …]
  source: 'kakao' | 'engine'
  transfers: number | null
  fare: number | null
}

export type Commute = { p1: CommuteLeg; p2: CommuteLeg }

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

/** 자유 텍스트("강남역") → 좌표 */
export function geocode(query: string): Promise<Geo> {
  return json(`${BASE}/api/geocode?query=${encodeURIComponent(query)}`)
}

export type PersonQuery = {
  workLat: number
  workLng: number
  priceMin: number
  priceMax: number
  areaMin: number
  areaMax: number
}

export function searchListings(p1: PersonQuery, p2: PersonQuery, limit = 150): Promise<Listing[]> {
  return json(`${BASE}/api/listings/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ p1, p2, limit }),
  })
}

export function fetchCommute(
  id: number,
  p1: { lat: number; lng: number },
  p2: { lat: number; lng: number },
): Promise<Commute> {
  const q = new URLSearchParams({
    p1WorkLat: String(p1.lat),
    p1WorkLng: String(p1.lng),
    p2WorkLat: String(p2.lat),
    p2WorkLng: String(p2.lng),
  })
  return json(`${BASE}/api/listings/${id}/commute?${q}`)
}

// ---------------------------------------------------------------- 좌표 투영
//
// 화면은 아직 실제 지도 SDK가 아니라 0~100 %좌표에 마커를 찍는다.
// 백엔드는 위경도를 주므로 여기서 한 번 변환한다.
// 지도 SDK를 붙이면 이 블록만 지우고 lat/lng을 그대로 넘기면 된다.

/** 서울 범위 (남, 서, 북, 동). 여유를 조금 둬서 가장자리 마커가 잘리지 않게 한다. */
const BOUNDS = { s: 37.42, w: 126.78, n: 37.70, e: 127.18 }

export function toXY(lat: number, lng: number): { x: number; y: number } {
  const x = ((lng - BOUNDS.w) / (BOUNDS.e - BOUNDS.w)) * 100
  const y = ((BOUNDS.n - lat) / (BOUNDS.n - BOUNDS.s)) * 100 // 위도는 위가 크므로 뒤집는다
  return { x: clamp(x), y: clamp(y) }
}

const clamp = (v: number) => Math.max(2, Math.min(98, v))
