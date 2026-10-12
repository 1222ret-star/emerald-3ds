# Optional day/night, encounters and clock

## Scope

The lighting, timed land encounters and bottom-screen clock are independent,
opt-in features. They introduce no NPC schedules, music changes or new assets.
They do not modify the RTC,
berry updates, daily events, game save layout or data-pack schema.

In OPTION → ENHANCEMENTS:

| Setting | Values | Default |
| --- | --- | --- |
| DAY / NIGHT | OFF, AUTO | OFF |
| CLOCK SPEED | 1X, 6X, 12X, 24X, 60X, 120X | 1X |
| WILD POKEMON | ORIGINAL, TIMED | ORIGINAL |
| SHOW CLOCK | OFF, ON | OFF |

The port persists `day_night=0|1` and `clock_speed=0..5` in its existing
SD settings file, along with `timed_encounters=0|1` and `show_clock=0|1`.
Unknown enable values disable their feature; unknown speed values select 1X.
The shared clock runs whenever at least one consumer is enabled. Lighting
remains unchanged when DAY / NIGHT is OFF, even with timed encounters enabled.

## Clock behaviour

1X reads Emerald's effective local clock, including the saved local-time
offset. The bridge calculates a temporary time instead of rewriting
`gLocalTime` or the game's RTC. It samples at most once per second.

Accelerated rates use elapsed monotonic milliseconds, never game frames.
They start from local game time, retain their phase when changing accelerated
rates, wrap at midnight, and pause over console sleep/suspension. At 24X a
day takes one hour; at 60X, 24 minutes; at 120X, 12 minutes. Selecting 1X
resynchronizes to local time. Disabling all three consumers and re-enabling
one also resynchronizes; toggling one while another remains on retains phase.
The accelerated phase is session-only; only the selected options persist.

## Bottom-screen indicator

SHOW CLOCK displays `HH:MM`, MORNING / DAY / NIGHT and the selected rate
in a compact plate below the location name on the MAP screen. It does not
overlap the map, right-hand buttons, menus or battle UI. Spanish builds show
MANANA / DIA / NOCHE. The name plate uses the small font while the clock is
visible; disabling it restores the original layout. Redraws track minutes,
not frames or seconds, and clock-only changes repaint only the footer.
An unavailable clock displays `--:--` and timed encounters fall back to ORIGINAL.

## Timed land encounters

WILD POKEMON → TIMED (Spanish: POKéMON SALV. → POR HORARIO) switches
selected grass slots on eleven Hoenn routes using the same effective clock:
morning 04:00–09:59, day 10:00–19:59, night 20:00–03:59.
This is a custom, conservative Hoenn schedule, not HGSS encounter data.
Slots are zero-based; their weights remain Emerald's original weights.

| Route | Slot (weight) | Original | Morning | Day | Night |
| --- | --- | --- | --- | --- | --- |
| 101 | 2 (10%) | Wurmple | Taillow | Wurmple | Poochyena |
| 101 | 6 (5%) | Wurmple | Wurmple | Zigzagoon | Poochyena |
| 102 | 3 (10%) | Wurmple | Taillow | Wurmple | Poochyena |
| 102 | 5 (10%) | Lotad | Lotad | Lotad | Oddish |
| 103 | 2 (10%) | Poochyena | Wingull | Zigzagoon | Poochyena |
| 104 | 5 (10%) | Poochyena | Taillow | Wingull | Poochyena |
| 104 | 4 (10%) | Marill | Wurmple | Marill | Zubat |
| 110 | 3 (10%) | Electrike | Electrike | Minun | Oddish |
| 110 | 7 (5%) | Gulpin | Gulpin | Gulpin | Zubat |
| 116 | 4 (10%) | Nincada | Taillow | Nincada | Poochyena |
| 116 | 7 (5%) | Taillow | Taillow | Taillow | Zubat |
| 117 | 3 (10%) | Oddish | Marill | Oddish | Volbeat |
| 117 | 7 (5%) | Illumise | Illumise | Roselia | Illumise |
| 119 | 2 (10%) | Zigzagoon | Zigzagoon | Linoone | Oddish |
| 119 | 7 (5%) | Oddish | Tropius | Oddish | Gloom |
| 120 | 6 (5%) | Oddish | Marill | Oddish | Mightyena |
| 121, 123 | 3 (10%) | Shuppet | Oddish | Gloom | Shuppet |
| 121, 123 | 9 (4%) | Wingull | Wingull | Wingull | Duskull |

All other slots/maps, levels and encounter rates remain unchanged. Water,
fishing/Feebas, Rock Smash, caves, facilities, roamers and scripted encounters
remain original. ORIGINAL returns the exact original table without consuming
RNG. Repel, type-attracting abilities, level selection and shiny generation
continue through the existing engine. Ordinary encounters, Sweet Scent,
visible wild spawns and local land-species queries share the selected tables.
Already visible Pokémon keep their species/personality until they disappear
or are encountered; newly spawned ones follow the current phase. Each rule
checks the original species before applying, avoiding unexpected table edits.

## Lighting

The proposed schedule is inspired by, not an exact reproduction of, HGSS:

| Visual time | Lighting |
| --- | --- |
| 00:00–03:30 | Cool blue night |
| 03:30–04:00 | Smooth transition to morning |
| 04:00–09:30 | Warm morning |
| 09:30–10:00 | Smooth transition to daylight |
| 10:00–16:30 | Original daylight colours |
| 16:30–17:00 | Smooth transition to sunset |
| 17:00–19:30 | Warm sunset |
| 19:30–20:00 | Smooth transition to night |
| 20:00–24:00 | Cool blue night |

Only towns, cities, routes and ocean routes receive the effect. Interiors,
secret bases, caves and underwater maps retain their existing lighting.
Classic battle screens and menus are unchanged. Outdoor voxel battle
scenery uses the cycle; battlers and battle UI are not recoloured.

Classic 2D multiplies the world layers and non-screen-space sprites during
composition, before applying detected palette fades. BG0 text/windows and
tagged screen-space sprites are excluded. Source palettes and cached tile
textures remain unchanged. Voxel lighting modifies existing per-draw colour
grades, distance haze, sunlight rays, motes and dapples; it does not rebuild
meshes or atlases as time advances. Sun direction and baked shadows remain
fixed. Night does not introduce illuminated windows or lamps.

## Automated validation

- `make -C 3ds_port verify-daynight`: rate validation, midnight rollover,
  smooth phase boundaries, elapsed-time/frame-count independence, invalid
  settings, outdoor exclusions, sleep/resume and RTC failure fallback.
- `make -C 3ds_port verify-encounters`: phase boundaries and route/slot/species
  guards in the pure resolver.
- `python3 3ds_port/tests/encounter_tables_test.py --tree build/upstream`:
  production rules against pinned map data, every phase and original fallback,
  with unchanged input tables, levels and rates under ASan/UBSan.
  Repeat with `--tree build/upstream-es` for the Spanish staging.
- `python3 3ds_port/tests/bottom_map_test.py`: partial/full redraw equivalence,
  clock toggles, invalid time, midnight, rate changes and moving between locations.
- Settings shutdown test: all four keys survive the asynchronous writer's latest
  snapshot, including stalled writes and write failures.
- `make -C build/upstream/3ds_port verify PYTHON=python3`: build/link audit
  and the project's host tests, including day/night.
- `python3 -m unittest discover -s builder/tests -v`.
- `python3 tools/release_audit.py --repo . --strict`.

## Hardware validation and acceptance checklist

### Local validation status (2026-10-12)

- Default 3DS development and engine-only release builds: passed in the
  existing devkitPro Docker image using Python 3.12.
- ARM11 hard-float/link and RomFS asset audit: passed, no strong undefined
  symbols; 6,424 assets verified.
- Spanish BPES embedded development build: passed using the user's clean ROM
  in a separate `build/upstream-es` tree. ARM11/link audit and all 6,393
  indexed assets passed; the day/night host tests also passed in this tree.
  Spanish options also include `POKéMON SALV.` and `VER RELOJ`.
- Original touch-screen menu localization: 60 Spanish port labels fit the
  small font's 110-pixel cell area (maximum measured advance: 85 pixels).
- Timed encounter core and all production rule/phase combinations passed,
  including original/invalid setting, indoor and unavailable-clock fallbacks,
  in both language trees. Production table tests passed ASan/UBSan.
- Clock-only/encounters-only consumers, suspension, invalid RTC recovery and
  phase continuity passed. The map raster harness passed partial/full redraw
  comparisons with clock toggles, midnight and location changes.
- Both updated desktop packs passed every entry CRC and matching
  language/engine ABI checks: English `a79c1bd3`, Spanish `b17b20c3`.
- Day/night, input, video decoding, pack and settings shutdown tests: passed.
  Day/night also passed Clang AddressSanitizer/UndefinedBehaviorSanitizer.
- Repository publication audit and `git diff --check`: passed.
- Native syntax checks with VOXEL=0 and VOXEL_LIGHTING=0: passed after
  exempting existing unused-variable/parameter warnings. VOXEL=0 does not
  currently pass the original strict `-Werror` configuration unchanged.
- Full `make verify`: blocked by pre-existing incompatible one-argument
  `VoxelTree_Part`/`VoxelTree_GroundMetatile` stubs in
  `3ds_port/tests/voxel_world_hash_test.c`; production declarations take two
  arguments. Both forms are already present in the base revision.
- Builder suite: 42/43 passed; the existing
  `test_inprocess_matches_subprocess` fixture fails because its subprocess
  generator cannot find `romfs/voxel/regions.bin`. This change does not edit
  the builder or its tests.
- Console validation: the user confirmed the supplied build works on their
  physical 3DS on 2026-10-12 and authorized opening the PR. The console model
  and an itemized checklist were not supplied, so this records user acceptance,
  not a claim that every scenario below was individually verified.
- Follow-up scope: configurable time bands, gentler perceived lighting
  transitions and illuminated windows/lamps are not included in this version.
  The user approved publishing the current tested implementation unchanged.

### Procedure

Back up the console's game save and settings first. Use an engine/data pack
built together from this checkout, or a development build with embedded data.
Do not replace a release executable while keeping an incompatible data pack.

1. With DAY / NIGHT OFF, compare outdoors, weather, menus and battles against
   the previous build. Verify no tint, brightness or performance regression.
2. Enable AUTO at 1X. Confirm lighting follows the clock set inside Emerald,
   not just the system clock. Check both touch and button navigation.
3. Set 120X and observe a complete twelve-minute cycle in classic 2D and
   voxel mode. Verify smooth dawn, daylight, sunset and night in both eyes
   with the 3D slider enabled, and with the slider off.
4. Check player/NPC sprites, visible wild Pokémon, Surf, reflected sprites,
   field move banners, dialogue and location popups. Text/UI must remain
   legible and untinted. Check voxel fallback/warm-up when entering maps.
5. Enter a Pokémon Center, house, secret base, cave and underwater map at
   night. Each must retain its original lighting. Exit and check the cycle
   returns without flickering or a stale indoor/outdoor grade.
6. Check rain, fog, sandstorm, ash, sunny/drought weather, poison flashes,
   doors, warps, Fly and fade-to-black/fade-to-white transitions.
7. Test classic battles, voxel battle scenery, battle intro/exit and moves
   replacing the battle background. Battle text and Pokémon must not tint.
8. Switch accelerated rates: no phase reset. Switch to 1X: resynchronize.
   Disable all clock consumers and re-enable to confirm resynchronization.
   Toggle only the lighting while SHOW CLOCK is ON and confirm phase continuity.
   Use game fast-forward and
   verify the visual clock still advances at the selected clock rate.
9. Close/reopen the lid and use HOME/suspend. Accelerated lighting must not
   jump by the slept interval; 1X must refresh to local time after resume.
10. Restart and soft-reset. All four options persist, but accelerated phase
    restarts from local time. Confirm saves, berries and daily events are
    unchanged. Check FPS on Old 3DS if available.
11. Enable SHOW CLOCK at 1X and 120X. Check the MAP footer, midnight, phase
    boundaries, location changes and tapping the map; switch to other screens
    and battles to verify there is no overlay. Disable it to restore the name plate.
12. Compare ORIGINAL and TIMED on routes 101/104/117/121 at each time band,
    with lighting OFF as well as AUTO. Test random encounters, Sweet Scent,
    visible wild spawns, Repel and attraction abilities. Existing visible mons
    must not reroll when the time band or encounter setting changes.
13. Verify unaffected rare slots, caves, Surf, fishing, Feebas, Rock Smash,
    Battle Frontier, roamers and scripted encounters. ORIGINAL must restore
    the original species distribution immediately for new spawns/encounters.

Record console model, firmware/homebrew entry point, language, renderer,
options, tested areas and results. Visual fidelity and GPU behaviour require
hardware testing; passing host tests alone does not establish acceptance.
The current build has user-confirmed console acceptance. Keep this checklist
for future lighting refinements and regression testing.
