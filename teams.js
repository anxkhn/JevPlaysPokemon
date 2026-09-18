import showdown from 'pokemon-showdown';

const dex = showdown.Dex.mod('gen3');
function pokemon(species, level, moves) {
  return {
    species, name: species, level, moves: moves.split(', '),
    ability: dex.species.get(species).abilities[0], nature: 'Hardy',
    evs: { hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 },
    ivs: { hp: 31, atk: 31, def: 31, spa: 31, spd: 31, spe: 31 },
    item: '', gender: 'M',
  };
}

export const playerTeam = [
  pokemon('Jolteon', 60, 'Thunderbolt, Bite, Thunder Wave, Double Kick'),
  pokemon('Lapras', 60, 'Surf, Ice Beam, Thunderbolt, Confuse Ray'),
  pokemon('Alakazam', 60, 'Psychic, Recover, Calm Mind, Reflect'),
  pokemon('Charizard', 60, 'Flamethrower, Fly, Slash, Dragon Claw'),
  pokemon('Snorlax', 60, 'Body Slam, Shadow Ball, Earthquake, Rest'),
  pokemon('Nidoking', 60, 'Earthquake, Rock Slide, Ice Beam, Megahorn'),
];

// Species and levels match the first FireRed league; movesets are battle presets.
export const opponents = {
  lorelei: [
    pokemon('Dewgong', 52, 'Surf, Ice Beam, Hail, Safeguard'),
    pokemon('Cloyster', 51, 'Dive, Spikes, Hail, Protect'),
    pokemon('Slowbro', 52, 'Surf, Ice Beam, Yawn, Amnesia'),
    pokemon('Jynx', 54, 'Ice Punch, Double Slap, Lovely Kiss, Attract'),
    pokemon('Lapras', 54, 'Surf, Ice Beam, Body Slam, Confuse Ray'),
  ],
  bruno: [
    pokemon('Onix', 51, 'Earthquake, Rock Tomb, Iron Tail, Roar'),
    pokemon('Hitmonchan', 53, 'Sky Uppercut, Mach Punch, Rock Tomb, Counter'),
    pokemon('Hitmonlee', 53, 'Brick Break, Mega Kick, Facade, Foresight'),
    pokemon('Onix', 54, 'Earthquake, Iron Tail, Double Edge, Sand Tomb'),
    pokemon('Machamp', 56, 'Cross Chop, Rock Tomb, Bulk Up, Scary Face'),
  ],
  agatha: [
    pokemon('Gengar', 54, 'Shadow Punch, Confuse Ray, Toxic, Double Team'),
    pokemon('Golbat', 54, 'Air Cutter, Bite, Confuse Ray, Poison Fang'),
    pokemon('Haunter', 53, 'Hypnosis, Dream Eater, Curse, Mean Look'),
    pokemon('Arbok', 56, 'Sludge Bomb, Iron Tail, Screech, Bite'),
    pokemon('Gengar', 58, 'Shadow Ball, Sludge Bomb, Hypnosis, Nightmare'),
  ],
  lance: [
    pokemon('Gyarados', 56, 'Hyper Beam, Bite, Dragon Rage, Twister'),
    pokemon('Dragonair', 54, 'Outrage, Safeguard, Hyper Beam, Dragon Rage'),
    pokemon('Dragonair', 54, 'Outrage, Safeguard, Hyper Beam, Dragon Rage'),
    pokemon('Aerodactyl', 58, 'Wing Attack, Ancient Power, Scary Face, Hyper Beam'),
    pokemon('Dragonite', 60, 'Outrage, Wing Attack, Safeguard, Hyper Beam'),
  ],
  champion: [
    pokemon('Pidgeot', 59, 'Aerial Ace, Feather Dance, Sand Attack, Whirlwind'),
    pokemon('Alakazam', 57, 'Psychic, Reflect, Recover, Future Sight'),
    pokemon('Rhydon', 59, 'Earthquake, Rock Tomb, Take Down, Scary Face'),
    pokemon('Exeggutor', 59, 'Giga Drain, Egg Bomb, Sleep Powder, Light Screen'),
    pokemon('Gyarados', 61, 'Hydro Pump, Dragon Rage, Bite, Thrash'),
    pokemon('Charizard', 63, 'Fire Blast, Aerial Ace, Slash, Fire Spin'),
  ],
};
