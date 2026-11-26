첨부한 파일(`voice-clone/my-voice.m4a`)은 내 목소리 녹음이야.

내 컴퓨터의 OS·CPU·GPU·메모리를 확인하고, 사양에 맞는 Bunyi 앱과 CLI, 음성 복제 모델을 설치해줘.
이미 설치된 항목은 재사용해.

공식 저장소: https://github.com/shaztechio/bunyi-app
다운로드: https://github.com/shaztechio/bunyi-app/releases

설치 후 CLI 사용법(`bunyi --help`, `apps/dotnet/CLI.md`)을 확인하고, CLI로 작업해줘.
필요하면 녹음을 변환하고(`voice-clone/my-voice-reference.wav` 사용 가능) 참조 대본을 추출해서(`bunyi transcribe`)
'내 목소리'라는 이름으로 재사용 가능한 목소리를 등록해줘(`bunyi voices add`).
녹음 처리와 음성 합성은 모두 로컬에서 실행해줘.

아래 대본을 한 번의 요청으로 생성해줘. 원본 목소리의 말투를 살린 약 10초짜리 예시 음성이면 돼.

"안녕하세요. 제 목소리를 복제해 만든 첫 번째 예시입니다. 오늘도 편안하고 좋은 하루 보내세요."

결과를 현재 프로젝트 폴더에 WAV로 저장하고 재생해줘.
사용한 모델과 목소리 ID, 다시 생성하는 명령어도 파일로 남겨줘.
Bunyi 앱과 모델, 등록한 목소리는 유지해줘.
공식 지원 조건에 맞지 않으면 설치 전에 이유를 알려줘.
(참고: macOS CLI는 아직 없고 Windows/Linux x64만 CLI 제공. macOS는 앱 GUI 사용.)
