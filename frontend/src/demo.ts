import type { MatchResponse } from './types';

// Fixed UI fixture, not a recommendation algorithm. Never substitutes for a failed API call.
export const demoResponse: MatchResponse = {
  results: [{
    listing: {
      id: 3, name: '성북 A하우스', address: '서울특별시 성북구', rent: 1100000,
      deposit: 20000000, stationDistance: 5,
      rooms: [
        { id: 'roomA', area: 10.2, sunlight: 5, hasWindow: true, hasStorage: true },
        { id: 'roomB', area: 7.8, sunlight: 3, hasWindow: true, hasStorage: false },
      ],
    },
    scores: { userA: 92, userB: 86, average: 89, fairnessPenalty: 1.5, final: 87.5 },
    commute: { userA: 19, userB: 38 }, rentSplit: { roomA: 610000, roomB: 490000 },
    reasons: ['두 사람 모두 이동시간 조건을 만족합니다.', '두 사람의 만족도 차이가 작은 매물입니다.'],
  }],
  compatibility: { score: 78, warnings: ['친구 초대 빈도', '냉난방 선호'] },
};
