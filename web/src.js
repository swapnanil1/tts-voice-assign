import { PipecatClient } from '@pipecat-ai/client-js';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';

const byId = (id) => document.getElementById(id);

function element(tag, className, text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

const dateDisplay = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', weekday: 'short', timeZone: 'UTC' });
const displayDate = (date) => dateDisplay.format(new Date(`${date}T00:00:00Z`));
const displayTime = (time) => new Intl.DateTimeFormat('en-IN', {
  hour: 'numeric', minute: '2-digit', timeZone: 'UTC', hour12: true,
}).format(new Date(`2000-01-01T${time}:00Z`));

function renderSchedule({ doctors, slots, appointments }) {
  const busy = new Set(appointments.map(({ slot_id }) => slot_id));
  byId('slot-count').textContent = `${slots.length - busy.size} open slots`;
  byId('booking-count').textContent = `${appointments.length} booked`;
  byId('doctors').replaceChildren(...doctors.map((doctor) => {
    const card = element('article', 'doctor');
    const header = element('header', 'doctor-heading');
    const name = element('div');
    name.append(element('h3', '', doctor.name), element('p', 'specialty', doctor.specialty));
    header.append(element('span', 'initials', doctor.initials), name);
    card.append(header);

    const days = Map.groupBy(slots.filter((slot) => slot.doctor_id === doctor.id), (slot) => slot.date);
    for (const [date, daySlots] of days) {
      const row = element('div', 'day');
      row.append(element('span', 'day-title', displayDate(date)));
      for (const slot of daySlots) {
        const booked = busy.has(slot.slot_id);
        const label = element('span', booked ? 'slot booked' : 'slot', displayTime(slot.time));
        label.title = `${displayTime(slot.time)} IST, ${booked ? 'booked' : 'available'}`;
        row.append(label);
      }
      card.append(row);
    }
    return card;
  }));

  const rows = appointments.map((appointment) => {
    const row = element('article', 'appointment');
    const details = element('div');
    details.append(
      element('strong', '', appointment.doctor),
      element('p', 'appointment-detail', `${displayDate(appointment.date)} · ${displayTime(appointment.time)} · Phone ending ${appointment.phone_end}`),
    );
    row.append(details, element('span', 'reference', appointment.reference));
    return row;
  });
  byId('appointments').replaceChildren(...(rows.length ? rows : [element('p', 'empty', 'No appointments yet.')]));
}

let priorSchedule;
let refreshingSchedule = false;
async function refreshSchedule() {
  if (refreshingSchedule) return;
  refreshingSchedule = true;
  const error = byId('schedule-error');
  try {
    const response = await fetch('/api/schedule', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('Schedule unavailable');
    const schedule = await response.text();
    if (priorSchedule !== schedule) {
      renderSchedule(JSON.parse(schedule));
      priorSchedule = schedule;
    }
    error.hidden = true;
  } catch {
    error.textContent = 'Could not load the schedule. Check that the Python server is running.';
    error.hidden = false;
  } finally {
    refreshingSchedule = false;
  }
}

const start = byId('start');
const stop = byId('stop');
const mute = byId('mute');
const timer = byId('timer');
const transcript = byId('transcript');
const audio = byId('bot-audio');
const callError = byId('call-error');
let client;
let state = 'idle';
let callStartedAt = null;

function setState(next) {
  state = next;
  byId('call-state').textContent = {
    idle: 'Ready to call', connecting: 'Connecting…', connected: 'Connected',
    ending: 'Ending call…', ended: 'Call ended',
  }[state];
  start.hidden = ['connected', 'ending'].includes(state);
  start.disabled = state === 'connecting';
  stop.hidden = ['idle', 'ended'].includes(state);
  stop.disabled = state === 'ending';
  mute.hidden = state !== 'connected';
  timer.hidden = state !== 'connected';
  if (state !== 'connected') {
    callStartedAt = null;
    timer.textContent = '00:00';
    mute.setAttribute('aria-pressed', 'false');
    mute.textContent = 'Mute';
  }
}

function addTurn(speaker, message) {
  const text = message?.trim();
  if (!text) return;
  transcript.querySelector('.empty')?.remove();
  const row = element('div', speaker === 'You' ? 'turn caller' : 'turn');
  row.append(element('strong', '', speaker), element('p', '', text));
  transcript.append(row);
  transcript.scrollTop = transcript.scrollHeight;
}

function showError(message) {
  callError.textContent = message;
  callError.hidden = false;
}

async function endCall(active) {
  if (!active || active !== client) return;
  setState('ending');
  client = undefined;
  audio.srcObject = null;
  try {
    await active.disconnect();
  } catch {
    showError('The call connection closed unexpectedly. You can start a new call.');
  } finally {
    setState('ended');
  }
}

start.addEventListener('click', async () => {
  callError.hidden = true;
  transcript.replaceChildren(element('p', 'empty', 'Waiting for the assistant…'));
  setState('connecting');
  const active = new PipecatClient({
    transport: new SmallWebRTCTransport(),
    enableMic: true,
    enableCam: false,
    callbacks: {
      onBotReady: () => {
        if (client !== active) return;
        callStartedAt = Date.now();
        setState('connected');
      },
      onDisconnected: () => {
        if (client !== active) return;
        client = undefined;
        audio.srcObject = null;
        setState('ended');
      },
      onTrackStarted: (track, participant) => {
        if (client === active && !participant?.local && track.kind === 'audio') {
          audio.srcObject = new MediaStream([track]);
          audio.play().catch(() => {
            audio.controls = true;
            showError('Your browser paused playback. Press play on the audio control.');
          });
        }
      },
      onUserTranscript: ({ text, final }) => {
        if (client === active && final) addTurn('You', text);
      },
      onBotOutput: (output) => {
        const type = output.text_type ?? output.aggregated_by;
        if (client === active && type !== 'word' && type !== 'token') {
          addTurn('Assistant', output.text);
          void refreshSchedule();
        }
      },
      onError: ({ data }) => {
        if (client === active) showError(data?.error || 'The voice service reported an error.');
      },
    },
  });
  client = active;
  try {
    await active.initDevices();
    if (client !== active) {
      await active.disconnect();
      return;
    }
    await active.connect({ webrtcUrl: new URL('/api/offer', window.location.href).href });
    if (client !== active) await active.disconnect();
  } catch (error) {
    if (client !== active) return;
    showError(`Could not start the call. Check microphone permission, the Python server and provider keys. ${error.message ?? ''}`);
    await endCall(active);
  }
});

stop.addEventListener('click', () => void endCall(client));
mute.addEventListener('click', () => {
  if (!client || state !== 'connected') return;
  const muted = mute.getAttribute('aria-pressed') !== 'true';
  client.enableMic(!muted);
  mute.setAttribute('aria-pressed', String(muted));
  mute.textContent = muted ? 'Unmute' : 'Mute';
});
window.addEventListener('pagehide', () => { void client?.disconnect(); });
setInterval(() => {
  if (callStartedAt === null) return;
  const seconds = Math.floor((Date.now() - callStartedAt) / 1000);
  timer.textContent = [Math.floor(seconds / 60), seconds % 60].map((v) => String(v).padStart(2, '0')).join(':');
}, 1000);

void refreshSchedule();
setInterval(() => { if (state === 'connected') void refreshSchedule(); }, 1800);
