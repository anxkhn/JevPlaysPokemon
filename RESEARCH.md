# Project research

Checked September 18, 2026 against repository source and primary documentation. A short list of the projects that mattered, not a catalog.

## Best options

| Project | Actual interface and support | Fit |
| --- | --- | --- |
| [Pokémon Showdown](https://github.com/smogon/pokemon-showdown/blob/master/sim/SIMULATOR.md) | In-process JavaScript simulator, structured choice requests, text protocol, Gen 3 custom teams. | Chosen. Smallest complete battle-only loop, with no emulator or local server. |
| [poke-env](https://github.com/hsahovic/poke-env) | Python battle objects and agents backed by a Showdown server. No pixels required. | Best Python starting point, but adds a server and language boundary to this implementation. |
| [PokéLLMon](https://github.com/git-disl/PokeLLMon) | Existing text-only Showdown LLM agent with feedback, move/type knowledge, and action generation. [Paper](https://arxiv.org/html/2402.01118v3). | Useful strategy reference. Its published evaluation is not a FireRed Elite Four run. |
| [PokéBot Gen3](https://github.com/40Cakes/pokebot-gen3) | Working mGBA RAM readers, battle strategies, menu automation, and FireRed/LeafGreen support, including USA/Europe Rev 1. | Best candidate for the supplied v1.1 ROM. Native mGBA/Tk setup and an Elite Four save are additional work. |
| [Clad3815 FireRed agent](https://github.com/Clad3815/gpt-play-pokemon-firered) | mGBA Lua bridge, Python state API, Node/OpenAI agent, screenshots plus structured RAM. | Real FireRed implementation. Requires adaptation and a particular ROM checksum; do not assume v1.1 compatibility. |
| [NousResearch/pokemon-agent](https://github.com/NousResearch/pokemon-agent) | Agent-facing state API, working Game Boy support. | FireRed is not implemented. Do not choose it based on the filename alone. |

### Source details that affect the choice

- NousResearch's [`memory/firered.py`](https://github.com/NousResearch/pokemon-agent/blob/f8a03e4a8bc58f1d9dda6d677a7436cc832a57a9/pokemon_agent/memory/firered.py) raises `NotImplementedError` in its party, battle, and decryption functions. The README still labels FireRed as Phase 2.
- PokéBot's [`BattleStrategy`](https://github.com/40Cakes/pokebot-gen3/blob/5dd898f830775d448b06db6f5cd65b930540f146/modules/battle_strategies/_interface.py) supplies `decide_turn` and `choose_new_lead_after_faint`. These are natural Jev integration points. Its [macOS installation guide](https://github.com/40Cakes/pokebot-gen3/blob/5dd898f830775d448b06db6f5cd65b930540f146/wiki/pages/MacOS%20Installation.md) and [supported ROM list](https://github.com/40Cakes/pokebot-gen3/blob/main/wiki/pages/Supported%20Games%20and%20Languages.md) should be checked before an emulator implementation.
- Clad3815's [README](https://github.com/Clad3815/gpt-play-pokemon-firered/blob/9619b101d607ee79b68e1274174ac3b6eeb6ff06/README.md) specifies ROM MD5 `e26ee0d44e809351c8ce2d73c7400cdd`, rather than general FireRed compatibility. Its license is CC BY-NC 4.0.
- Showdown's [choice protocol](https://github.com/smogon/pokemon-showdown/blob/master/sim/SIM-PROTOCOL.md#choice-requests) provides available moves and forced switches. A choice request alone is not a complete state snapshot. This project deliberately serializes selected fields from the engine and labels them full information.

## Other projects and input modalities

| Project | Verified input and scope |
| --- | --- |
| [David Hershey's Claude starter](https://github.com/davidhershey/ClaudePlaysPokemonStarter) | Pokémon Red through PyBoy. Screenshots plus RAM-derived location, inventory, party, dialogue and move data. Full-game button control, not a ready FireRed battle interface. The starter is not necessarily the complete streamed system. |
| [Joel Z's Gemini Plays Pokémon](https://blog.jcz.dev/the-making-of-gemini-plays-pokemon) | Annotated screenshots plus RAM-derived objects, navigability, stats and inventory. Blue, Yellow Legacy and Crystal are documented. Still images per action, not raw video. The [public tracking repository](https://github.com/waylaidwanderer/gemini-plays-pokemon-public) is not the complete original runtime. |
| [PokéAgent Challenge battle track](https://pokeagentchallenge.com/battling.html) and [PokéChamp](https://github.com/sethkarten/pokechamp) | Showdown battle benchmarks with text-based LLM and encoded-state RL baselines. Current formats include Gen 3 OU and other generations. Not an Elite Four implementation. The [RPG track](https://pokeagentchallenge.com/speedrunning.html) targets Emerald and combines visual/structured observations. |
| [adenta/fire_red_agent](https://github.com/adenta/fire_red_agent) | RetroArch FireRed, RAM-derived information, screenshot OCR, and memories. The author reports battle automation that mostly presses A, followed by random inputs. Development paused over control problems. Poor foundation for evaluating battle decisions. |

The separate John Verron/GPT-5.2 completion story in the brief could not be tied to a verified primary artifact during this research. Clad3815's repository exists, but this report does not treat the attribution or claimed autonomous completion as established, or count it as a second repository.

The older `bouletmarc/PokeBot-GenerationIII` and unnamed Twitch/RL projects add no verified advantage over the maintained options above and were not adopted or runtime-tested.

## Corrections to the brief

1. Claude and Gemini systems use still images and structured text, rather than continuous video. That does not prove vision is dispensable. The claimed no-vision ablation with unchanged performance was not verified in the primary sources checked.
2. FireRed's Elite Four allows bag healing between trainers. You cannot return to a Pokémon Center mid-run. [Trainer roster and rules](https://www.serebii.net/fireredleafgreen/elitefour.shtml).
3. Showdown Gen 3 is a battle simulator, not the FireRed cartridge campaign. Trainer AI, badge effects, inventory and inter-battle state require their own treatment. This implementation calls its matchups FireRed-inspired and heals between matches.
4. A complete text description must include relevant mechanics and distinguish known from hidden information. There is no universal guarantee that a small HP/types/moves summary is lossless. This prototype provides additional active state and recent events, but is not a benchmark-grade observation for every possible custom team.
5. The supplied credential works with TypeSafe's direct API. [API reference](https://docs.typesafe.ai/api.md), [Choice primitive](https://docs.typesafe.ai/primitives/choice.md), and [model documentation](https://docs.typesafe.ai/models.md) define the actual request and response. Jev accepts text/JSON, not images or video.

## Decision

Use the direct Showdown JavaScript engine and TypeSafe HTTP endpoint for the requested minimum battle-only scope. No need to fork a full RPG agent, deploy a server, or automate emulator menus to establish that Jev can select and execute battle actions end to end.

For the next distinct requirement, actual FireRed ROM execution, adapt PokéBot Gen3's battle strategy interface after preparing a compatible league save. The ROM alone does not place a party at the Elite Four.
