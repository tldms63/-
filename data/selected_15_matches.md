# 선별된 15개 경기 — 영상 클립 검색용 정리 (v2)

`olympics.db`에 새로 적재된 15건입니다. 이전 버전과 달리 **실제 선수명·핵심 세부종목명
키워드**(김광선, 박시헌, 전병관, 박종훈, 도마, 사브르 등)와 **결승/금메달/시상식** 가산점
기준으로 `collector.py`가 전체 공공데이터(약 9,752건)를 훑어 자동 선별한 결과입니다.

각 항목의 `video_url`은 DB에 `/static/videos/{id}.mp4`로 미리 설정되어 있습니다 —
아래 추천 키워드로 유튜브에서 영상을 찾아 그 구간을 `download_clip.py`로 잘라
해당 파일명으로 저장하면 됩니다.

> ID는 `olympics.db`의 실제 `id` 컬럼 값(1~15)입니다.

---

## 1. (ID 1) 복싱 — 라이트 미들급 -71KG 시상식
- **경기 제목**: 복싱 라이트 미들급 -71KG (9) - 시상식
- **경기 일자**: 1988-10-02 (원본 API에는 "1998-10-02"로 오기재되어 있어 1988로 보정함)
- **참가국**: 대한민국, 미국, 영국, 캐나다
- **상세 설명**: 대한민국 박시헌(Park, Si-Hun) 금메달, 미국 Jones, R.(로이 존스 주니어) 은메달, 영국 Woodhall / 캐나다 Downey 공동 동메달.
- **참고**: 이 경기는 로이 존스 주니어가 일방적으로 압도했음에도 박시헌이 판정승한 것으로 유명한 **1988 서울올림픽 최대 판정 논란** 경기입니다.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics boxing light middleweight final Roy Jones Park Si-hun`

## 2. (ID 2) 복싱 — 플라이급 -51KG 시상식
- **경기 제목**: 복싱 플라이급 -51KG (13) - 시상식
- **경기 일자**: 1988-10-02
- **참가국**: 대한민국, 동독, 멕시코, 소련
- **상세 설명**: 대한민국 김광선(Kim, Kwang-Sun) 금메달, 동독 Tews, A. 은메달, 멕시코 Gonzalez / 소련 Skriabian 공동 동메달.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics boxing flyweight gold medal Kim Kwang-sun`

## 3. (ID 3) 복싱 — 라이트 웰터급 -63.5KG 시상식
- **경기 제목**: 복싱 라이트 웰터급 -63.5KG (11) - 시상식
- **경기 일자**: 1988-10-02
- **참가국**: 소련, 호주, 스웨덴, 서독
- **상세 설명**: 소련 Janovski, V. 금메달, 호주 Cheny, G. 은메달, 스웨덴/서독 공동 동메달.
- **⚠️ 데이터 품질 참고**: 원본 요약문에 `"Myr버뮤다g, L선수"`처럼 한글이 섞여 깨진 표기가 있습니다. 저희가 만든 것이 아니라 **공공데이터 원문 자체의 오류**이니, 실제 선수명(스웨덴 대표)은 별도로 확인 후 사용하세요.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics boxing light welterweight final Vyacheslav Janovski`

## 4. (ID 4) 체조 — 남자 개인 종목별 결승, 박종훈 1라운드
- **경기 제목**: 체조 남자 개인 종목별 결승 (4) - 대한민국의 박종훈(Park, Jong-Hoon) 1라운드
- **경기 일자**: 1988-09-24
- **참가국**: 대한민국
- **상세 설명**: 박종훈 선수 9.950점, 주요장면 리플레이.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics gymnastics Park Jong-hoon apparatus final`

## 5. (ID 5) 체조 — 남자 개인 종목별 결승, 박종훈 2라운드 (10.000 만점)
- **경기 제목**: 체조 남자 개인 종목별 결승 (4) - 대한민국의 박종훈(Park, Jong-Hoon) 2라운드
- **경기 일자**: 1988-09-24
- **참가국**: 대한민국
- **상세 설명**: 박종훈 선수 **10.000점 만점**, 주요장면 리플레이. (ID 4의 1라운드 9.950점과 이어지는 같은 결선 종목의 2라운드)
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics gymnastics Park Jong-hoon perfect 10 vault final`

## 6. (ID 6) 체조 — 남자 개인 종목별 결승 (4) 시상식 — 박종훈 동메달
- **경기 제목**: 체조 남자 개인 종목별 결승 (4) - 시상식
- **경기 일자**: 1988-09-24
- **참가국**: 중화인민공화국, 동독, 대한민국
- **상세 설명**: 중공 Lou 선수 금메달, 동독 Kroll 선수 은메달, **대한민국 박종훈(Park) 선수 동메달** 획득. ID 4·5의 두 라운드 연기로 획득한 메달의 시상식으로, 3건이 하나의 이야기로 이어집니다.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics gymnastics vault final medal ceremony Park Jong-hoon bronze`

## 7. (ID 7) 태권도 — 남자 라이트급(64-70KG) 시상식
- **경기 제목**: 태권도 남자 라이트급 64KG-70KG(2) - 시상식
- **경기 일자**: 1988-09-19
- **참가국**: 대한민국, 스페인, 미국, 멕시코
- **상세 설명**: 대한민국 Park 선수 금메달. (1988년 태권도는 시범종목)
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics taekwondo demonstration lightweight medal ceremony`

## 8. (ID 8) 태권도 — 남자 미들급(76-83KG) 시상식
- **경기 제목**: 태권도 남자 미들급 76KG-83KG(3) - 시상식
- **경기 일자**: 1988-09-18
- **참가국**: 대한민국, 이집트, 서독, 터키
- **상세 설명**: 대한민국 Lee 선수 금메달.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics taekwondo demonstration middleweight medal ceremony`

## 9. (ID 9) 태권도 — 남자 밴텀급(54-58KG) 시상식
- **경기 제목**: 태권도 남자 밴텀 54-58KG(2) - 시상식
- **경기 일자**: 1988-09-18
- **참가국**: 대한민국, 스페인, 미국, 이란
- **상세 설명**: 대한민국 Ji 선수 금메달.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics taekwondo demonstration bantamweight medal ceremony`

## 10. (ID 10) 펜싱 — 남자 사브르 개인전 시상식
- **경기 제목**: 펜싱 남자 사브르 개인전 (3) - 시상식
- **경기 일자**: 1988-09-23
- **참가국**: 프랑스, 폴란드, 이탈리아
- **상세 설명**: 프랑스 **Jean-François Lamour** 금메달(2연패), 폴란드 **Janusz Olech** 은메달, 이탈리아 Scalzo Giovanni 동메달.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics fencing sabre individual medal ceremony Jean-Francois Lamour`

## 11. (ID 11) 펜싱 — 남자 사브르 단체전 시상식
- **경기 제목**: 펜싱 남자 사브르 단체전 (3) - 시상식
- **경기 일자**: 1988-09-29
- **참가국**: 헝가리, 소련, 이탈리아
- **상세 설명**: 헝가리팀 금메달, 소련팀 은메달, 이탈리아팀 동메달.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics team sabre fencing medal ceremony Hungary`

## 12. (ID 12) 펜싱 — 남자 사브르 개인전 (1) — Delrieu vs Pogosov
- **경기 제목**: 펜싱 남자 사브르 개인전 (1) - Philippe Delrieu(프랑스) : Georgy Pogosov(소련)
- **경기 일자**: 1988-09-23
- **참가국**: 프랑스, 소련
- **상세 설명**: 프랑스 Philippe Delrieu 선수가 12-11로 승리.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics fencing sabre Philippe Delrieu Georgy Pogosov`

## 13. (ID 13) 역도 — 52KG급 시상식
- **경기 제목**: 역도 52KG급 (4) - 시상식
- **경기 일자**: 1988-09-18
- **참가국**: 불가리아, 대한민국, 중화인민공화국
- **상세 설명**: 불가리아 Marinov, S. 금메달, 대한민국 **전병관(Chun, Byung Kwan)** 은메달, 중공 He, Z. 동메달.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics weightlifting 52kg medal ceremony Chun Byung-kwan`

## 14. (ID 14) 역도 — 52KG급, 전병관 105.0KG 인상 시도
- **경기 제목**: 역도 52KG급 (3) - 105.0KG 시도
- **경기 일자**: 1988-09-18
- **참가국**: 일본, 대한민국
- **상세 설명**: 대한민국 전병관(Chun, Byung Kwan) 선수 105.0KG 시도 성공.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics weightlifting 52kg Chun Byung-kwan snatch`

## 15. (ID 15) 역도 — 60KG급 시상식 (나임 술레이마놀루 금메달)
- **경기 제목**: 역도 60KG급 (4) - 시상식
- **경기 일자**: 1988-09-20
- **참가국**: 터키, 불가리아, 중화인민공화국
- **상세 설명**: 터키의 **Naim Süleymanoğlu(나임 술레이마놀루)** 선수가 금메달, 불가리아 Topourov 선수 은메달, 중공 Ye, H. 선수 동메달 획득. 술레이마놀루는 "포켓 헤라클레스"로 불리는 역사상 가장 유명한 역도 선수 중 한 명이라 유튜브 자료가 풍부합니다.
- **추천 유튜브 검색 키워드**: `1988 Seoul Olympics weightlifting 60kg Naim Suleymanoglu gold medal`

---

## 검색 팁
- 시상식(medal ceremony) 클립은 "medal ceremony" 영문 키워드가 한글보다 검색 적중률이 높은 경우가 많습니다.
- 국가명은 당시 국호 기준입니다 (예: "서독" = West Germany, "동독" = East Germany, "소련" = Soviet Union/USSR, "중공" = People's Republic of China).
- ID 3의 "Myr버뮤다g" 같은 원본 데이터 오류는 임의로 고치지 않고 그대로 옮겨 적었습니다 — 실제 사용 전 확인이 필요합니다.
- 체조 4·5·6번은 박종훈 선수의 1라운드(9.950)→2라운드(10.000 만점)→시상식(동메달)으로 이어지는 하나의 이야기이니, 유튜브 클립도 가능하면 같은 원본 영상에서 세 구간을 나눠 잘라 쓰는 것을 추천합니다.
