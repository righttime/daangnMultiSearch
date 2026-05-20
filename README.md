# 당근검색 — 다중 동네 통합 검색

> 여러 동네를 한번에 검색해서 숨겨진 보물을 찾아보세요

당근마켓에서 여러 동네(최대 495개)를 동시에 검색하고, 실시간으로 결과를 확인하며 최신순으로 정렬하는 서비스입니다.

## 주요 기능

- **다중 동네 동시 검색** — 원하는 만큼의 동네를 자유롭게 선택
- **실시간 스트리밍** — SSE로 동네별 결과가 도착하는 즉시 화면에 표시
- **최신순 정렬** — 등록일시 기준 내림차순, 새 글이 앞에
- **검색 중지** — 언제든 검색 중지 가능 (버튼 또는 `Esc` 키)
- **검색 기록** — 이전 검색어를 다시 사용 가능
- **빠른 선택** — 안산, 수원, 구로 등 지역 그룹 단위 선택

## 시작하기

### Docker (추천)

```bash
docker-compose up -d
# http://localhost:9095 에서 접근
```

### 로컬 개발

```bash
pip install fastapi uvicorn requests beautifulsoup4
python main.py
# http://localhost:9095 에서 접근
```

## API

| Endpoint | 설명 |
|----------|------|
| `GET /` | 메인 페이지 |
| `GET /regions.json` | 전체 동네 목록 |
| `GET /history` | 검색 기록 |
| `DELETE /history` | 검색 기록 삭제 |
| `GET /search?query=&regions=` | 동시 검색 (JSON 응답) |
| `GET /search/stream?query=&idx=` | SSE 실시간 스트리밍 |
| `GET /explore?lat=&lng=` | 좌표 기반 동네 탐색 |

### Search Examples

```bash
# JSON 응답
curl "http://localhost:9095/search?query=맥북&regions=안산동-1514,수원-1000"

# SSE 스트리밍 (idx는 regions.json 순번)
curl -N "http://localhost:9095/search/stream?query=자전거&idx=0,1,2"
```

## 기술 스택

- **Backend** — FastAPI + Python
- **Frontend** — Vanilla JS, SSE (Server-Sent Events)
- **Parser** — BeautifulSoup (당근마켓 HTML 스크래핑)
- **Container** — Docker + docker-compose

## 디렉토리 구조

```
.
├── main.py              # FastAPI 서버
├── regions.json         # 동네 ID/이름 매핑 (495개)
├── templates/
│   └── index.html      # 메인 UI
├── data/
│   └── history.json    # 검색 기록 (자동 생성)
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HISTORY_FILE` | `/app/data/history.json` | 검색 기록 저장 경로 |

## 유의사항

- 당근마켓 웹 스크래핑 방식 사용 — 사이트 구조 변경 시 수정 필요
- 동네별 요청 사이에 0.3초 딜레이 (서버 보호)
- 검색 기록은 최대 100개까지 저장
