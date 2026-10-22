# 한국어판

팬 한글패치 최종판(J-K) 롬에서 한글 폰트, 텍스트, 그림을 읽어 오는 한국어 빌드예요.
대사·메뉴·간이회화 문자열(게임 텍스트의 약 98.6%)와 이름 표(포켓몬·기술·도구·특성·타입·
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
- `patches/pokeemerald/0063-korean-port-texts.patch`: 포트가 더한 게임 문구(학습장치 경험치, 개체값/노력치,
  분류, 필드 비전기술, 벌레회피스프레이, 로컬 무선)의 한국어
- `0064-korean-dex-texts.patch`: 도감 크기 비교 문구, 미터법 단위, 설명 위치
- `0065-korean-summary-effect-window.patch`: 분류가 있는 요약 화면 기술 효과 창을 한글판 타일로 만들어요.
- `0066-korean-wide-dialogue-font.patch`: 위 화면 대화창(높이 4, 폭 26 이상, 14행 아래)만 11칸 `hangul_normal`
- `0067-korean-battle-buffer-particles.patch`: 배틀 버퍼(B_TXT_BUFF1~3) 안의 조사 코드. 없으면 라이벌 2차전에서 멈춰요.
- `0068-korean-ui-layout.patch`: 한글은 왼쪽 여백이 없어서 가방·상점 설명, 파티 메뉴, 용돈, 경험치,
  기술 위력/명중·어필/방해 라벨(8픽셀 안쪽)을 상자 안으로 옮겨요.
- `0069-korean-easy-chat-keyboard.patch`: 간이회화 가나다 자판(3줄)
- `0070-korean-summary-pp.patch`: 기술 PP를 40픽셀 폭에 맞춰 PP 상자 안에 둬요.

## 매니페스트 만들기 (개발용)

`tools/korean/`의 도구로 `tools/locales/korean.json.gz`와 `korean-symbols.s.gz`를 다시 만들어요.
롬은 읽기만 하고, 결과에는 위치·크기·이름만 들어가요. MSYS2 MINGW64(devkitARM 환경)에서 실행해요.

필요한 것: 영문판 원본 롬(`Pokemon Emerald (USA).gba`, BPEE), 한글패치 롬(`EmeraldJK.gba`),
pret `symbols` 브랜치의 `pokeemerald.sym`(영문판 롬의 심볼 주소).

1. 복사 지도: 한글판 롬의 각 바이트 구간이 영문판 롬 어디에서 왔는지 적어요.
   ```sh
   python tools/korean/romdiff.py USA.gba EmeraldJK.gba work/usa_to_jk_map.json
   ```
2. 심볼 대응: 영문판 심볼마다 한글판 주소를 찾아요(포인터 투표, 표·스크립트·BL 짝 맞추기).
   스크립트 명령 배치를 읽으려고 `build/upstream`(bootstrap한 트리)이 있어야 해요.
   자동으로 못 찾거나 잘못 찾는 심볼은 `tools/korean/overrides_jk.json`에 주소를 직접 적어요.
   ```sh
   python tools/korean/relocmap.py pokeemerald.sym work/usa_to_jk_map.json USA.gba EmeraldJK.gba work/reloc tools/korean/overrides_jk.json
   ```
   `RELOC_TRACE=심볼이름`을 주면 그 심볼을 어떻게 정했는지 출력해요.
3. recipe 힌트용 심볼:
   ```sh
   python tools/korean/gen_korean_symbols.py work/reloc/symbols_kor.tsv tools/locales/korean-symbols.s.gz
   ```
4. 남은 문자열: 2단계가 못 찾은 문자열은 그것을 가리키는 포인터(스크립트의 `msgbox`, 표의 항목)를 따라가
   한글판 주소를 찾아요. 구조체·목록을 여러 단계 거쳐도 돼요(포켓내비 지명). 결과는 `tools/korean/texts_jk.json`에
   쌓이고, 표 구조가 바뀐 항목(칼슘 설명: `gItems` 한 칸이 44→48바이트)은 손으로 적어 두었어요.
   ```sh
   python tools/korean/follow_pointers.py build/upstream work/reloc/symbols_kor.tsv work/usa_to_jk_map.json USA.gba EmeraldJK.gba tools/korean/texts_jk.json 이름...
   ```
5. 매니페스트: 패치만 적용한 트리(한국어 적용 전)에서 문자열·이름 표·창 배치·그림 위치를 롬과 맞춰요.
   소스 위치를 담으므로 pret 소스를 바꾸는 패치가 달라지면 다시 만들어야 해요.
   ```sh
   python tools/bootstrap.py
   make -C build/upstream generated
   python tools/korean/gen_korean_manifest.py build/upstream work/reloc/symbols_kor.tsv USA.gba EmeraldJK.gba tools/locales/korean.json.gz work/manifest_report.tsv
   ```
   창 배치는 영문판 pret와 같은 항목만 한글판 것을 쓰고, `WINDOW_KEEP`에 적은 항목은 영문판 그대로 둬요.
   그래도 위치가 없고 아무 데서도 쓰지 않는 대사(루비·사파이어의 잔재)는 비워요. 영어 원문이 recipe에 들어가지 않게요.
6. 빌드: `python tools/bootstrap.py --make --korean-rom EmeraldJK.gba -j8`

그 밖의 도구: `hangul_encode.py`(한국어 문장을 게임 코드로, 패치 0063의 문구용), `kortext.py`(한글판 텍스트 읽기),
`extract_hangul_font.py`(글꼴을 PNG로), `vcdiff.py`(xdelta 패치 적용·분석), `script_cmds.py`(이벤트 스크립트 해석).

## 원본 3DS 포팅판이 업데이트될 때

1. upstream을 병합하고 `python tools/bootstrap.py`로 패치가 모두 적용되는지 봐요.
   0057~0070이 실패하면 바뀐 소스에 맞춰 다시 만들어요(문맥 줄이 앞 패치에 걸려 있으면 앞 패치가 바뀔 때 같이 고쳐요).
2. pret 기준 커밋이 바뀌었거나 문자열이 있는 소스가 바뀌었으면 5단계(매니페스트)를 다시 해요.
   기준 롬이 그대로면 1~4단계는 다시 할 필요 없어요.
3. `manifest_report.tsv`에서 새로 영어로 남는 문자열과 창 배치를 확인해요. 쓰는 문자열이면 4단계로 찾아요. 포트가 새로 만든 화면의 창은
   한글판에 없으니 상자를 벗어나면 0068처럼 좌표를 고쳐요.
4. 포트 자체 문구: 새 `CTR_TEXT`의 5번째(한국어) 인자와, 패치로 더한 게임 문구(0063)를 채워요.
5. upstream이 아래 화면 UI(도감·요약·파티)를 새로 만들면 0064·0065·0068·0070에서 해당 부분이 필요 없는지 봐요.
6. 배포판을 만들어 `gen_recipe.py`가 통과하는지(게임 문자열 한도 4096바이트), `tools/release_audit.py --repo . --strict`가
   깨끗한지 확인해요. recipe의 literal에 영어 문장이 없어야 해요(`--report`의 파일별 크기로 찾아요).
7. 에뮬레이터 확인: 타이틀, 이름 정하기, 오박사 대사, 가방·상점, 요약 화면(능력치·기술), 도감 설명·크기 비교,
   라이벌 2차전, 진화 문구 조사, 간이회화 가나다 자판, 포켓내비.

## 아직 안 된 것

- 위치를 찾지 못한 문자열 일부(주로 C 코드의 짧은 문자열, 연결 기능의 일본어판 잔재)는 영어로 나와요.
- 무로마을 체육관 대화창이 잘려요(포트의 와이드 화면 창 처리로 보여요).
- 도감 가나다 정렬
