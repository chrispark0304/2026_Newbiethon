export interface Preference {
  name: string;
  destination: string;
  maxBudget: number;
  maxCommute: number;
  priorities: { commute: number; price: number; roomSize: number; station: number; sunlight: number };
  lifestyle: {
    sleepTime: 'early' | 'normal' | 'late';
    cleaningFrequency: number;
    guestFrequency: number;
    temperaturePreference: 'cool' | 'normal' | 'warm';
    foodSharing: boolean;
    sharedSupplies: boolean;
  };
}
export interface MatchRequest { userA: Preference; userB: Preference }
export interface MatchResult {
  listing: {
    id: number; name: string; address: string; rent: number; deposit: number; stationDistance: number;
    rooms: { id: string; area: number; sunlight: number; hasWindow: boolean; hasStorage: boolean }[];
  };
  scores: { userA: number; userB: number; average: number; fairnessPenalty: number; final: number };
  commute: { userA: number; userB: number };
  rentSplit: { roomA: number; roomB: number };
  reasons: string[];
}
export interface MatchResponse {
  results: MatchResult[];
  compatibility: { score: number; warnings: string[] };
}
