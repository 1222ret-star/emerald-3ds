# 한국어판

팬 한글패치 최종판(J-K) 롬에서 한글 폰트, 텍스트, 그림을 읽어 오는 한국어 빌드예요.
대사·메뉴·간이회화 문자열 약 12,600개(게임 텍스트의 약 97%)와 이름 표(포켓몬·기술·도구·특성·타입·
트레이너·트레이너 분류·도감 분류·장식품·나무열매)가 한국어로 바뀌고, 필드와 배틀 문장의 조사
(이/가, 을/를 등)도 처리해요.

이 패치는 일본판 롬에 적용하지만, 결과 롬은 pret의 영문판 소스로 빌드되어 있어서(헤더도 BPEE)
영문판 심볼을 그대로 대응시킬 수 있어요. 같은 팀의 1차 배포(영문판 기반 E-K 20210221)는
번역이 약 72%뿐이라 최종판으로 바꿨어요. 한글 코드·글꼴·조사 코드는 두 판이 같아요.

## 필요한 롬

| 롬 | SHA-1 |
|---|---|
| 일본판 원본 (Pocket Monsters - Emerald (Japan), BPEJ) | `d7cf8f156ba9c455d164e1ea780a6bf1945465c2` |
| 한글패치 롬 (일본판 + `20260613 포켓몬스터 에메랄드(J-K).xdelta`) | `17cd49e1af1184cd29355c674bedee7f5b72b055` |

롬, 패치, 번역문, 폰트는 저장소에 들어 있지 않아요. `tools/localize_korean.py`가
사용자의 롬에서 읽어 생성 트리에만 써요. 빌드와 빌더에는 패치를 적용한 롬을 넣어요.

## 빌드

```sh
python tools/bootstrap.py --make --korean-rom EmeraldJK.gba -j8
```

## 배포판 (빌더로 pak 만들기)

배포판은 다른 언어처럼 실행 파일과 recipe만 담고, 사용자가 빌더에 자기 한글패치 롬을 넣어
`emerald3ds.pak`을 만들어요. 빌더는 롬의 SHA-1로 한국어판(프로필 `BPEE-KO`)을 알아보고
`payload/ko/`의 실행 파일과 recipe를 골라요. 엔진도 pak의 롬 SHA-1이 한국어판인지 확인해요.

```sh
python tools/build_release.py --korean-rom EmeraldJK.gba ...   # payload/ko/ 추가
python -m emerald3ds_builder build --rom EmeraldJK.gba --output out  # 사용자 쪽
```

recipe는 `tools/gen_recipe.py`가 만들고, 한국어판 심볼 주소(`tools/locales/korean-symbols.s.gz`,
이름과 주소만)를 힌트로 써요.

## 한글 코드

- 2바이트: 리드 0x37~0x41 + 트레일 0x01~0xEF, KS X 1001 순서
  (`index = (리드-0x37)*239 + 트레일-1`, 음절 2,350자). 리드 0x41은 호환 자모예요.
- 트레일이 0xF0 이상이 되지 않아서 제어 코드(0xF7~0xFF)와 겹치지 않아요.
- 글리프는 코드당 64바이트(2bpp 8×8 타일 4개, Latin 글꼴과 같은 배치)이고,
  `graphics/fonts/hangul_{small,small_narrow,normal,narrow}.hanfont` 네 파일에 코드 0x3700~0x412F가 들어 있어요.

| 글꼴 | 한글 글꼴 파일 | 칸 |
|---|---|---|
| FONT_SMALL | hangul_small | 8×13 |
| FONT_SMALL_NARROW | hangul_small_narrow | 8×13 |
| FONT_SHORT (복사본 포함) | hangul_narrow | 8×14 |
| FONT_NORMAL | hangul_narrow | 8×15 |
| FONT_NARROW | hangul_narrow | 8×15 |

최종판(J-K)과 같은 배치예요. `hangul_normal`(11칸)은 3DS 아래 화면과 HD 배틀 HUD가 써요.

## 구현 위치

- `patches/pokeemerald/0057-korean-text.patch`: RenderText의 2바이트 읽기,
  GetStringWidth의 폭 계산, 글리프/폭 함수의 한글 분기 (`GAME_LANGUAGE == LANGUAGE_KOREAN`일 때만)
- `3ds_port/src/3ds_compat.c`: `Port_HangulGlyphs()`가 한글 글꼴 파일을 읽어요.
- `patches/pokeemerald/0058-korean-particles.patch`: 조사 플레이스홀더
  (은/는, 이/가, 을/를, (으)로, (이)다, 과/와, 아/야 — 필드 0x10~0x16, 배틀 0x35~0x3B)와
  호칭 0x0E/0x0F(형/누나, 오빠/언니). 바로 앞 글자의 받침으로 형태를 골라요.
  `include/hangul.h`는 KS X 1001의 받침 표예요.
- `patches/pokeemerald/0059-korean-name-lengths.patch`: 한글판 롬처럼 이름 칸을 늘려요
  (도구 18, 기술 16, 트레이너 분류 15, 도감 분류 16글자).
- `patches/pokeemerald/0060-korean-naming-screen.patch`: 한글판 롬과 같은 10열 키보드
  (한글 두벌식, 숫자·영문)와 입력 중 자모 조합(겹모음·겹받침, 받침 넘김, 백스페이스로 한 자모씩 지우기).
  `include/hangul_ks.h`는 KS X 1001 음절 2350자의 유니코드 순서 표예요.
- `patches/pokeemerald/0061-korean-battle-yesno.patch`: 배틀의 예/아니오 상자를 왼쪽으로
  두 칸 넓혀 "아니오"가 잘리지 않게 해요.
- `3ds_port/src/3ds_bottom_ui.c`, `3ds_battle_hud.c`: 아래 화면과 HD 배틀 HUD도 한글을 그려요.
- `3ds_port/include/3ds_locale.h`: `CTR_TEXT`에 한국어 인자(5번째)를 더했어요. 포트 자체 메뉴
  문구 68개(설정·추가 기능·치트 등)의 한국어 번역이 `3ds_extras.c`, `3ds_bottom_ui.c`에 있고,
  `3ds_locale_text.h`가 UTF-8 한글을 게임의 2바이트 코드로 바꿔요.
- `patches/pokeemerald/0062-korean-title-version-banner.patch`: 한글판 타이틀의 "에메랄드" 배너는
  16색이 아니라 144색 팔레트를 써요.
- `tools/localize_korean.py`: 롬 확인, 글꼴 추출, 매니페스트 적용(문자열과 그래픽), 포켓몬 이름, `GAME_LANGUAGE`
- `tools/locales/korean.json.gz`: 문자열 정의 위치(소스 파일·오프셋)와 롬 오프셋·크기.
  텍스트는 들어 있지 않아요. 원본 영문판과 한글판을 심볼 단위로 대응시켜 만들어요
  (개발용 도구: 두 롬의 복사 지도, 포인터·표·이벤트 스크립트 구조 맞추기).
  `graphics`에는 한글판이 바꾼 그림(타이틀 로고와 팔레트, 메뉴·요약 화면·박스 타일 등 68개)의 롬 위치가 들어 있어요.

## 아직 안 된 것

- 위치를 찾지 못한 문자열 약 440개(약 2.4%, 주로 C 코드의 문자열과 일부 맵 대사)는 영어로 나와요.
- 간이회화 가나다 정렬과 입력 화면, 도감 가나다 정렬
- recipe에 남은 영문판 원문 줄이기(공개 배포 전)
