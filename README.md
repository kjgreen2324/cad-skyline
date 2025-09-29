# CAD-Skyline (AWS Cost Anomaly Detection PoC)

## 📈 개요

이 프로젝트는 **AWS Cost Anomaly Detection** 서비스를 활용하여 **비용 이상 징후를 자동 감지**하고,
이를 실시간으로 **Slack 알림** 및 **자동 완화 조치**로 연계하는 시스템입니다.

AWS의 비용 관리(FinOps) 기능과 여러 서비스를 조합하여,
예상치 못한 비용 급등을 조기에 발견하고 대응할 수 있도록 설계되었습니다.

### 주요 목표

* AWS **비용 이상 이벤트** 자동 감지 및 모니터링
* **Lambda**를 통한 이벤트 처리 및 알림 요약
* **Amazon Bedrock** 활용 → 이상 내역 한국어 요약본 생성
* **Slack Bot 알림** + 관리자 승인 버튼 제공
* 승인 시 → EC2 인스턴스 **자동 중지 (SSM Automation)** 수행

---

## 🏗 아키텍처

아래 아키텍처는 **비용 이상 탐지 → Slack 알림/승인 → 자동 완화**까지의 전체 흐름을 보여줍니다.

```mermaid
flowchart TD
    CAD[AWS Cost Anomaly Detection] --> EB[Amazon EventBridge]
    EB --> R[Router Lambda]
    R --> S3[(S3: 로그 저장)]
    R --> B[Amazon Bedrock]
    R --> SB[Slack Bot 알림]
    SB --> U[관리자 (승인/유지 버튼)]

    U -->|승인| API[API Gateway]
    API --> H[Slack Interaction Handler Lambda]
    H --> W[Worker Lambda]
    W --> SSM[AWS SSM Automation]
    SSM --> EC2[EC2 Instance Stop]
    W --> SU[Slack 메시지 업데이트]
```

---

## ⚙️ 동작 흐름

1. **CAD**: 계정 내 비용 이상 징후 감지 → EventBridge로 이벤트 송신
2. **Router Lambda**

   * 이벤트 로그 S3 저장
   * Bedrock 호출 → 한국어 요약 생성
   * Slack Bot으로 알림 전송 (승인 버튼 포함)
   * EC2 Root Cause 리소스 검증 및 `Quarantine` 태그 부여
3. **관리자**: Slack에서 버튼 클릭 (✅ 중지 승인 / 🚫 유지)
4. **API Gateway + Handler Lambda**: Slack 이벤트 수신, Worker Lambda 호출
5. **Worker Lambda**

   * 승인 시 → **SSM Automation (AWS-StopEC2Instance)** 실행
   * 유지 시 → 기록만 남김
   * 처리 결과로 Slack 메시지 업데이트

---

## 🧩 주요 기술 스택

* **AWS Cost Anomaly Detection** – 비용 이상 탐지
* **Amazon EventBridge** – 이상 이벤트 라우팅
* **AWS Lambda (Python)** – Router / Handler / Worker 함수
* **Amazon S3** – 이상 로그 저장
* **Amazon Bedrock (Titan)** – 이벤트 데이터 한국어 요약
* **Slack Bot + API Gateway** – 알림 전송 및 승인 액션 처리
* **AWS SSM Automation** – EC2 자동 중지 조치

---

## 📊 결과

* 이상 징후 발생 시 → Slack 알림 및 요약 메시지 자동 전송
* Slack에서 **승인 버튼** 클릭 시 → EC2 인스턴스 중지 자동화 확인
* Slack 메시지 업데이트로 운영자가 결과 즉시 확인 가능
* FinOps 환경에서 **비용 이상 탐지 + 대응 자동화 PoC**로 활용 가능

---

## 🙋 본인 기여 포인트

* 비용 이상 탐지 파트 아키텍처 설계 및 구현 담당
* Router Lambda, Slack Bot, Bedrock 요약 연동 직접 구현
* Slack Interactive Button + API Gateway + Worker Lambda 설계/구현
* SSM 기반 EC2 자동 중지 프로세스 시뮬레이션 및 검증

---

## 🔗 참고

* 본 프로젝트는 인턴십 팀 프로젝트 **Skyline**의 일부이며,
  본 레포는 본인이 담당한 **비용 이상 탐지 파트**를 중심으로 정리한 것입니다.

---

✅ 이번 버전은 전부 마크다운 문법만 사용했으니, GitHub `README.md`에 그대로 복붙하셔도 깨지지 않고 잘 보입니다.

혹시 이 README를 **짧게 압축한 PDF 제출용 요약본(2~3쪽)**도 만들어드릴까요?
