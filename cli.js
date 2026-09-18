import { parseArgs } from 'node:util';
import { mkdirSync, appendFileSync, writeFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { runBattle, baselineAction } from './battle.js';
import { askJev, loadKey } from './jev.js';
import { opponents } from './teams.js';

async function main() {
  const { values } = parseArgs({ options: {
    agent: { type: 'string', default: 'jev' }, opponent: { type: 'string', default: 'lorelei' },
    seed: { type: 'string', default: '1,2,3,4' }, 'max-decisions': { type: 'string', default: '200' },
    model: { type: 'string', default: 'jev-1.13.0' }, team: { type: 'string' },
    help: { type: 'boolean', short: 'h' },
  } });
  if (values.help) {
    console.log(`Jev plays Pokemon, text-only Gen 3 battles

npm start -- [--agent jev|human|baseline] [--opponent ${Object.keys(opponents).join('|')}|all]
             [--seed 1,2,3,4] [--max-decisions 200] [--model jev-1.13.0] [--team team.json]

Default: Jev vs Lorelei. The opponent uses an approximate damage baseline.
Each matchup starts fully healed. This runs Showdown, not the FireRed ROM.
JSONL decisions, battle protocols and summaries are saved in runs/.`);
    return;
  }
  if (!['jev', 'human', 'baseline'].includes(values.agent)) throw new Error('Unknown agent. Use jev, human, or baseline.');
  if (values.opponent !== 'all' && !Object.hasOwn(opponents, values.opponent)) throw new Error('Unknown opponent. Use --help.');
  const seed = values.seed.split(',').map(Number);
  if (seed.length !== 4 || seed.some(n => !Number.isInteger(n) || n < 0 || n > 65535)) throw new Error('Seed requires four integers between 0 and 65535.');
  const maxDecisions = Number(values['max-decisions']);
  if (!Number.isSafeInteger(maxDecisions) || maxDecisions < 1) throw new Error('--max-decisions must be a positive integer.');
  const team = values.team ? JSON.parse(readFileSync(values.team, 'utf8')) : undefined;
  if (team && (!Array.isArray(team) || team.length < 1 || team.length > 6 || team.some(p => !p.species || !Array.isArray(p.moves) || !p.moves.length || p.moves.length > 4))) {
    throw new Error('Team JSON must contain 1-6 Pokemon with species and 1-4 moves each.');
  }
  const key = values.agent === 'jev' ? loadKey() : undefined;
  const rl = values.agent === 'human' ? createInterface({ input: process.stdin, output: process.stdout }) : null;
  const directory = join('runs', `${new Date().toISOString().replaceAll(':', '-')}-${values.agent}`);
  mkdirSync(directory, { recursive: true });
  console.log(`Full-information Gen 3 battles. Agent: ${values.agent}. Logs: ${directory}`);
  const summaries = [];
  try {
    for (const opponent of values.opponent === 'all' ? Object.keys(opponents) : [values.opponent]) {
      let inputTokens = 0, outputTokens = 0, apiCalls = 0;
      console.log(`\nAgainst ${opponent}`);
      const result = await runBattle({ opponent, seed, team, maxDecisions,
        decide: async (state, actions, battle, side) => {
          if (values.agent === 'jev') return askJev(state, actions, { key, model: values.model });
          if (values.agent === 'baseline') return { action: baselineAction(battle, side, actions) };
          console.log(JSON.stringify(state, null, 2));
          actions.forEach((action, i) => console.log(`${i + 1}. ${action.description}`));
          while (true) {
            const input = await rl.question('Action number, or q to quit: ');
            if (input === 'q') throw new Error('Stopped by player.');
            const index = Number(input) - 1;
            if (Number.isInteger(index) && actions[index]) return { action: actions[index] };
            console.log('Choose one of the listed action numbers.');
          }
        },
        onDecision: record => {
          appendFileSync(join(directory, `${opponent}.jsonl`), JSON.stringify(record) + '\n');
          if (record.result) {
            apiCalls++;
            inputTokens += record.result.usage?.input_tokens || 0;
            outputTokens += record.result.usage?.output_tokens || 0;
          }
          const confidence = record.result ? ` confidence=${record.result.answers.action.confidence.toFixed(2)}` : '';
          console.log(`Turn ${record.turn}: ${record.state.you.species} ${record.state.you.hp}/${record.state.you.maxHp} vs ${record.state.opponent.species} ${record.state.opponent.hp}/${record.state.opponent.maxHp} -> ${record.action.command}${confidence}`);
        },
      });
      writeFileSync(join(directory, `${opponent}.battle.log`), result.log.join('\n'));
      writeFileSync(join(directory, `${opponent}.input.log`), result.inputLog.join('\n'));
      const { log, inputLog, ...summary } = result;
      summaries.push({ ...summary, agent: values.agent, apiCalls, inputTokens, outputTokens });
      writeFileSync(join(directory, 'summary.json'), JSON.stringify(summaries, null, 2));
      console.log(`Winner: ${result.winner}. ${result.turns} turns, ${apiCalls} API calls.`);
    }
  } catch (error) {
    writeFileSync(join(directory, 'error.json'), JSON.stringify({ error: error.message, completedBattles: summaries }, null, 2));
    throw error;
  } finally {
    rl?.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
