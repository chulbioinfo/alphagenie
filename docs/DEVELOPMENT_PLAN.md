# GitHub 개발 계획 — v0.21 Local / v0.20 engine

작성: 2026-09-10 · 패키지 버전: 0.21.0-local.1

## 목표와 범위

공개 서버와 별개로 설치 가능한 개인용 AlphaGENIE를 제공한다. v0.21의 간결한 탐색 화면과 v0.20 분석 구현을 재사용한다. 사용자 키·입력·결과를 AlphaGENIE 서버에 수집하지 않는다. 논문 frozen 결과와 새 API 실행을 UI·문서·provenance에서 분리한다.

실제 GitHub 저장소 생성/푸시, 공개 alpha-genie.net 변경, 운영 키·DB 복사, 임의의 실제 API 추론은 이 패키징 작업 범위에 포함하지 않는다.

## 설계 결정

1. **단일 로컬 저장소:** 순수 HTML/CSS/JS v0.21, FastAPI 로컬 서버, 기존 Python 분석 엔진. 개발용 Node 외 별도 프런트엔드 빌드가 필요 없다.
2. **키 입력은 터미널:** `getpass` → 개인 설정 파일 600 권한 또는 환경변수. 키를 받거나 반환하는 웹 API를 만들지 않는다. 암호화 저장으로 표현하지 않는다.
3. **localhost 전용:** 127.0.0.1 bind, 정확한 Host/Origin, 변경 요청용 세션 토큰, 외부 CORS/프록시 신뢰 없음. 다중 사용자/공개 호스팅용 보안 모델로 판매하지 않는다.
4. **로컬 저장:** 설정·job DB·결과는 전용 개인 폴더에 둔다. 저장소 내부 state 디렉터리는 거부한다. 원격 계정/원격 스토리지/Sites 배포를 추가하지 않는다.
5. **검증 후 명시적 실행:** TSV·REF·FAI·GTF·구간·SDK 확인, 전송 동의 후 실행. 분석 lock으로 동시/중복 추론을 제한하고 중단 작업을 자동 재실행하지 않는다.
6. **재현성과 구분:** 새로운 UUID epoch, 원본 score provenance/해시, null 설계·값을 보존한다. SDK 0.8.0을 검사하되 모델 checkpoint는 미공개로 기록한다.

## 단계 및 완료 기준

| 단계 | 이 패키지의 상태 | 완료 기준 / 남은 일 |
|---|---|---|
| 1. 소스 분리 | 구현 | 필요한 앱/worker/6개 pipeline만 복사; 운영 설정·키·DB·v0.18 numerical cache 제외 |
| 2. 로컬 보안 실행기 | 구현 | CLI 설정, key 관리, 사전 검증, API 동의, subprocess 환경 제한, 로그 redaction, 잠금, 경로 검증 |
| 3. 현재 화면 연결 | 구현 | 기존 saved explorer와 새 My analyses 화면, job 상태·기존 엔진 그림·다운로드, 외부 feedback 제거 |
| 4. 테스트/문서/패키징 | 구현 및 검사 기록 | 오프라인 scientific/security/HTTP/JS tests, source scan, 별도 Git 저장소, source ZIP |
| 5. 실제 사용자 환경 검증 | **공개 전 필수** | 새 macOS/Linux 설치, 본인 키로 10-null smoke test, 이후 1,000-null single/multi, quota·장시간 실패·디스크 사용 기록 |
| 6. 공개 권한 확정 | **소유자 결정 필요** | 코드 라이선스, 기여자 권리, bundled manuscript outputs 공개 권한·Google 약관, 저장소 소유자/이름 |
| 7. GitHub 공개 | 미실행 | 비밀정보 스캔 후 명시적인 저장소 생성·push, CI 결과, release note/tag |

## 다음 기능 개발 — 이번 초안에 포함되지 않은 것

- **신규 API의 Brain9/11-category adapter:** frozen release의 track key·life stage·ontology 분류를 별도 버전으로 정의. 새 track은 확인 전 unknown 처리. adult14/embryo7 등 고정 숫자를 미래 API에 강제하지 않는다. 전체 real/null track matrix를 동일하게 재분류하고 누락/중복/1,000-null completeness를 검증한다.
- **신규 frontal cortex 곡선:** UBERON:0001870와 GTEx Brain_Cortex, RNA strand 조건을 명시적으로 선택. 없을 때 Whole brain/첫 track으로 대체하지 않고 unavailable 표시.
- **신규 결과의 v0.21 interactive/stacked exporter 통합:** 원본 엔진 PDF와 숫자 동일성 테스트 후 shared point payload와 figure adapter를 연결한다. 현재 사용자 지정 stacked PDF는 saved single 결과용이다.
- OS keychain 기반 선택적 암호화 저장, 사용자 지정 null seed/분류/모델 버전은 각각 검증된 설정으로 추가한다. 현재 seed는 20260527이며 서버 모델은 미확정이다.
- 대용량 raw score의 압축/선택적 parquet, 안전한 중단·resume는 provenance/추가 과금 확인 절차를 먼저 설계한다. 조용한 legacy cache fallback은 허용하지 않는다.

## 공개 보류 조건

키 또는 개인 경로 유출, saved numerical hash 변경, null provenance 불일치, Brain6/Brain9 혼동, reference 실패 후 조용한 대체, 불완전 cohort의 자동 BH/cosine, 실제-key smoke test 미실행, 라이선스/데이터 권한 미확정 중 하나라도 있으면 안정 버전으로 홍보하지 않는다.
