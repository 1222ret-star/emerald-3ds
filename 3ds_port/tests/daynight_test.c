#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "3ds_daynight.h"

static uint64_t sNow;
static unsigned sLocal = 12 * 3600;
static int sEnabled, sSpeed, sShowClock, sTimedEncounters;
static bool sOutdoor = true, sClockValid = true;

uint64_t CtrPlatform_Milliseconds(void) { return sNow; }
bool CtrGame_IsOutdoor(void) { return sOutdoor; }
bool CtrGame_LocalTimeSeconds(unsigned *seconds)
{
    *seconds = sLocal;
    return sClockValid;
}
int CtrSettings_GetInt(const char *key, int fallback)
{
    if (strcmp(key, "day_night") == 0) return sEnabled;
    if (strcmp(key, "clock_speed") == 0) return sSpeed;
    if (strcmp(key, "show_clock") == 0) return sShowClock;
    if (strcmp(key, "timed_encounters") == 0) return sTimedEncounters;
    return fallback;
}

static void Near(float actual, float expected)
{
    assert(fabsf(actual - expected) < 0.00001f);
}

static void ClockTests(void)
{
    CtrDayNightClock clock = {0};
    const unsigned rates[] = {1, 6, 12, 24, 60, 120};

    for (unsigned index = 0; index < CTR_DAYNIGHT_SPEED_COUNT; ++index)
    {
        clock = (CtrDayNightClock){0};
        assert(CtrDayNight_Speed(index) == rates[index]);
        CtrDayNight_Advance(&clock, 100, 86399, index);
        CtrDayNight_Advance(&clock, 1100, 0, index);
        assert(clock.timeMs == (index == 0 ? 0 : (rates[index] - 1) * 1000));
    }
    assert(CtrDayNight_Speed(-1) == 1 && CtrDayNight_Speed(999) == 1);
    CtrDayNight_Advance(&clock, 2100, 0, 1);
    assert(clock.timeMs == 125000);
    CtrDayNight_Advance(&clock, 2200, 123, 0);
    assert(clock.timeMs == 123000);
    CtrDayNight_Advance(&clock, 2300, 123, 5);
    assert(clock.timeMs == 135000);
    CtrDayNight_Advance(&clock, 2300, 123, 5);
    assert(clock.timeMs == 135000);
    CtrDayNight_Advance(&clock, 1, 123, 5);
    assert(clock.timeMs == 135000);
    CtrDayNight_Advance(&clock, UINT64_MAX, 123, 5);
    assert(clock.timeMs < CTR_DAYNIGHT_DAY_MS);

    CtrDayNightClock slow = {0}, fast = {0};
    CtrDayNight_Advance(&slow, 0, 0, 4);
    CtrDayNight_Advance(&fast, 0, 0, 4);
    for (unsigned index = 1; index <= 1000; ++index)
        CtrDayNight_Advance(&fast, index, 0, 4);
    CtrDayNight_Advance(&slow, 1000, 0, 4);
    assert(slow.timeMs == fast.timeMs && slow.timeMs == 60000);
}

static void LightTests(void)
{
    const unsigned boundaries[] = {0, 210, 240, 570, 600, 990, 1020, 1170, 1200, 1440};
    CtrDayNightLight day = CtrDayNight_At(12 * 3600000), night = CtrDayNight_At(0);

    Near(day.rgb[0], 1.0f);
    Near(day.rgb[1], 1.0f);
    Near(day.rgb[2], 1.0f);
    Near(day.daylight, 1.0f);
    Near(night.daylight, 0.0f);
    assert(night.rgb[2] > night.rgb[0]);
    for (unsigned index = 0; index < sizeof(boundaries) / sizeof(boundaries[0]); ++index)
    {
        unsigned time = boundaries[index] * 60000;
        CtrDayNightLight before = CtrDayNight_At(time + CTR_DAYNIGHT_DAY_MS - 1);
        CtrDayNightLight after = CtrDayNight_At(time);

        for (unsigned channel = 0; channel < 3; ++channel)
            Near(before.rgb[channel], after.rgb[channel]);
        Near(before.daylight, after.daylight);
    }
    for (unsigned minute = 0; minute < 1440; ++minute)
    {
        CtrDayNightLight light = CtrDayNight_At(minute * 60000);

        for (unsigned channel = 0; channel < 3; ++channel)
            assert(light.rgb[channel] > 0 && light.rgb[channel] <= 1);
        assert(light.daylight >= 0 && light.daylight <= 1);
    }
}

static void RuntimeTests(void)
{
    unsigned seconds, rate;

    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 1);
    sEnabled = 1;
    sLocal = 0;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 0.55f);
    sOutdoor = false;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 1);
    sOutdoor = true;
    sSpeed = 5;
    sNow = 360000;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 1);
    sNow += 3600000;
    CtrDayNight_Resume();
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 1);
    sSpeed = 0;
    sNow += 1000;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 0.55f);
    sEnabled = 99;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 1);
    sEnabled = 1;
    sClockValid = false;
    sNow += 1000;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 1);
    sClockValid = true;
    sSpeed = -1;
    CtrDayNight_Update();
    Near(CtrDayNight_Get()->rgb[0], 0.55f);
    sEnabled = 0;
    CtrDayNight_Update();
    assert(!CtrDayNight_Time(&seconds, &rate));
    sShowClock = 1;
    sLocal = 9 * 3600;
    sSpeed = 5;
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == sLocal && rate == 120);
    Near(CtrDayNight_Get()->rgb[0], 1);
    sNow += 30000;
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == 10 * 3600);
    sShowClock = 0;
    sTimedEncounters = 1;
    sNow += 30000;
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == 11 * 3600);
    Near(CtrDayNight_Get()->rgb[0], 1);
    sNow += 3600000;
    CtrDayNight_Resume();
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == 11 * 3600);
    sClockValid = false;
    sNow += 1000;
    assert(!CtrDayNight_Time(&seconds, &rate));
    sNow += 30000;
    sClockValid = true;
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == 11 * 3600);
    sTimedEncounters = 0;
    sShowClock = 99;
    assert(!CtrDayNight_Time(&seconds, &rate));
    sShowClock = 1;
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == sLocal);
    sSpeed = 0;
    sLocal = 21 * 3600;
    sNow += 1000;
    assert(CtrDayNight_Time(&seconds, &rate));
    assert(seconds == sLocal && rate == 1);
}

int main(void)
{
    ClockTests();
    LightTests();
    RuntimeTests();
    puts("PASS day/night: rates, rollover, continuity, fast-forward independence, outdoors, resume, invalid settings");
    return 0;
}
