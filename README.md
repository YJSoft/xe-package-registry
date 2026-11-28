# XE 쉬운설치 자료실

XE 비공식 패치의 쉬운설치 모듈에서 읽는 공개 자료실입니다. 자료 목록과 상세 정보, 배포 ZIP은 [GitHub Pages](https://yjsoft.github.io/xe-package-registry/)에서 제공합니다.

등록 자료와 버전은 `packages.json`에서 관리합니다. 커밋 SHA, ZIP 바이트 수와 SHA-256, 설치 트리 SHA-256, 지원 환경, 원본 제작자와 라이선스를 기록합니다. 코드 검토 후 등록하고 철회한 버전은 삭제하지 말고 `withdrawn`을 true로 변경하세요. 게시한 버전의 파일은 교체하지 않습니다.

PR에서 `python3 publish.py /tmp/xe-registry-preview` 검사를 실행합니다. 기본 브랜치 반영 후 GitHub Pages 환경의 RSA 키로 목록에 서명합니다. 서명 대상은 봉투의 `payload`를 Base64 디코딩한 UTF-8 바이트이며 알고리즘은 RSA PKCS#1 v1.5/SHA-256입니다. 목록은 21일 후 만료되며 주 2회 다시 게시합니다. `v1/index.json`의 세대 번호는 발행 시각(UTC Unix 초)입니다. 각 상세 JSON과 ZIP은 SHA-256을 파일명으로 사용합니다.

키를 교체할 때는 클라이언트 공개키도 함께 배포해야 합니다. 개인키는 등록 저장소와 공개 파일에 포함하지 않습니다. 복구 시 저장한 개인키와 등록 내역으로 빌드한 뒤 기존 클라이언트로 서명과 ZIP을 확인하세요.

승인한 ZIP 원본은 `archives/<SHA-256>.zip`에 보관합니다. 새 버전을 등록할 때는 원본 저장소의 고정 커밋 ZIP과 출처를 함께 제출하세요. 게시 후에는 원본 서버가 중단되거나 ZIP 압축 방식이 변경되어도 같은 바이트를 배포할 수 있습니다. 등록 도구는 GPL-2.0-or-later이며 각 ZIP은 내부에 포함된 제작자 고지와 라이선스를 따릅니다.

심플스트랩은 원본의 GPLv2 변경 커밋 `1cdcdab80d467b071e6cda8af869ff76b4fe132d`를 기준으로 분리했습니다. 각 ZIP은 XE 설치 폴더에서 바로 풀 수 있도록 원래의 하위 경로를 유지하며, 해당 구성요소의 소스와 원본 LICENSE를 함께 제공합니다. 같은 커밋이 있는 로컬 저장소에서 `python3 pack_component.py /path/to/xe-simplestrap simplestrap 3.0 layout.zip`으로 등록된 ZIP을 재현할 수 있습니다. [원본 저장소](https://github.com/wincomi/xe-simplestrap)

자료별 PNG는 `thumbnails/`에 두고 `packages.json`의 `thumbnail`에 파일명을 등록합니다. 초기 섬네일은 XE에 포함된 XEIcon 글리프와 단색 배경으로 만들었습니다. [XEIcon](https://github.com/xpressengine/XEIcon)

스킨과 구성요소 ZIP을 지원하는 클라이언트는 `v1/index-v2.json`을 읽습니다. `v1/index.json`은 기존 클라이언트가 설치할 수 있는 자료를 계속 제공합니다.

함께 설치해야 할 자료는 `requires`에 자료 ID 목록으로 지정합니다. 게시 전에 누락된 자료와 순환 참조를 검사합니다.
