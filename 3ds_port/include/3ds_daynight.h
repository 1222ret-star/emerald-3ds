#ifndef CTR_DAYNIGHT_H
#define CTR_DAYNIGHT_H

#include <stdbool.h>
#include <stdint.h>

#define CTR_DAYNIGHT_SPEED_COUNT 6
#define CTR_DAYNIGHT_DAY_MS 86400000u

typedef struct
{
    uint64_t lastMs;
    uint32_t timeMs;
    bool ready;
} CtrDayNightClock;

typedef struct
{
    float rgb[3];
    float daylight;
} CtrDayNightLight;

unsigned CtrDayNight_Speed(int index);
void CtrDayNight_Advance(CtrDayNightClock *clock, uint64_t nowMs, unsigned localSeconds, int speed);
CtrDayNightLight CtrDayNight_At(unsigned timeMs);
void CtrDayNight_Update(void);
void CtrDayNight_Resume(void);
const CtrDayNightLight *CtrDayNight_Get(void);
bool CtrDayNight_Time(unsigned *seconds, unsigned *rate);

#endif
