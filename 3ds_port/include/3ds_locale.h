#ifndef CTR_LOCALE_H
#define CTR_LOCALE_H

#include "constants/global.h"

/* Native UI literals are converted from UTF-8 into the game font encoding. */
#if GAME_LANGUAGE == LANGUAGE_SPANISH
#define CTR_TEXT(english, spanish, french, italian, korean) (spanish)
#elif GAME_LANGUAGE == LANGUAGE_FRENCH
#define CTR_TEXT(english, spanish, french, italian, korean) (french)
#elif GAME_LANGUAGE == LANGUAGE_ITALIAN
#define CTR_TEXT(english, spanish, french, italian, korean) (italian)
#elif defined(LANGUAGE_KOREAN) && GAME_LANGUAGE == LANGUAGE_KOREAN
#define CTR_TEXT(english, spanish, french, italian, korean) (korean)
#else
#define CTR_TEXT(english, spanish, french, italian, korean) (english)
#endif

#endif
