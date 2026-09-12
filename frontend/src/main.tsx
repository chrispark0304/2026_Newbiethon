import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { getHouseMatches } from './api/houseApi';
import { demoResponse } from './demo';
import type { MatchRequest, MatchResponse, MatchResult, Preference } from './types';
import './styles.css';

const initial = (name: string, destination: string, maxBudget: number, maxCommute: number): Preference => ({
  name, destination, maxBudget, maxCommute,
  priorities: { commute: 3, price: 3, roomSize: 3, station: 3, sunlight: 3 },
  lifestyle: { sleepTime: 'normal', cleaningFrequency: 3, guestFrequency: 1, temperaturePreference: 'normal', foodSharing: false, sharedSupplies: true },
});
const labels = { commute: '통학·출퇴근', price: '가격', roomSize: '방 크기', station: '역 접근성', sunlight: '채광' };
const money = (value: number) => `${value.toLocaleString('ko-KR')}원`;

function PreferenceFields({ value, onChange }: { value: Preference; onChange: (value: Preference) => void }) {
  return <>
    <div className="fields">
      <label>이름<input required maxLength={30} value={value.name} onChange={e => onChange({ ...value, name: e.target.value })} /></label>
      <label>목적지<input required maxLength={100} placeholder="예: 고려대학교" value={value.destination} onChange={e => onChange({ ...value, destination: e.target.value })} /></label>
      <label>최대 월 부담금 (원)<input type="number" required min={1} step={1} value={value.maxBudget || ''} onChange={e => onChange({ ...value, maxBudget: Number(e.target.value) })} /></label>
      <label>최대 이동시간 (분)<input type="number" required min={1} step={1} value={value.maxCommute || ''} onChange={e => onChange({ ...value, maxCommute: Number(e.target.value) })} /></label>
    </div>
    <h3>어떤 조건이 중요한가요?</h3><p className="muted">1은 덜 중요, 5는 매우 중요해요.</p>
    {Object.entries(labels).map(([key, label]) => <label className="slider" key={key}>{label}
      <input type="range" min={1} max={5} value={value.priorities[key as keyof typeof labels]} onChange={e => onChange({ ...value, priorities: { ...value.priorities, [key]: Number(e.target.value) } })} />
      <output>{value.priorities[key as keyof typeof labels]}</output>
    </label>)}
  </>;
}

function LifestyleFields({ value, onChange }: { value: Preference; onChange: (value: Preference) => void }) {
  const life = value.lifestyle;
  const update = (patch: Partial<Preference['lifestyle']>) => onChange({ ...value, lifestyle: { ...life, ...patch } });
  return <fieldset><legend>{value.name}의 생활패턴</legend><div className="fields">
    <label>취침 시간<select value={life.sleepTime} onChange={e => update({ sleepTime: e.target.value as typeof life.sleepTime })}><option value="early">일찍 자는 편</option><option value="normal">보통</option><option value="late">늦게 자는 편</option></select></label>
    <label>냉난방 선호<select value={life.temperaturePreference} onChange={e => update({ temperaturePreference: e.target.value as typeof life.temperaturePreference })}><option value="cool">시원하게</option><option value="normal">보통</option><option value="warm">따뜻하게</option></select></label>
    <label>청소 빈도 (1 낮음 ~ 5 높음)<select value={life.cleaningFrequency} onChange={e => update({ cleaningFrequency: Number(e.target.value) })}>{[1,2,3,4,5].map(n => <option key={n}>{n}</option>)}</select></label>
    <label>친구 초대 빈도 (1 낮음 ~ 5 높음)<select value={life.guestFrequency} onChange={e => update({ guestFrequency: Number(e.target.value) })}>{[1,2,3,4,5].map(n => <option key={n}>{n}</option>)}</select></label>
    <label className="check"><input type="checkbox" checked={life.foodSharing} onChange={e => update({ foodSharing: e.target.checked })} />음식 공유하기</label>
    <label className="check"><input type="checkbox" checked={life.sharedSupplies} onChange={e => update({ sharedSupplies: e.target.checked })} />공용 생필품 함께 쓰기</label>
  </div></fieldset>;
}

function App() {
  const [step, setStep] = useState(0);
  const [request, setRequest] = useState<MatchRequest>({ userA: initial('민수', '고려대학교', 600000, 30), userB: initial('지수', '강남역', 700000, 45) });
  const [result, setResult] = useState<MatchResponse | null>(null);
  const [selected, setSelected] = useState<MatchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [demo, setDemo] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => { heading.current?.focus(); }, [step, result, selected]);
  useEffect(() => () => controller.current?.abort(), []);
  const update = (key: keyof MatchRequest, value: Preference) => setRequest(previous => ({ ...previous, [key]: value }));
  async function submit() {
    if (loading) return;
    setLoading(true); setError(''); setDemo(false);
    const abort = new AbortController(); controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 20000);
    try { setResult(await getHouseMatches(request, abort.signal)); }
    catch (cause) { setError(abort.signal.aborted ? '응답 시간이 길어지고 있어요. 다시 시도해 주세요.' : cause instanceof TypeError ? '서버에 연결하지 못했어요. 백엔드 실행 상태를 확인해 주세요.' : cause instanceof Error ? cause.message : '요청에 실패했어요. 다시 시도해 주세요.'); }
    finally { window.clearTimeout(timeout); setLoading(false); }
  }
  const title = selected ? selected.listing.name : result ? (demo ? '추천 결과 예시' : '두 사람을 위한 추천') : ['함께 납득할 수 있는 집.', '첫 번째 사람의 조건', '두 번째 사람의 조건', '함께 살기 전, 생활패턴'][step];
  return <div className="app">
    <header><a href="./">같이살집<span>두 사람을 위한 집 찾기</span></a><span className="tag">MVP</span></header>
    <main>
      <p className="eyebrow">{result ? 'OUR NEXT HOME' : 'A HOME FOR BOTH OF US'}</p>
      <h1 ref={heading} tabIndex={-1}>{title}</h1>
      {demo && <p className="notice">데모 · 가이드의 고정 예시 1건입니다. 입력 조건에 따른 실제 추천이 아닙니다.</p>}
      {selected ? <>
        <p className="muted">{selected.listing.address}</p>
        <section className="panel"><h2>집 정보</h2><dl><div><dt>월세</dt><dd>{money(selected.listing.rent)}</dd></div><div><dt>보증금</dt><dd>{money(selected.listing.deposit)}</dd></div><div><dt>역까지</dt><dd>{selected.listing.stationDistance}분</dd></div></dl>
          <h3>방별 월세 분담</h3><p className="muted">방 배정은 두 사람이 함께 결정해 주세요.</p>
          <div className="fields">{selected.listing.rooms.map(room => <article className="room" key={room.id}><h3>{room.id === 'roomA' ? '방 A' : room.id === 'roomB' ? '방 B' : room.id}</h3><strong>{room.id === 'roomA' ? money(selected.rentSplit.roomA) : room.id === 'roomB' ? money(selected.rentSplit.roomB) : '분담 정보 없음'}</strong><p>{room.area}㎡ · 채광 {room.sunlight}/5</p><p>창문 {room.hasWindow ? '있음' : '없음'} · 수납 {room.hasStorage ? '있음' : '없음'}</p></article>)}</div>
          <h3>공동 적합도 {selected.scores.final}점</h3><p>평균 만족도 {selected.scores.average}점 · 공평성 패널티 {selected.scores.fairnessPenalty}점</p>
          <ul>{selected.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
        </section><button onClick={() => setSelected(null)}>추천 목록으로</button>
      </> : result ? <>
        <p className="muted">한 사람의 희생을 줄이고, 둘의 만족을 함께 살펴보세요.</p>
        <div className="results">{result.results.length === 0 && <p className="panel">추천 가능한 매물이 없어요. 조건을 바꾸어 다시 시도해 주세요.</p>}{result.results.map((item, index) => <article className="panel" key={item.listing.id}>
          <span className="tag">추천 {index + 1}</span><h2>{item.listing.name}</h2><p className="muted">{item.listing.address}</p>
          <div className="score">{item.scores.final}<small>점 · 공동 적합도</small></div>
          <dl><div><dt>{demo ? '민수' : request.userA.name} 만족도 / 이동</dt><dd>{item.scores.userA}점 / {item.commute.userA}분</dd></div><div><dt>{demo ? '지수' : request.userB.name} 만족도 / 이동</dt><dd>{item.scores.userB}점 / {item.commute.userB}분</dd></div><div><dt>월세</dt><dd>{money(item.listing.rent)}</dd></div></dl>
          <ul>{item.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul><button onClick={() => setSelected(item)}>상세·월세 분담 보기</button>
        </article>)}</div>
        <section className="panel"><h2>생활 궁합 <span className="accent">{result.compatibility.score}점</span></h2><p>사전에 합의하면 좋은 부분</p>{result.compatibility.warnings.length ? <ul>{result.compatibility.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul> : <p className="muted">서버에서 전달한 주의사항이 없어요.</p>}</section>
        <button className="secondary" onClick={() => { setResult(null); setDemo(false); setStep(1); }}>조건 다시 입력하기</button>
      </> : step === 0 ? <>
        <p className="intro">각자의 예산과 이동시간, 생활 습관까지.<br />두 사람 모두에게 좋은 선택을 찾아보세요.</p>
        <div className="features"><article><b>01</b><h3>각자의 조건</h3><p>예산과 중요 조건을 입력해요.</p></article><article><b>02</b><h3>둘의 균형</h3><p>각자의 만족도를 함께 봐요.</p></article><article><b>03</b><h3>함께 정할 생활</h3><p>방별 월세와 생활 궁합을 확인해요.</p></article></div>
        <div className="actions"><button onClick={() => setStep(1)}>우리에게 맞는 집 찾기</button><button className="secondary" onClick={() => { setDemo(true); setResult(demoResponse); }}>예시 결과 보기</button></div>
      </> : <>
        <nav aria-label="입력 단계" className="steps">{['A 조건', 'B 조건', '생활패턴'].map((label, i) => <span key={label} aria-current={step === i + 1 ? 'step' : undefined} className={step === i + 1 ? 'active' : ''}>{i + 1}. {label}</span>)}</nav>
        <form className="panel" aria-busy={loading} onSubmit={e => { e.preventDefault(); if (step < 3) { const value = step === 1 ? request.userA : request.userB; if (!value.name.trim() || !value.destination.trim()) { setError('이름과 목적지는 공백 없이 입력해 주세요.'); return; } setError(''); setStep(step + 1); } else void submit(); }}>
          <fieldset disabled={loading} className="form-body">
            {step < 3 ? <PreferenceFields value={step === 1 ? request.userA : request.userB} onChange={value => update(step === 1 ? 'userA' : 'userB', value)} /> : <>{(['userA', 'userB'] as const).map(key => <LifestyleFields key={key} value={request[key]} onChange={value => update(key, value)} />)}</>}
            {error && <p role="alert" className="error">{error}</p>}
            <div className="actions"><button type="button" className="secondary" onClick={() => { setError(''); setStep(step - 1); }}>이전</button><button type="submit">{loading ? '집을 찾는 중…' : step < 3 ? '다음' : '추천받기'}</button></div>
          </fieldset>
          {loading && <p role="status">두 사람에게 맞는 집을 찾고 있어요…</p>}
        </form>
      </>}
    </main><footer>같이살집 · 두 사람이 함께 납득할 수 있는 선택</footer>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
