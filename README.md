# treasurytotal

공개 데이터(미 연준·뉴욕 연은·BEA·BLS·미 재무부·ECB·BOJ·한국은행 ECOS 등)로 만드는 거시·금리 지표 대시보드.

- 화면: `docs/` (GitHub Pages, `main` 브랜치 `/docs`)
- 수집: `.github/workflows/` (GitHub Actions 예약 실행)
- 수집 결과와 실패 내역: `docs/_status.json`

API 키(`BEA_API_KEY`, `ECOS_API_KEY`, 선택 `BLS_API_KEY`)는 저장소 Secrets에만 둔다.
