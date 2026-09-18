# Verified run

## Actual FireRed emulator runs

The newer implementation runs the supplied USA v1.1 ROM with mGBA. These results are separate from the original Showdown experiment below.

| Real Jev run | Starting party | Result | API decisions | Verified switches |
| --- | --- | --- | ---: | ---: |
| `20260918-105222-923929` | Current six, level 40 | Lorelei won | 34 | 5 |
| `20260918-105329-138886` | Current six, level 40 | Bruno won | 21 | 5 |
| `20260918-105753-782102` | Current six, level 40 | Agatha won | 26 | 5 |
| `20260918-105934-395003` | Current six, level 40 | Lorelei won | 39 | 7 |
| `20260918-110050-677495` | Current six, level 40 | Bruno lost | 24 | 5 |

The last two rows are one consecutive league attempt. It stopped on the real loss. No five-win level-40 completion is claimed. The earlier sequence reached Agatha but stopped on a voluntary-switch controller bug, which was then fixed and tested in the subsequent Agatha win.

Both forced replacements and voluntary switches now identify the selected Pokémon by personality after the party menu stabilizes. The adapter checks HP and cursor identity before confirmation, then verifies the active battler matches that identity at the next decision.

`./emulator.sh --check-custom` passed custom player/opponent RAM readback and automatic Lance-to-Champion progression using an explicitly separate, level-100 baseline test fixture. It does not demonstrate Jev skill or change the level-40 configuration.

Dashboard checks passed for browser boot, catalog loading, replay seeking, model probability display, expandable request/response JSON, and mobile overflow. A prior live browser test verified pause/resume and recorded a level-60 Lorelei win with H.264 video and AAC audio.

## Original Showdown run

September 18, 2026. Local Pokémon Showdown 0.11.11, `gen3customgame`, seed `1,2,3,4`. TypeSafe returned `jev-1.13.0` for the live decisions.

```sh
npm start -- --opponent all
```

| Opponent | Winner | Turns | Real API decisions | Input tokens |
| --- | --- | ---: | ---: | ---: |
| Lorelei | Jev | 9 | 9 | 30,662 |
| Bruno | Jev | 11 | 14 | 46,089 |
| Agatha | Jev | 8 | 9 | 30,085 |
| Lance | Jev | 10 | 11 | 37,704 |
| Champion | Jev | 17 | 20 | 67,637 |
| Total | 5 wins | 55 | 63 | 212,177 |

Output usage was 5,751 tokens. At the documented input price of $0.042 per million tokens, the estimated model cost is about $0.0089. This is a calculated estimate, not a billing receipt.

Run artifacts are gitignored. A local Showdown run writes the same layout under `runs/<timestamp>-jev/`:

- `summary.json` contains winners, turns, decisions, seeds, and usage.
- Each trainer's `.jsonl` contains the exact state, legal choice criteria, submitted action, latency, returned model, probabilities, confidence, and usage.
- Each `.battle.log` records the engine's resolved battle and winning event.
- Each `.input.log` records the engine setup and submitted commands.

The offline baseline also won all five matches. These easy fixed matchups establish integration, not superior tactics. Jev made mistakes, including selecting Thunderbolt against Onix. There is no scripted replacement of low-confidence answers.

Every trainer starts with a fresh, fully healed player party. Opponents use a simple damage heuristic, and Jev receives privileged state. These results do not establish that Jev beat the authentic FireRed Elite Four campaign.
