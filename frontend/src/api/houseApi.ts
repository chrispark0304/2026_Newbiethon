import type { MatchRequest, MatchResponse } from '../types';

export async function getHouseMatches(payload: MatchRequest, signal?: AbortSignal): Promise<MatchResponse> {
  const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
  const response = await fetch(`${base}/api/match`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal,
  });
  if (!response.ok) {
    throw new Error(response.status === 400 || response.status === 422
      ? '입력 조건을 서버에서 확인하지 못했어요. 입력값을 확인해 주세요.'
      : '추천 결과를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
  }
  const data: MatchResponse = await response.json();
  if (!Array.isArray(data.results) || !data.compatibility || !Array.isArray(data.compatibility.warnings)) {
    throw new Error('서버 응답 형식을 확인해 주세요.');
  }
  return data;
}
