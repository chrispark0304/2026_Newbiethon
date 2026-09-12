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
  // 사람별 환승 횟수. "환승 적은 순" 정렬용 — 목록 정렬 버튼에서 쓴다.
  // 백엔드를 재시작하기 전에는 없을 수 있어서 optional로 둔다.
  transfers?: [number, number]
  jointScore: number
}

export type ApiStop = {
  name: string
  lat: number
  lng: number
  mode?: 'subway' | 'bus'
  line?: string
}

/** 실제 선로 좌표. 정류장을 직선으로 이으면 지하철이 강을 가로지르는 것처럼 그려진다. */
export type PathSegment = {
  mode: 'subway' | 'bus' | 'walk'
  line: string | null
  points: [number, number][] // [lat, lng]
}

export type CommuteLeg = {
  minutes: number
  stops: ApiStop[]
  path: PathSegment[]
  source: 'kakao' | 'engine'
  transfers: number | null
  fare: number | null
}

export type Commute = { p1: CommuteLeg; p2: CommuteLeg }

/** 백엔드 오류에 붙는 코드. 화면에서 분기할 일이 있으면 이걸 본다. */
export type ApiErrorCode = 'AREA_RANGE_DISJOINT' | 'PRICE_RANGE_INVALID' | 'WORK_NO_STATION'

export class ApiError extends Error {
  code?: ApiErrorCode
  status: number

  constructor(message: string, status: number, code?: ApiErrorCode) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/**
 * FastAPI는 오류를 `{ detail: ... }`로 싼다. detail이 문자열일 때도 있고
 * `{ code, message }` 객체일 때도 있어서(조건 모순 등) 양쪽을 다 받는다.
 * 객체를 그냥 문자열로 만들면 화면에 "[object Object]"가 찍힌다.
 */
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    // 네트워크 자체가 안 닿는 경우 — 보통 백엔드가 안 떠 있다.
    throw new ApiError('서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.', 0)
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    if (detail && typeof detail === 'object') {
      throw new ApiError(detail.message ?? `${res.status} ${res.statusText}`, res.status, detail.code)
    }
    throw new ApiError(
      typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`,
      res.status,
    )
  }
  return res.json()
}

/** json()과 같지만 응답 헤더도 함께 돌려준다. */
async function jsonWithHeaders<T>(url: string, init?: RequestInit): Promise<{ data: T; headers: Headers }> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    throw new ApiError('서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.', 0)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    if (detail && typeof detail === 'object') {
      throw new ApiError(detail.message ?? `${res.status} ${res.statusText}`, res.status, detail.code)
    }
    throw new ApiError(
      typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`,
      res.status,
    )
  }
  return { data: await res.json(), headers: res.headers }
}

/** 자유 텍스트("강남역") → 좌표 */
export function geocode(query: string): Promise<Geo> {
  return json(`${BASE}/api/geocode?query=${encodeURIComponent(query)}`)
}

export type PersonQuery = {
  workLat: number
  workLng: number
  depositMin: number
  depositMax: number
  priceMin: number
  priceMax: number
  areaMin: number
  areaMax: number
}

/** 목록 정렬 기준. 백엔드에서 자르기 전에 적용되므로 재요청이 필요하다. */
export type SortBy = 'recommended' | 'balanced' | 'price' | 'commute' | 'area'

export type SearchResult = {
  listings: Listing[]
  /** 조건에 맞는 전체 개수. listings는 limit만큼만 잘린 앞부분이다. */
  total: number
}

export async function searchListings(
  p1: PersonQuery,
  p2: PersonQuery,
  /** 오류 문구에 쓸 직장 표시명. "'판교' 주변에 지하철역이 없어요" 처럼 쓰인다. */
  names?: { p1Name: string; p2Name: string },
  sortBy: SortBy = 'recommended',
  limit = 50,
): Promise<SearchResult> {
  const { data, headers } = await jsonWithHeaders<Listing[]>(`${BASE}/api/listings/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ p1, p2, limit, sortBy, ...names }),
  })
  const total = Number(headers.get('X-Total-Matched'))
  return { listings: data, total: Number.isFinite(total) && total > 0 ? total : data.length }
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
