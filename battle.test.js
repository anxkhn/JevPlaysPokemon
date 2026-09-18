import test from 'node:test';
import assert from 'node:assert/strict';
import { createBattle, legalActions, stateFor, baselineAction, runBattle } from './battle.js';
import { askJev, validateAnswer } from './jev.js';
import { opponents } from './teams.js';

test('all five real Gen 3 battles finish, including forced replacements', async () => {
  let replacements = 0;
  for (const opponent of Object.keys(opponents)) {
    const result = await runBattle({ opponent,
      decide: async (state, actions, battle, side) => {
        assert.ok(JSON.stringify(state).length < 30000);
        if (state.forcedSwitch) {
          replacements++;
          assert.ok(actions.every(a => a.id.startsWith('switch_')));
        }
        return { action: baselineAction(battle, side, actions) };
      },
    });
    assert.ok(result.log.some(line => line.startsWith('|win|')));
    assert.ok(result.decisions > 0);
    assert.ok(result.turns > 0 && result.turns < 200);
  }
  assert.ok(replacements > 0);
});

test('requests respect disabled moves, trapping, waiting, and Struggle', () => {
  const battle = createBattle('lorelei');
  try {
    const side = battle.p1;
    const request = side.activeRequest;
    request.active[0].moves[0].disabled = true;
    request.active[0].trapped = true;
    assert.ok(legalActions(battle, side).every(a => a.id !== 'move_1' && !a.id.startsWith('switch_')));
    request.active[0].moves = [{ move: 'Struggle', id: 'struggle', target: 'randomNormal' }];
    assert.deepEqual(legalActions(battle, side).map(a => a.command), ['move 1']);
    side.activeRequest = { wait: true };
    assert.deepEqual(legalActions(battle, side), []);
  } finally { battle.destroy(); }
});

test('state uses Gen 3 physical/special categories and serializable data', () => {
  const battle = createBattle('lorelei');
  try {
    const state = stateFor(battle, battle.p1);
    assert.equal(state.you.moves.find(m => m.name === 'Bite').category, 'Special');
    assert.equal(state.you.moves.find(m => m.name === 'Double Kick').category, 'Physical');
    assert.deepEqual(JSON.parse(JSON.stringify(state)), state);
  } finally { battle.destroy(); }
});

test('Jev sends only JSON state and maps a validated choice to an engine command', async () => {
  const actions = [{ id: 'move_1', command: 'move 1', description: 'Thunderbolt' }];
  const response = { model: 'jev-1.13.0', answers: { action: {
    type: 'choice', choice: 'move_1', confidence: 1, probabilities: { move_1: 1 },
  } }, usage: { input_tokens: 12, output_tokens: 5 } };
  const result = await askJev({ turn: 1 }, actions, { key: 'test-only', fetchImpl: async (url, options) => {
    assert.equal(url, 'https://api.typesafe.ai/v1/systemone');
    assert.equal(options.headers.Authorization, 'Bearer test-only');
    const payload = JSON.parse(options.body);
    assert.deepEqual(payload.state, { turn: 1 });
    assert.deepEqual(payload.questions.action.criteria, { move_1: 'Thunderbolt' });
    return Response.json(response);
  } });
  assert.equal(result.action.command, 'move 1');
  assert.ok(!JSON.stringify(result).includes('test-only'));
  assert.throws(() => validateAnswer({ answers: { action: { ...response.answers.action, choice: 'move_9' } } }, actions), /invalid action/);
  assert.throws(() => validateAnswer({ answers: { action: { ...response.answers.action, probabilities: { move_1: 0.1 } } } }, actions), /probability/);
  await assert.rejects(askJev({}, actions, { key: 'test-only', fetchImpl: async () => new Response('', { status: 401 }) }), /HTTP 401/);
});

test('decision budget and illegal actions fail instead of inventing a win', async () => {
  await assert.rejects(runBattle({ opponent: 'lorelei', maxDecisions: 1,
    decide: async (_, actions) => ({ action: actions[0] }),
  }), /battle is incomplete/);
  await assert.rejects(runBattle({ opponent: 'lorelei',
    decide: async () => ({ action: { id: 'move_99' } }),
  }), /outside the legal action set/);
});
