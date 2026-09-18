import showdown from 'pokemon-showdown';
import { playerTeam, opponents } from './teams.js';

export function createBattle(opponent, seed = [1, 2, 3, 4], team = playerTeam) {
  const battle = new showdown.Battle({ formatid: 'gen3customgame', seed });
  battle.setPlayer('p1', { name: 'Jev', team: showdown.Teams.pack(team) });
  battle.setPlayer('p2', { name: opponent, team: showdown.Teams.pack(opponents[opponent]) });
  return battle;
}

function moveData(battle, id) {
  const move = battle.dex.moves.get(id);
  return { name: move.name, type: move.type, category: battle.getCategory(move), power: move.basePower,
    accuracy: move.accuracy, priority: move.priority, effect: move.desc || move.shortDesc };
}

export function legalActions(battle, side) {
  const request = side.activeRequest;
  if (!request || request.wait) return [];
  if (request.teamPreview) throw new Error('Only Gen 3 singles without team preview is supported.');
  const actions = [];
  if (!request.forceSwitch) {
    for (const [index, move] of request.active[0].moves.entries()) {
      if (!move.disabled) actions.push({ id: `move_${index + 1}`, command: `move ${index + 1}`,
        description: JSON.stringify({ action: 'use move', ...moveData(battle, move.id), pp: move.pp }) });
    }
  }
  if (request.forceSwitch || !request.active[0].trapped) {
    for (const [index, pokemon] of request.side.pokemon.entries()) {
      if (!pokemon.active && !pokemon.condition.endsWith('fnt')) actions.push({ id: `switch_${index + 1}`,
        command: `switch ${index + 1}`, description: `Switch to ${pokemon.details}, HP/status ${pokemon.condition}, moves ${pokemon.moves.join(', ')}` });
    }
  }
  if (!actions.length) throw new Error('No legal actions in an active request.');
  return actions;
}

function describePokemon(battle, pokemon, detailed = false) {
  const data = {
    species: pokemon.species.name, level: pokemon.level, types: pokemon.getTypes(),
    hp: pokemon.hp, maxHp: pokemon.maxhp, status: pokemon.status || 'healthy',
    ability: pokemon.ability, item: pokemon.item || 'none',
    moves: pokemon.moveSlots.map(m => ({ name: m.move, pp: m.pp })),
  };
  if (detailed) Object.assign(data, {
    stats: Object.fromEntries(['atk', 'def', 'spa', 'spd', 'spe'].map(stat => [stat, pokemon.getStat(stat)])),
    boosts: { ...pokemon.boosts }, volatiles: Object.keys(pokemon.volatiles),
    moves: pokemon.moveSlots.map(m => ({ ...moveData(battle, m.id), pp: m.pp })),
  });
  return data;
}

export function stateFor(battle, side) {
  return {
    rules: 'Generation 3 singles. Full-information experiment: both teams and exact HP are visible. No bag items. Each trainer battle starts with a fully healed team. Physical/special split is by type, not by move.',
    turn: battle.turn, forcedSwitch: Boolean(side.activeRequest.forceSwitch),
    weather: battle.field.weather || 'none',
    fieldConditions: Object.keys(battle.field.pseudoWeather),
    yourSideConditions: Object.keys(side.sideConditions),
    opponentSideConditions: Object.keys(side.foe.sideConditions),
    you: describePokemon(battle, side.active[0], true),
    opponent: describePokemon(battle, side.foe.active[0], true),
    yourTeam: side.pokemon.map(p => describePokemon(battle, p)),
    opponentTeam: side.foe.pokemon.map(p => ({ species: p.species.name, hp: p.hp, maxHp: p.maxhp, status: p.status })),
    recentEvents: battle.log.filter(line => /^\|(move|switch|faint|-damage|-heal|-status|-boost|-unboost|-immune|-supereffective|-resisted)\|/.test(line)).slice(-12),
  };
}

// ponytail: approximate damage baseline ignores setup and switching strategy.
export function baselineAction(battle, side, actions) {
  const target = side.foe.active[0];
  const source = side.active[0];
  const moves = actions.filter(a => a.id.startsWith('move_'));
  if (!moves.length) return actions[0];
  const score = action => {
    const index = Number(action.id.split('_')[1]) - 1;
    const move = battle.dex.moves.get(side.activeRequest.active[0].moves[index].id);
    if (!battle.dex.getImmunity(move.type, target) || (move.type === 'Ground' && target.ability === 'levitate') ||
      (move.type === 'Water' && target.ability === 'waterabsorb') || (move.type === 'Electric' && target.ability === 'voltabsorb')) return -1;
    const physical = battle.getCategory(move) === 'Physical';
    const ratio = source.getStat(physical ? 'atk' : 'spa') / target.getStat(physical ? 'def' : 'spd');
    return move.basePower * ratio * (source.hasType(move.type) ? 1.5 : 1) *
      2 ** battle.dex.getEffectiveness(move.type, target) * (move.accuracy === true ? 1 : move.accuracy / 100);
  };
  return moves.reduce((best, action) => score(action) > score(best) ? action : best);
}

export async function runBattle({ opponent, decide, seed, maxDecisions = 200, onDecision = () => {}, team }) {
  const battle = createBattle(opponent, seed, team);
  let decisions = 0;
  try {
    while (!battle.ended) {
      if (decisions >= maxDecisions) throw new Error(`Decision limit ${maxDecisions} reached; battle is incomplete.`);
      const p1 = battle.p1;
      const p2 = battle.p2;
      const actions = legalActions(battle, p1);
      const opponentActions = legalActions(battle, p2);
      const opponentAction = opponentActions.length ? baselineAction(battle, p2, opponentActions) : null;
      if (!actions.length && !opponentAction) throw new Error('Battle stalled without a choice request.');
      if (actions.length) {
        const state = stateFor(battle, p1);
        const decision = await decide(state, actions, battle, p1);
        const action = actions.find(a => a.id === decision.action?.id);
        if (!action) throw new Error('Agent chose an action outside the legal action set.');
        decisions++;
        await onDecision({ decision: decisions, turn: battle.turn, state, ...decision, action });
        if (!battle.choose('p1', action.command)) throw new Error(`Engine rejected ${action.command}: ${p1.choice.error}`);
      }
      if (opponentAction && !battle.ended && !battle.choose('p2', opponentAction.command)) {
        throw new Error(`Engine rejected opponent choice: ${p2.choice.error}`);
      }
    }
    return { opponent, winner: battle.winner || 'tie', turns: battle.turn, decisions,
      seed: battle.prngSeed, log: [...battle.log], inputLog: [...battle.inputLog] };
  } finally {
    battle.destroy();
  }
}
