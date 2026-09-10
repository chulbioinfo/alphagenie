# AlphaGENIE 로컬 설치판

**AlphaGENome-Integrated Explorer**의 v0.21 화면과 v0.20 분석 엔진을 개인 컴퓨터에서 실행하는 배포본입니다.

## API 정보와 개인정보

**이 코드에는 사용자의 API 정보를 AlphaGENIE 운영자에게 수집·전송하는 기능이 없습니다.** 키는 개인 환경에서만 저장·관리하고, Google DeepMind AlphaGenome API 요청을 인증하는 데 사용합니다. 새 분석에서는 실제/null 변이와 구간, 인증 키가 **Google로 전송**됩니다. 따라서 “모든 계산이 완전히 오프라인”이라는 뜻은 아닙니다.

키는 웹 폼이 아니라 터미널의 숨김 입력으로 등록합니다. 기본 저장 위치는 저장소 외부 `~/.alphagenie/credentials.json`이며, 디렉터리 700 / 파일 600 권한을 적용합니다. **암호화 저장은 아닙니다.** 같은 OS 계정, 관리자, 백업/동기화 프로그램으로부터 보호하는 비밀 저장소는 아닙니다. 환경변수 방식은 앱이 키를 파일에 저장하지 않습니다.

자동 피드백 업로드, 원격 분석 프록시, 사용량 추적, Cloudflare 위젯은 포함하지 않습니다. GitHub 이슈를 직접 작성하거나 외부 링크를 열면 해당 서비스의 정책이 적용됩니다.

## 실행

macOS / Linux / WSL2, Python **3.11**을 사용합니다. Windows 네이티브 실행은 지원하지 않습니다.

```sh
bash scripts/setup.sh
source .venv/bin/activate
python -m alphagenie serve
```

브라우저에서 **http://127.0.0.1:8877/**를 여세요. 저장된 RBFOX1 / PTCHD1 / 17변이 결과는 API 키 없이 열고 PDF로 저장할 수 있습니다. 터미널은 계속 열어 둡니다.

새 분석은 samtools와 GRCh38 FASTA·FAI, GENCODE v46 GTF를 준비한 뒤:

```sh
python -m alphagenie key set
python -m alphagenie configure --fasta /path/to/hg38.fa --gtf /path/to/gencode.v46.annotation.gtf.gz
python -m alphagenie doctor
```

**My analyses**에서 TSV를 입력하고 전송에 동의한 다음 실행합니다. 기본 null은 변이당 **1,000개**입니다. 1행이면 single, 2–20행이면 multi이며 첫 행이 cosine reference입니다. REF 불일치·지원하지 않는 입력 길이·복잡한 delins는 API 전에 거부합니다. Ctrl+C로 서버를 종료하면 현재 작업을 중단하며 자동 재실행하지 않습니다.

## 분석 해석에서 반드시 구분할 점

- **저장된 논문 결과:** v0.20 / Brain9(성인 8개 범주 + Embryo) / frontal cortex / 분석당 1,000 null. 17변이 cohort와 RBFOX1 16kb single은 별개입니다.
- **신규 사용자 분석:** v0.20 기존 worker의 **6개 뇌 그룹 + Whole brain**입니다. 이 그룹은 성인 전용이 아닙니다. 신규 결과를 Brain9 논문 재현 결과라고 표시하지 않습니다.
- 다중 분석은 모든 요청 변이가 성공해야 cohort BH/cosine을 만듭니다. 일부 실패 시 완료된 개별 결과를 보존하고 합산 결과는 만들지 않습니다.
- SDK 0.8.0을 고정해도 Google 서버 checkpoint는 고정되지 않습니다. 새 API 숫자가 기존 저장 결과와 같다는 보장은 없습니다. v0.18 데이터로 대체하지 않습니다.
- 저장된 single 그림에는 현재의 인터랙티브 점 표시·위아래 패널·크기 지정 PDF 기능이 유지됩니다. 신규 분석 그림은 기존 엔진 렌더러를 사용하며, 동일한 사용자 지정 PDF 편집 기능은 후속 개발 항목입니다.

원본 점수·null 설계·통계·provenance·로그는 개인 설정 폴더 아래에 저장됩니다. 이를 공유할 때는 개인 변이·파일 경로·민감정보를 직접 검토하세요. 논문용 1Mb×1,000 null은 큰 용량과 시간이 필요할 수 있습니다.

자세한 문서: [설치](docs/INSTALL.md), [개발 계획](docs/DEVELOPMENT_PLAN.md), [Methods](docs/METHODS.md), [개인정보](docs/PRIVACY.md), [GitHub 공개 체크리스트](docs/PUBLISHING.md).

이 배포본은 로컬 **pre-release**입니다. 실제 사용자 API 키로 끝까지 실행하는 검증은 수행하지 않았습니다. 공개 전 코드 라이선스와 배포 권한을 확정해야 하며, Google의 API/출력물 약관은 코드 라이선스와 별개입니다. 실제 GitHub 저장소 생성·푸시는 자동 수행하지 않습니다.
