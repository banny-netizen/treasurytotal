# treasurytotal

공개 자료로 보는 거시·금리 지표 대시보드. 각국 중앙은행과 정부 통계기관이 공개한 자료를 GitHub Actions가 정해진 시각에 받아 `docs/data/`에 쌓고, GitHub Pages(`main` 브랜치 `/docs`)가 화면을 보여 준다.

## 운영 정책

이 저장소는 공개 저장소다. 아래는 예외 없이 지킨다.

1. 공용 API와 공개 웹 페이지에서 받은 공개 자료만 다룬다.
2. 내부 자료(잔고, 거래 내역, 한도, 내부 문서)는 일절 올리지 않는다.
3. 수집 대상은 `config/allowlist.json`에 등록된 주소로 한정한다.
4. API 키는 저장소 Secrets에만 둔다. 파일·커밋·로그에 적지 않는다.
5. 제3자가 만든 보고서 본문은 저장하지 않는다. 필요한 숫자만 읽는다.

정책은 코드로도 막아 둔다.

- 수집 스크립트는 허용 목록 밖 주소를 호출하면 그 자리에서 멈춘다.
- 상대 서버가 목록 밖 주소로 넘기려 하거나(리다이렉트) 호출을 막으면(403·429) 따라가거나 반복해 넘으려 하지 않고 그 출처만 실패로 처리한다.
- PR과 수집 실행 때마다 `scripts/check_policy.py`가 돈다. 허용 목록 밖 주소, 등록되지 않은 데이터 파일, 엑셀·PDF 같은 수동 자료, API 키로 보이는 값이 있으면 실패한다.

## 메뉴와 출처

| 메뉴 | 내용 | 출처 |
|---|---|---|
| 통화별 지표금리 | EFFR·SOFR·목표범위, €STR·ECB 수신금리, TONA, 콜금리·KOFR | 뉴욕 연은, ECB, 일본은행, 한국은행 ECOS |
| 자금조달 여건 | SOFR 75백분위 − IORB, KOFR − 콜금리 | 뉴욕 연은, FRED, ECOS |
| 통화정책회의 일정·점도표 | 연준·ECB·일본은행·한국은행 회의 일정과 결과, 연준 SEP 점 분포 | 각 중앙은행 일정 페이지, FRED, ECB, ECOS, 연준 SEP 표 |
| 인플레이션 확산 지표 | PCE 16개 품목군 중 상승률이 기준을 넘는 품목군의 지출 비중 | BEA (DBnomics 경유) |
| CPI·PCE 발표 수치 | 회차별 전월비·전년비, PCE 항목별 가중치·기여도 | BLS (FRED 경유), BEA (DBnomics 경유) |
| 물가·통화 / 고용 / 경기 | CPI, PCE 물가, M2, 연준 총자산, 실업률, 고용, 임금, GDP, 산업생산, 소매판매, 연은 활동 지수 | FRED (원자료 BLS·BEA·연준·Census) |
| 자동차대출 연체율 | 90일 이상 연체율, 잔액 | 뉴욕 연은 가계신용 보고서 |
| 재정적자·리프라이싱 | 기초적자(GDP 대비), 1년 내 리프라이싱 비중 | FRED, 미 재무부 Fiscal Data |
| 금리 vs 성장률 | 10년물 금리와 명목 GDP 3년 연평균 성장률, 만기별 금리 | FRED, 미 재무부 |
| 연준 모델 | S&P 500 선행 이익수익률 vs 10년물 | FactSet Earnings Insight(선행 PER 수치), FRED |
| 수집 현황 | 출처별 수집 결과와 경고 | `docs/data/_status.json` |

알아 둘 점.

- 결과(인상·동결·인하)는 성명서를 읽지 않고 공식 금리 시계열의 변화로 판정한다. 일본은행은 회의 전후 콜금리 수준 변화로 추정한 값이다.
- ISM PMI, 미시간대 소비자심리처럼 재배포가 제한된 민간 지표는 싣지 않는다.
- 순이자는 FY2014까지 FRED `FYOINT`, FY2015부터 재무부 월간 재정보고서의 Net Interest를 쓴다.
- 확산 지표는 16개 품목군 기준이라 세부 품목 기준 지표보다 거칠다.
- 한국 금리는 `ECOS_API_KEY`가 없으면 공용 sample 키로 최근 10건만 받는다.

## 구조

```
config/allowlist.json          수집 허용 주소, 산출 파일 목록
scripts/common.py              허용 목록 검사, 호출·파싱 공용 함수
scripts/collect.py             수집 진입점 (출처별로 따로 받아 쓴다)
scripts/src_<이름>.py          출처별 수집: rates, cbank, macro, infl, delinq, fiscal, growth, fedmodel
scripts/fred.py, pdftext.py    FRED 내려받기, PDF 글자 추출
scripts/check_policy.py        정책 점검
scripts/probe.py               새 출처 응답 확인 (probe/ 브랜치에서만 실행)
tests/                         파싱·계산 단위 테스트 (실제 응답에서 옮긴 자료 사용)
docs/index.html, app.js, chart.js, app.css   대시보드 화면 (외부 스크립트·글꼴 없음)
docs/data/<이름>.json          수집 결과 (자동 생성, 손으로 고치지 않는다)
docs/data/_status.json         출처별 수집 결과
trigger/run.txt                첫 줄을 고쳐 올리면 그 묶음을 바로 수집한다
```

## 수집 일정 (한국 시간)

| 시각 | 묶음 | 내용 |
|---|---|---|
| 월~토 13:37 | `daily` | 금리, 회의 일정·점도표, 경제지표, 물가 발표·확산, 연체율, 재정·리프라이싱, 성장률 |
| 월 13:53 | `weekly` | 연준 모델 |

- 한 출처가 실패해도 나머지는 진행하고, 실패한 출처는 직전 수집분을 남긴다.
- 내용이 바뀐 파일만 다시 쓴다. 월·분기 자료도 매일 점검하고 바뀐 때에만 갱신한다.
- 수동 실행: Actions 화면에서 `collect`를 직접 실행하거나, `trigger/run.txt` 첫 줄(`all`, `daily`, `weekly` 또는 출처 이름)을 고쳐 `main`에 올린다.

## 처음 설정

1. Settings → Pages → Source를 `main` 브랜치 `/docs`로 지정한다.
2. Settings → Secrets and variables → Actions에 `ECOS_API_KEY`(한국은행 ECOS 인증키)를 등록한다. 없어도 돌지만 한국 금리 이력이 쌓이지 않는다.

## 로컬 실행

```
python3 scripts/check_policy.py
python3 -m unittest discover -s tests
python3 scripts/collect.py daily
python3 -m http.server -d docs 8000
```

외부 라이브러리는 쓰지 않는다. 파이썬 표준 라이브러리만 쓴다.
