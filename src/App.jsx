import { useState, useEffect } from 'react';
import { 
  MountainSnow, 
  AlertTriangle, 
  Clock, 
  ExternalLink, 
  Calendar,
  Search,
  RefreshCw,
  Info
} from 'lucide-react';

const formatDateIT = (isoDate) => {
  if (!isoDate) return '';
  const parts = isoDate.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return isoDate;
};

const MONTHS_IT = [
  'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
  'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'
];

// Normalizzatore stringhe: rimuove trattini strani, accenti e spazi multipli
const norm = (str) => (str || '')
  .toLowerCase()
  .replace(/[\u2010-\u2015\u2212]/g, '-')
  .replace(/\s+/g, ' ');

// Risoluzione deterministica della fonte ufficiale: nessun URL generato dal modello,
// solo una mappa corridoio + parole chiave verso il portale del gestore competente.
const getCorridorOfficialSource = (corridorKey, corridorData) => {
  if (!corridorData) return null;
  const hasContent = Boolean(
    corridorData.title ||
    corridorData.details ||
    corridorData.micro_stops ||
    corridorData.status === 'BLOCCO_TOTALE'
  );
  if (!hasContent) return null;

  const text = norm(`${corridorData.title} ${corridorData.details}`);

  if (corridorKey === 'frejus') {
    if (text.includes('aprr')) {
      return { name: 'APRR', url: 'https://www.aprr.fr/' };
    }
    if (text.includes('a32') || text.includes('sitaf') || text.includes('susa') || text.includes('oulx') || text.includes('bussoleno')) {
      return { name: 'SITAF', url: 'https://www.sitaf.it/' };
    }
    return { name: 'SFTRF', url: 'https://www.sftrf.fr/it/autoroute/travaux-et-fermetures/' };
  }

  if (corridorKey === 'monte_bianco') {
    if (text.includes('a40') || text.includes('atmb') || text.includes('vuache') || text.includes('egratz') || text.includes('chavants')) {
      return { name: 'ATMB', url: 'https://www.atmb.com/' };
    }
    if (/\brav/.test(text)) {
      return { name: 'RAV S.p.A.', url: 'https://www.ravspa.it/' };
    }
    if (text.includes('a5') || text.includes('sav') || text.includes('arnad')) {
      return { name: 'SAV A5', url: 'https://www.sav-a5.it/' };
    }
    return { name: 'TMB-GEIE', url: 'https://www.tunnelmb.net/it-IT/interruzioni-e-previsioni' };
  }

  return null;
};

// Rilevatore intelligente di chiusure notturne (es. 21:00 - 06:00)
const detectNightClosure = (corridorObj) => {
  if (!corridorObj || corridorObj.status !== 'BLOCCO_TOTALE') return null;
  const text = norm(`${corridorObj.title} ${corridorObj.details}`);

  // Cerca pattern orari tipo "21:00-06:00", "22:00 - 06:00", "21.00-06.00"
  const match = text.match(/(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})/);
  if (match) {
    const startH = parseInt(match[1], 10) + parseInt(match[2], 10) / 60;
    const endH = parseInt(match[3], 10) + parseInt(match[4], 10) / 60;
    // Se inizia la sera (>= 19:00) e finisce al mattino (<= 08:00)
    if (startH >= 19 && endH <= 8) {
      return { startH, endH };
    }
  }

  // Fallback su parole chiave notturne
  if (text.includes('notturn') || text.includes('nuit')) {
    const startH = (text.includes('21:00') || text.includes('21h')) ? 21 : 22;
    return { startH, endH: 6 };
  }

  return null;
};

// Calcolo deterministico delle fasce orarie 00-24
const getDaySegments = (day, prevDay, corridorKey) => {
  const cur = day[corridorKey] || {};
  const prev = prevDay ? prevDay[corridorKey] : null;

  const curText = norm(`${cur.title} ${cur.details}`);
  const prevNight = detectNightClosure(prev);
  const curNight = detectNightClosure(cur);

  // 1. Il mattino (00:00 - 06:00) è chiuso se:
  // - La notte prima aveva una chiusura notturna
  // - O il testo di oggi dice espressamente "chiuso fino alle 06:00" o "riapertura ore 06:00"
  let morningClosedUntil = 0;
  if (prevNight) {
    morningClosedUntil = prevNight.endH;
  } else if (curText.includes('fino alle 06:00') || curText.includes('riapertura ore 06:00') || curText.includes('riapertura dalle ore 06:00')) {
    morningClosedUntil = 6;
  }

  // 2. Blocchi durante la giornata
  let dayBlocks = [];
  if (cur.status === 'BLOCCO_TOTALE') {
    if (curNight) {
      // Blocco serale che inizia oggi (es. dalle 21:00 o 22:00 a mezzanotte)
      dayBlocks.push({ start: curNight.startH, end: 24 });
    } else {
      // Cerca blocchi diurni specifici (es. Charmaix 03:30 - 12:30)
      const match = curText.match(/(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})/);
      if (match) {
        const startH = parseInt(match[1], 10) + parseInt(match[2], 10) / 60;
        const endH = parseInt(match[3], 10) + parseInt(match[4], 10) / 60;
        dayBlocks.push({ start: startH, end: endH });
      } else if (!curText.includes('riapertura')) {
        // Se è un blocco totale dell'intera giornata
        dayBlocks.push({ start: morningClosedUntil, end: 24 });
      }
    }
  }

  // 3. Costruzione dei segmenti 00-24
  let segments = [];
  let currentHour = 0;

  if (morningClosedUntil > 0) {
    segments.push({ start: 0, end: morningClosedUntil, type: 'closed' });
    currentHour = morningClosedUntil;
  }

  dayBlocks.forEach(b => {
    if (b.start > currentHour) {
      segments.push({ start: currentHour, end: b.start, type: 'open' });
    }
    segments.push({ start: b.start, end: b.end, type: 'closed' });
    currentHour = Math.max(currentHour, b.end);
  });

  if (currentHour < 24) {
    segments.push({ start: currentHour, end: 24, type: 'open' });
  }

  return segments;
};

// Estrae TUTTE le micro-chiusure da testo libero (es. "04:30 - 05:15", "22:30-23:15")
const parseMicroStops = (rawText) => {
  const found = [];
  const re = /(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})/g;
  let match;
  while ((match = re.exec(rawText)) !== null) {
    const startH = parseInt(match[1], 10) + parseInt(match[2], 10) / 60;
    const endH = parseInt(match[3], 10) + parseInt(match[4], 10) / 60;
    if (endH > startH) {
      found.push({ startH, endH, label: match[0] });
    }
  }
  return found;
};

// Badge di stato: management by exception — si segnala solo il blocco totale.
const StatusBadge = ({ status }) => {
  if (status !== 'BLOCCO_TOTALE') return null;
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200 shrink-0">
      <span className="w-2 h-2 rounded-full bg-rose-600 animate-pulse"></span>
      BLOCCO TOTALE
    </span>
  );
};

// Contenuto di una cella corridoio, condiviso tra tabella desktop e card mobile:
// - BLOCCO_TOTALE: badge rosso + titolo in grassetto + dettagli + micro-stop.
// - Eventi senza blocco: nessun badge, testo uniforme in peso regolare + micro-stop.
// - Giornata regolare o priva di eventi: cella completamente vuota.
const CorridorContent = ({ corridor, corridorKey }) => {
  if (!corridor) return null;

  const isBlock = corridor.status === 'BLOCCO_TOTALE';
  const title = (corridor.title || '').trim();
  const details = (corridor.details || '').trim();
  const microStops = (corridor.micro_stops || '').trim();
  const source = getCorridorOfficialSource(corridorKey, corridor);

  if (!isBlock) {
    if (corridor.status === 'REGOLARE') return null;
    if (!title && !details && !microStops) return null;
    return (
      <>
        {title && (
          <p className="font-normal text-slate-700 leading-relaxed text-xs">{title}</p>
        )}
        {details && (
          <p className="font-normal text-slate-700 leading-relaxed text-xs">{details}</p>
        )}
        {microStops && (
          <div className="text-[11px] font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded inline-block mt-1">
            ⏱️ {microStops}
          </div>
        )}
        {source && (
          <div className="mt-1.5 flex items-center">
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 hover:text-blue-600 transition-colors"
              title={`Apri portale ufficiale ${source.name}`}
            >
              <span>{source.name}</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <div className="flex items-center gap-2 mb-1">
        <StatusBadge status={corridor.status} />
        {title && <span className="font-bold text-slate-900">{title}</span>}
      </div>
      {details && <p className="text-slate-600 leading-relaxed mb-1">{details}</p>}
      {microStops && (
        <div className="text-[11px] font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded inline-block mt-0.5">
          ⏱️ {microStops}
        </div>
      )}
      {source && (
        <div className="mt-1.5 flex items-center">
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 hover:text-blue-600 transition-colors"
            title={`Apri portale ufficiale ${source.name}`}
          >
            <span>{source.name}</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      )}
    </>
  );
};

// COMPONENTE: Nastro Orario Continuo (Timeline Ribbon)
const TimelineRibbon = ({ day, prevDay, corridorKey }) => {
  const corridorData = day[corridorKey];
  const microStops = norm(corridorData?.micro_stops);
  const microStopRanges = parseMicroStops(microStops);
  const segments = getDaySegments(day, prevDay, corridorKey);

  return (
    <div className="relative w-11 sm:w-12 self-stretch border-r border-slate-200 bg-emerald-200 shrink-0 select-none overflow-hidden">
      {/* Fasce orarie (Verde / Rosso) */}
      {segments.map((seg, idx) => {
        const topPct = (seg.start / 24) * 100;
        const heightPct = ((seg.end - seg.start) / 24) * 100;
        const bgColor = seg.type === 'closed' ? 'bg-rose-300' : 'bg-emerald-200';
        return (
          <div
            key={idx}
            className={`absolute w-full ${bgColor}`}
            style={{ top: `${topPct}%`, height: `${heightPct}%` }}
          />
        );
      })}

      {/* Micro-chiusure tecniche: una barra per ogni fascia oraria rilevata */}
      {microStopRanges.map((stop, idx) => {
        const topPct = (stop.startH / 24) * 100;
        const heightPct = Math.max(((stop.endH - stop.startH) / 24) * 100, 2.5);
        return (
          <div
            key={`micro-${idx}`}
            className="absolute w-full min-h-[4px] bg-amber-300 z-10"
            style={{ top: `${topPct}%`, height: `${heightPct}%` }}
            title={stop.label || 'Stop tecnico'}
          />
        );
      })}

      {/* Tacche orarie centrate verticalmente sulla linea, con etichetta nel varco */}
      {[
        { pct: 25, label: '06h' },
        { pct: 50, label: '12h' },
        { pct: 75, label: '18h' },
      ].map(({ pct, label }) => (
        <div
          key={label}
          className="absolute left-0 right-0 flex items-center pointer-events-none -translate-y-1/2 px-1"
          style={{ top: `${pct}%` }}
        >
          <div className="flex-1 border-t border-slate-500/25" />
          <span className="text-[8.5px] font-semibold text-slate-600/80 pl-1 leading-none select-none">
            {label}
          </span>
        </div>
      ))}
    </div>
  );
};

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterAxis, setFilterAxis] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetch('./traffic_data.json')
      .then((res) => {
        if (!res.ok) throw new Error('Dati non trovati');
        return res.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Errore caricamento dati:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-white font-sans">
        <RefreshCw className="w-10 h-10 animate-spin text-blue-500 mb-4" />
        <p className="text-lg font-semibold tracking-wide">Caricamento Control Tower...</p>
      </div>
    );
  }

  if (!data || !data.days) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-white p-6 font-sans">
        <AlertTriangle className="w-12 h-12 text-amber-500 mb-4" />
        <h2 className="text-xl font-bold mb-2">Dati non disponibili</h2>
        <p className="text-slate-400 text-center max-w-md">
          Esegui <code className="text-blue-400 bg-slate-800 px-2 py-1 rounded">python fetch_traffic.py</code> per raccogliere i dati.
        </p>
      </div>
    );
  }

  const filteredDays = data.days.filter((day) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.trim().toLowerCase();
    const termWithSlash = term.replace(/[.\- ]/g, '/');
    // 1. Corridor text match (con guardie difensive sui dati generati dal modello)
    const frejusText = `${day.frejus?.title || ''} ${day.frejus?.details || ''} ${day.frejus?.micro_stops || ''}`.toLowerCase();
    const mbText = `${day.monte_bianco?.title || ''} ${day.monte_bianco?.details || ''} ${day.monte_bianco?.micro_stops || ''}`.toLowerCase();
    const matchCorridor = frejusText.includes(term) || mbText.includes(term);
    // 2. Corrispondenza data in formato ISO, italiano (21/10/2026) e naturale (21 ottobre)
    const dateIT = formatDateIT(day.date);
    const dateITWithSlash = dateIT.replace(/[.\- ]/g, '/');
    const parts = (day.date || '').split('-');
    let naturalDateIT = '';
    if (parts.length === 3) {
      const dayNum = parseInt(parts[2], 10);
      const monthIdx = parseInt(parts[1], 10) - 1;
      const monthName = MONTHS_IT[monthIdx] || '';
      naturalDateIT = `${dayNum} ${monthName}`;
    }
    const dateSearchTarget = `${day.date || ''} ${dateIT} ${dateITWithSlash} ${naturalDateIT} ${day.day_name || ''}`.toLowerCase();
    const matchDate = dateSearchTarget.includes(term) || dateSearchTarget.includes(termWithSlash);
    return matchCorridor || matchDate;
  });

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 font-sans pb-16">
      {/* HEADER */}
      <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30 shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-600/90 rounded-lg text-white shadow flex items-center justify-center">
              <MountainSnow className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-extrabold tracking-tight">
                TUNNELS CONTROL TOWER
              </h1>
              <div className="flex items-center gap-1.5 flex-wrap">
                <p className="text-xs text-slate-400 font-medium">
                  Monitoraggio Valichi Transalpini &bull; Focus Veicoli Pesanti 44t (escluso ADR e convogli eccezionali)
                </p>
                <div className="relative inline-flex items-center group">
                  <button
                    type="button"
                    aria-label="Informazioni sulla fonte dei dati"
                    className="text-slate-400 hover:text-slate-200 focus:outline-none focus:text-blue-400 transition-colors"
                  >
                    <Info className="w-3.5 h-3.5" />
                  </button>
                  {/* Tooltip a comparsa */}
                  <div className="absolute left-1/2 -translate-x-1/2 top-full mt-2 hidden group-hover:block group-focus-within:block w-72 p-2.5 bg-slate-800 text-slate-200 text-[11px] leading-relaxed rounded-lg shadow-xl border border-slate-700 z-50 pointer-events-none">
                    Le informazioni sono ricercate e sintetizzate automaticamente tramite intelligenza artificiale da fonti web ufficiali. Possono verificarsi imprecisioni od omissioni: verificare sempre sui canali ufficiali.
                    {/* Triangolino freccia superiore */}
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 border-4 border-transparent border-b-slate-700" />
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs bg-slate-800 px-3 py-2 rounded-lg border border-slate-700 self-start sm:self-auto">
            <Clock className="w-4 h-4 text-blue-400" />
            <span className="text-slate-300">Aggiornato:</span>
            <span className="font-bold text-white">{data.last_updated}</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 pt-6">
        {/* BARRA FILTRI */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm mb-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-1.5 w-full md:w-auto overflow-x-auto pb-1 md:pb-0">
            <button
              onClick={() => setFilterAxis('ALL')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                filterAxis === 'ALL'
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Tutti i Valichi
            </button>
            <button
              onClick={() => setFilterAxis('FREJUS')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                filterAxis === 'FREJUS'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Solo Fréjus (A43)
            </button>
            <button
              onClick={() => setFilterAxis('MONTE_BIANCO')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                filterAxis === 'MONTE_BIANCO'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Solo Monte Bianco (A40)
            </button>
          </div>

          <div className="relative w-full md:w-72">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Cerca Orelle, Charmaix, 21/10, ottobre..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
            />
          </div>
        </div>

        {/* 1. VISTA DESKTOP (TABELLA ROLLING CONTINUA) */}
        <div className="hidden md:block bg-white rounded-xl border border-slate-200 shadow-sm overflow-visible">
          <table className="w-full text-left border-collapse table-fixed">
            <thead>
              <tr className="bg-slate-900 text-white text-xs uppercase tracking-wider font-bold border-b border-slate-300">
                <th className="sticky top-[72px] z-20 bg-slate-900 shadow-sm py-3 px-4 w-44 rounded-tl-xl border-b border-slate-300">Data / Giorno</th>
                {(filterAxis === 'ALL' || filterAxis === 'FREJUS') && (
                  <th className={`sticky top-[72px] z-20 bg-slate-900 shadow-sm py-3 px-4 border-l border-slate-800 border-b border-slate-300 ${filterAxis === 'ALL' ? 'w-[calc((100%-11rem)/2)]' : ''} ${filterAxis === 'FREJUS' ? 'rounded-tr-xl' : ''}`}>
                    <div className="flex items-center gap-2.5">
                      <div className="w-14 h-7.5 bg-white p-1 rounded-md shadow-xs shrink-0 flex items-center justify-center">
                        <img
                          src="./logos/sftrf.png"
                          alt="SFTRF"
                          className="max-h-full max-w-full object-contain"
                        />
                      </div>
                      <span className="text-white text-xs uppercase tracking-wider font-bold">
                        Asse Fréjus (A43 &bull; T4 &bull; A32)
                      </span>
                    </div>
                  </th>
                )}
                {(filterAxis === 'ALL' || filterAxis === 'MONTE_BIANCO') && (
                  <th className={`sticky top-[72px] z-20 bg-slate-900 shadow-sm py-3 px-4 border-l border-slate-800 border-b border-slate-300 rounded-tr-xl ${filterAxis === 'ALL' ? 'w-[calc((100%-11rem)/2)]' : ''}`}>
                    <div className="flex items-center gap-2.5">
                      <div className="w-14 h-7.5 bg-white p-1 rounded-md shadow-xs shrink-0 flex items-center justify-center">
                        <img
                          src="./logos/tmb.png"
                          alt="TMB-GEIE"
                          className="max-h-full max-w-full object-contain"
                        />
                      </div>
                      <span className="text-white text-xs uppercase tracking-wider font-bold">
                        Asse Monte Bianco (A40 &bull; TMB &bull; A5)
                      </span>
                    </div>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-300 text-xs font-medium">
              {filteredDays.map((day, idx) => {
                const isToday = day.is_today;
                const prevDay = idx > 0 ? filteredDays[idx - 1] : null;

                return (
                  <tr 
                    key={day.date} 
                    className={`hover:bg-slate-50/50 transition-colors ${
                      isToday ? 'bg-blue-50/40 border-l-4 border-l-blue-600' : ''
                    }`}
                  >
                    {/* COLONNA DATA */}
                    <td className="py-3.5 px-4 align-top">
                      <div className="flex items-center gap-2">
                        {isToday && (
                          <span className="px-1.5 py-0.5 text-[10px] font-extrabold uppercase bg-blue-600 text-white rounded">
                            Oggi
                          </span>
                        )}
                        <span className="font-bold text-slate-900 text-sm">{day.day_name}</span>
                      </div>
                      <div className="text-slate-500 mt-0.5 font-medium">{formatDateIT(day.date)}</div>
                    </td>

                    {/* COLONNA FREJUS */}
                    {(filterAxis === 'ALL' || filterAxis === 'FREJUS') && (
                      <td className="p-0 h-px border-l border-slate-100 align-top">
                        <div className="flex h-full min-h-[110px] items-stretch">
                          <TimelineRibbon day={day} prevDay={prevDay} corridorKey="frejus" />
                          <div className="p-3.5 flex-1 min-w-0">
                            <CorridorContent corridor={day.frejus} corridorKey="frejus" />
                          </div>
                        </div>
                      </td>
                    )}

                    {/* COLONNA MONTE BIANCO */}
                    {(filterAxis === 'ALL' || filterAxis === 'MONTE_BIANCO') && (
                      <td className="p-0 h-px border-l border-slate-100 align-top">
                        <div className="flex h-full min-h-[110px] items-stretch">
                          <TimelineRibbon day={day} prevDay={prevDay} corridorKey="monte_bianco" />
                          <div className="p-3.5 flex-1 min-w-0">
                            <CorridorContent corridor={day.monte_bianco} corridorKey="monte_bianco" />
                          </div>
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* 2. VISTA MOBILE */}
        <div className="md:hidden space-y-3">
          {filteredDays.map((day, idx) => {
            const isToday = day.is_today;
            const prevDay = idx > 0 ? filteredDays[idx - 1] : null;

            return (
              <div 
                key={day.date}
                className={`bg-white rounded-xl border shadow-sm p-4 ${
                  isToday ? 'border-blue-500 ring-1 ring-blue-500' : 'border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-slate-400" />
                    <span className="font-bold text-slate-900 text-sm">
                      {day.day_name} {formatDateIT(day.date)}
                    </span>
                  </div>
                  {isToday && (
                    <span className="px-2 py-0.5 text-[10px] font-extrabold uppercase bg-blue-600 text-white rounded">
                      Oggi
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  {/* Fréjus Mobile */}
                  {(filterAxis === 'ALL' || filterAxis === 'FREJUS') && (
                    <div className="rounded-lg bg-slate-50 border border-slate-200 overflow-hidden flex items-stretch min-h-[90px]">
                      <TimelineRibbon day={day} prevDay={prevDay} corridorKey="frejus" />
                      <div className="p-3 flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <div className="w-12 h-6 bg-white p-0.5 rounded border border-slate-200/90 shadow-2xs shrink-0 flex items-center justify-center">
                            <img
                              src="./logos/sftrf.png"
                              alt="SFTRF"
                              className="max-h-full max-w-full object-contain"
                            />
                          </div>
                          <span className="text-[11px] font-extrabold uppercase tracking-wide text-slate-700">
                            Asse Fréjus
                          </span>
                        </div>
                        <CorridorContent corridor={day.frejus} corridorKey="frejus" />
                      </div>
                    </div>
                  )}

                  {/* Monte Bianco Mobile */}
                  {(filterAxis === 'ALL' || filterAxis === 'MONTE_BIANCO') && (
                    <div className="rounded-lg bg-slate-50 border border-slate-200 overflow-hidden flex items-stretch min-h-[90px]">
                      <TimelineRibbon day={day} prevDay={prevDay} corridorKey="monte_bianco" />
                      <div className="p-3 flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <div className="w-12 h-6 bg-white p-0.5 rounded border border-slate-200/90 shadow-2xs shrink-0 flex items-center justify-center">
                            <img
                              src="./logos/tmb.png"
                              alt="TMB-GEIE"
                              className="max-h-full max-w-full object-contain"
                            />
                          </div>
                          <span className="text-[11px] font-extrabold uppercase tracking-wide text-slate-700">
                            Asse Monte Bianco
                          </span>
                        </div>
                        <CorridorContent corridor={day.monte_bianco} corridorKey="monte_bianco" />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* FOOTER */}
        <div className="mt-8 pt-6 border-t border-slate-200 text-xs text-slate-500">
          <p className="font-bold uppercase tracking-wider mb-2 text-slate-600">Fonti Ufficiali Monitorate:</p>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            <a href="https://www.sftrf.fr" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              SFTRF (Fréjus/A43) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.sitaf.it" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              SITAF (T4/A32) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.aprr.fr" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              APRR (A43) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.tunnelmb.net/it-IT/interruzioni-e-previsioni" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              TMB-GEIE (Monte Bianco) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.atmb.com" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              ATMB (A40/RN205) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.ravspa.it" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              RAV S.p.A. (A5 Aosta-TMB) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.sav-a5.it" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              SAV S.p.A. (A5 Quincinetto-Aosta) <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.cciss.it" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              CCISS Viaggiare Informati <ExternalLink className="w-3 h-3" />
            </a>
            <a href="https://www.bison-fute.gouv.fr" target="_blank" rel="noreferrer" className="hover:text-blue-600 flex items-center gap-1">
              Bison Futé <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}