/*
 * Scene cycling for the GPU memory gate of phase F2 (-DCTR_CYCLE_TEST=cycles):
 * "100 scene cycles and a long session without a failure, corruption or loss
 * of 3D". Built only for that test; an ordinary build has none of it.
 *
 * From the player's save it presses A until the field is up, then cycles: the
 * voxel world on or off, the battle over it on or off and the 3D slider at 0
 * or 1 (the eight combinations in turn), a few seconds of field, a wild
 * battle, out of it by RUN (the action cursor set to it, A pressed), and back
 * to the field. Each cycle is logged; the frame profile's segments say how
 * much 3D each scene showed and GPUMEM what failed. The settings it changes
 * are not saved, and the game is never saved.
 */
#include <stdio.h>
#include "global.h"
#include "main.h"
#include "battle.h"
#include "battle_setup.h"
#include "script_pokemon_util.h"
#include "overworld.h"
#include "constants/species.h"
#include "3ds_platform.h"

#ifdef CTR_CYCLE_TEST

extern u8 gActionSelectionCursor[MAX_BATTLERS_COUNT];

#define CYCLE_FIELD_FRAMES 300
#define CYCLE_PRESS_EVERY 20

static u32 sFrame, sFieldSince, sCycle, sBattles;
static bool8 sStarted, sInBattle, sPress;

void CtrCycle_Frame(void)
{
    bool8 field = gMain.callback2 == CB2_Overworld && !gMain.inBattle;

    ++sFrame;
    if (!sStarted)
    {
        sStarted = TRUE;
        CtrSettings_Freeze();
        CtrSettings_ApplyLine("speed=1");
        CtrLog_Write(CTR_LOG_GAME, "CYCLE test: %u cycles", (unsigned)CTR_CYCLE_TEST);
    }
    sPress = FALSE;
    if (gMain.inBattle)
    {
        if (!sInBattle)
            ++sBattles;
        sInBattle = TRUE;
        for (unsigned i = 0; i < MAX_BATTLERS_COUNT; ++i)
            gActionSelectionCursor[i] = 3;
        sPress = (sFrame % CYCLE_PRESS_EVERY) < 2;
        sFieldSince = 0;
        return;
    }
    sInBattle = FALSE;
    if (!field)
    {
        /* The title and the main menu: CONTINUE is the default. */
        sPress = sCycle == 0 && (sFrame % 40) < 2;
        sFieldSince = 0;
        return;
    }
    if (!sFieldSince)
    {
        unsigned k = sCycle;
        char line[32];

        if (sCycle == CTR_CYCLE_TEST)
        {
            CtrLog_Write(CTR_LOG_GAME, "CYCLE test done: %lu cycles, %lu battles", (unsigned long)sCycle,
                         (unsigned long)sBattles);
            CtrPlatform_RequestExit();
            sFieldSince = sFrame;
            return;
        }
        snprintf(line, sizeof(line), "voxel=%u", k & 1);
        CtrSettings_ApplyLine(line);
        snprintf(line, sizeof(line), "voxel_battle=%u", (k >> 1) & 1);
        CtrSettings_ApplyLine(line);
        CtrScenario_ForceSlider((k >> 2) & 1 ? 1.0f : 0.0f);
        CtrLog_Write(CTR_LOG_GAME, "CYCLE %u voxel=%u battle3d=%u slider=%u at frame %lu", k, k & 1, (k >> 1) & 1,
                     (k >> 2) & 1, (unsigned long)sFrame);
        sFieldSince = sFrame;
        return;
    }
    if (sCycle < CTR_CYCLE_TEST && sFrame - sFieldSince == CYCLE_FIELD_FRAMES)
    {
        ++sCycle;
        CreateScriptedWildMon(SPECIES_ZIGZAGOON, 5, 0);
        BattleSetup_StartScriptedWildBattle();
    }
}

void CtrCycle_Input(CtrInputSample *sample)
{
    if (sPress)
        sample->buttons |= 1;
}

#else

void CtrCycle_Frame(void) {}
void CtrCycle_Input(CtrInputSample *sample) { (void)sample; }

#endif
