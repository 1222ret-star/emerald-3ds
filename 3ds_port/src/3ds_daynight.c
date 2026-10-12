#include "3ds_daynight.h"
#include "3ds_platform.h"

static const unsigned sSpeeds[CTR_DAYNIGHT_SPEED_COUNT] = {1, 6, 12, 24, 60, 120};
static CtrDayNightClock sClock;
static CtrDayNightLight sLight = {{1.0f, 1.0f, 1.0f}, 1.0f};
static unsigned sLocalSeconds;
static uint64_t sSampleMs;
static bool sSampled, sEnabled, sResume, sValid;

unsigned CtrDayNight_Speed(int index)
{
    return index >= 0 && index < CTR_DAYNIGHT_SPEED_COUNT ? sSpeeds[index] : 1;
}

void CtrDayNight_Advance(CtrDayNightClock *clock, uint64_t nowMs, unsigned localSeconds, int speed)
{
    unsigned rate = CtrDayNight_Speed(speed);

    if (!clock->ready || rate == 1)
        clock->timeMs = (localSeconds % 86400u) * 1000u;
    else if (nowMs >= clock->lastMs)
    {
        uint64_t elapsed = (nowMs - clock->lastMs) % CTR_DAYNIGHT_DAY_MS;

        clock->timeMs = (uint32_t)((clock->timeMs + elapsed * rate) % CTR_DAYNIGHT_DAY_MS);
    }
    clock->lastMs = nowMs;
    clock->ready = true;
}

CtrDayNightLight CtrDayNight_At(unsigned timeMs)
{
    static const struct
    {
        unsigned minute;
        CtrDayNightLight light;
    } keys[] = {
        {0,    {{0.55f, 0.62f, 0.82f}, 0.0f}},
        {210,  {{0.55f, 0.62f, 0.82f}, 0.0f}},
        {240,  {{0.96f, 0.94f, 0.88f}, 0.75f}},
        {570,  {{0.96f, 0.94f, 0.88f}, 0.75f}},
        {600,  {{1.00f, 1.00f, 1.00f}, 1.0f}},
        {990,  {{1.00f, 1.00f, 1.00f}, 1.0f}},
        {1020, {{1.00f, 0.80f, 0.65f}, 0.35f}},
        {1170, {{1.00f, 0.80f, 0.65f}, 0.35f}},
        {1200, {{0.55f, 0.62f, 0.82f}, 0.0f}},
        {1440, {{0.55f, 0.62f, 0.82f}, 0.0f}},
    };
    unsigned current = timeMs % CTR_DAYNIGHT_DAY_MS;

    for (unsigned index = 1; index < sizeof(keys) / sizeof(keys[0]); ++index)
        if (current < keys[index].minute * 60000u)
        {
            CtrDayNightLight light = keys[index - 1].light;
            float blend = (float)(current - keys[index - 1].minute * 60000u)
                        / ((keys[index].minute - keys[index - 1].minute) * 60000u);

            for (unsigned channel = 0; channel < 3; ++channel)
                light.rgb[channel] += (keys[index].light.rgb[channel] - light.rgb[channel]) * blend;
            light.daylight += (keys[index].light.daylight - light.daylight) * blend;
            return light;
        }
    return keys[0].light;
}

void CtrDayNight_Resume(void)
{
    sResume = true;
    sSampled = false;
}

void CtrDayNight_Update(void)
{
    uint64_t now = CtrPlatform_Milliseconds();
    bool enabled = CtrSettings_GetInt("day_night", 0) == 1;
    bool active = enabled || CtrSettings_GetInt("timed_encounters", 0) == 1
                          || CtrSettings_GetInt("show_clock", 0) == 1;
    int speed = CtrSettings_GetInt("clock_speed", 0);

    sLight = (CtrDayNightLight){{1.0f, 1.0f, 1.0f}, 1.0f};
    sValid = false;
    if (!active)
    {
        sEnabled = false;
        sClock.ready = false;
        return;
    }
    if (!sSampled || !sEnabled || now < sSampleMs || now - sSampleMs >= 1000)
    {
        if (!CtrGame_LocalTimeSeconds(&sLocalSeconds))
        {
            sSampled = false;
            sResume = true;
            return;
        }
        sSampleMs = now;
        sSampled = true;
    }
    if (sResume)
        sClock.lastMs = now;
    sResume = false;
    CtrDayNight_Advance(&sClock, now, sLocalSeconds, speed);
    sEnabled = true;
    sValid = true;
    if (enabled && CtrGame_IsOutdoor())
        sLight = CtrDayNight_At(sClock.timeMs);
}

bool CtrDayNight_Time(unsigned *seconds, unsigned *rate)
{
    CtrDayNight_Update();
    if (!sValid)
        return false;
    *seconds = sClock.timeMs / 1000u;
    *rate = CtrDayNight_Speed(CtrSettings_GetInt("clock_speed", 0));
    return true;
}

const CtrDayNightLight *CtrDayNight_Get(void)
{
    return &sLight;
}
