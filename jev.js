import { readFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

function loadEnv() {
  try {
    for (const raw of readFileSync(new URL('./.env', import.meta.url), 'utf8').split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('#') || !line.includes('=')) continue;
      const eq = line.indexOf('=');
      const name = line.slice(0, eq).trim();
      let value = line.slice(eq + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      if (process.env[name] === undefined) process.env[name] = value;
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
}

export function loadKey() {
  loadEnv();
  const key = process.env.TYPESAFE_API_KEY?.trim();
  if (!key) throw new Error('Set TYPESAFE_API_KEY in .env or in the environment.');
  return key;
}

export function validateAnswer(result, actions) {
  const answer = result?.answers?.action;
  if (answer?.type !== 'choice' || !actions.some(a => a.id === answer.choice)) {
    throw new Error('Jev returned an invalid action. No move was submitted.');
  }
  if (!Number.isFinite(answer.confidence) || answer.confidence < 0 || answer.confidence > 1) {
    throw new Error('Jev returned invalid confidence.');
  }
  const probabilities = answer.probabilities;
  if (!probabilities || Object.keys(probabilities).length !== actions.length ||
      actions.some(a => !Number.isFinite(probabilities[a.id]) || probabilities[a.id] < 0 || probabilities[a.id] > 1) ||
      Math.abs(Object.values(probabilities).reduce((a, b) => a + b, 0) - 1) > 0.02) {
    throw new Error('Jev returned an invalid probability distribution.');
  }
  return answer;
}

export async function askJev(state, actions, { key, model = 'jev-1.13.0', fetchImpl = fetch } = {}) {
  const request = {
    model,
    state,
    questions: {
      action: {
        type: 'choice',
        instructions: 'Choose the best legal action to win this Generation 3 singles Pokemon battle. Use HP, type matchups, abilities, move effects, speed and stat boosts. Prefer a reliable knockout. Switch when the matchup is poor, but avoid repeated switches that take free damage. Physical/special categories follow Gen 3 types. Only choose from the provided actions.',
        criteria: Object.fromEntries(actions.map(a => [a.id, a.description])),
      },
    },
  };
  const started = Date.now();
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetchImpl('https://api.typesafe.ai/v1/systemone', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(45000),
    });
    if ([429, 500, 502, 503, 504, 529].includes(response.status) && attempt < 2) {
      const retry = Number(response.headers.get('retry-after'));
      await response.body?.cancel();
      await sleep(Math.min(30000, Math.max(1000 * 2 ** attempt, Number.isFinite(retry) ? retry * 1000 : 0)));
      continue;
    }
    if (!response.ok) throw new Error(`TypeSafe API HTTP ${response.status}. Check your key, balance, and service availability.`);
    const result = await response.json();
    const answer = validateAnswer(result, actions);
    return { action: actions.find(a => a.id === answer.choice), request, result, latencyMs: Date.now() - started };
  }
}
