import boto3
import json
import os
from urllib.request import Request, urlopen
from datetime import datetime

# --- 클라이언트 초기화 ---
s3_client = boto3.client('s3')
ec2_client = boto3.client('ec2')
bedrock_runtime = boto3.client('bedrock-runtime')

# --- 환경 변수 ---
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID')

# --- 메인 핸들러 함수 ---
def lambda_handler(event, context):
    print("Main Handler received event:", json.dumps(event))

    anomaly_data = event.get('detail', {})
    if isinstance(anomaly_data.get('detail'), dict):
        anomaly_data = anomaly_data['detail']

    if not anomaly_data.get('anomalyId'):
        print("No anomalyId found in event, skipping.")
        return {'statusCode': 200, 'body': 'No anomaly data.'}

    # 1) S3 로그 저장
    log_to_s3(anomaly_data)

    # 2) 비용 영향도 체크 후 기본 요약 알림 (impact ≥ 1일 때만)
    impact = anomaly_data.get('impact', {}).get('maxImpact') or \
             anomaly_data.get('impact', {}).get('totalImpact', {}).get('amount')
    if isinstance(impact, (int, float)) and impact >= 1:
        notify_slack_with_bedrock(anomaly_data)

    # 3) RootCause 기반 EC2 autoterminate 탐색
    root_cause = anomaly_data.get('rootCauses', [{}])[0]
    region = root_cause.get('region')
    usage_type = root_cause.get('usageType')  # 예: "BoxUsage:t3.micro"

    if region and usage_type:
        instance_type = usage_type.split(":")[-1]
        check_and_request_remediation(region, instance_type, anomaly_data)

    return {'statusCode': 200, 'body': 'Main Handler processing complete.'}

# --- 헬퍼 함수들 ---
def log_to_s3(data):
    anomaly_id = data.get('anomalyId', 'unknown-id')
    now = datetime.utcnow()
    file_key = f"{now.strftime('%Y/%m/%d')}/{anomaly_id}.json"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=file_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )
        print(f"Successfully logged anomaly {anomaly_id} to S3.")
    except Exception as e:
        print(f"Failed to log to S3: {e}")

def notify_slack_with_bedrock(anomaly_data):
    """Bedrock 요약만 보내는 기본 알림 (impact ≥ 1)"""
    is_test = anomaly_data.get('isTestEvent', False)
    try:
        summary = generate_bedrock_summary(anomaly_data, is_test)
        send_slack_message(SLACK_CHANNEL_ID, summary, is_test=is_test)
    except Exception as e:
        print(f"Bedrock notification failed: {e}")
        send_slack_message(SLACK_CHANNEL_ID, f"Bedrock 요약 실패: `{str(e)}`", is_test=is_test)

def check_and_request_remediation(region, instance_type, anomaly_data):
    """EC2 인스턴스 중 autoterminate=true 태그 있는 경우, 요약+버튼 메시지 전송"""
    ec2 = boto3.client('ec2', region_name=region)
    try:
        resp = ec2.describe_instances(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "instance-type", "Values": [instance_type]},
                {"Name": "tag:autoterminate", "Values": ["true"]}
            ]
        )
        for r in resp.get("Reservations", []):
            for inst in r.get("Instances", []):
                instance_id = inst["InstanceId"]
                request_remediation_approval(
                    {"service": "AmazonEC2", "resourceId": instance_id},
                    anomaly_data
                )
    except Exception as e:
        print(f"Error checking instances in {region}: {e}")

def request_remediation_approval(root_cause, anomaly_data):
    """EC2 발견 시: Quarantine 태그 추가 + Bedrock 요약 + 버튼 알림 하나로 전송"""
    resource_id = root_cause.get('resourceId')
    service = root_cause.get('service', 'N/A')

    if 'AmazonEC2' in service and resource_id:
        try:
            # 1) Quarantine 태그 부여
            ec2_client.create_tags(
                Resources=[resource_id],
                Tags=[{'Key': 'Quarantine', 'Value': 'true'}]
            )

            # 2) Bedrock 요약 블록 생성
            summary_text = generate_bedrock_summary(anomaly_data)
            summary_block = [{"type": "section", "text": {"type": "mrkdwn", "text": summary_text}}]

            # 3) 버튼 블록 생성
            action_blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "🚨 비용 이상 리소스 조치 승인 요청", "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"⚠️ EC2 *{resource_id}* 에 `Quarantine` 태그를 부여했습니다. 비용 누수가 의심되니 아래 조치를 승인해 주세요."}},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ 중지 승인", "emoji": True}, "style": "danger", "value": resource_id, "action_id": "stop_instance"},
                    {"type": "button", "text": {"type": "plain_text", "text": "🚫 유지", "emoji": True}, "value": resource_id, "action_id": "keep_instance"}
                ]}
            ]

            # 4) 최종 메시지 = 요약 + 버튼
            blocks = summary_block + action_blocks

            send_slack_message(SLACK_CHANNEL_ID, "비용 이상 리소스 조치 승인 요청", blocks=blocks)

        except Exception as e:
            send_slack_message(SLACK_CHANNEL_ID, f"조치 요청 실패: `{str(e)}`")

def generate_bedrock_summary(anomaly_data, is_test=False):
    """Bedrock 호출 → 한국어 요약 생성"""
    prompt_header = "[테스트 알림] " if is_test else ""
    prompt = f"""Human: {prompt_header}당신은 AWS FinOps 전문가입니다.
    아래 AWS 비용 이상 탐지 데이터를 보고, 중요한 내용을 요약해서 Slack으로 보낼 메시지를 한국어로 작성해 주세요.
    심각도(anomalyScore), 총 영향($), 예상 원인(rootCauses)을 반드시 포함하고, 담당자가 확인할 사항을 제안해주세요.
    데이터: {json.dumps(anomaly_data)}

    Assistant:"""

    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 1024,
            "temperature": 0.1,
            "topP": 1
        }
    })
    response = bedrock_runtime.invoke_model(
        body=body,
        modelId=BEDROCK_MODEL_ID,
        accept='application/json',
        contentType='application/json'
    )
    response_body = json.loads(response.get('body').read())
    summary = response_body.get('results')[0].get('outputText', '')

    if not summary:
        summary = "AI 모델로부터 요약 정보를 생성하지 못했습니다."
    return summary

def send_slack_message(channel, text, blocks=None, is_test=False):
    header_text = "🚨 [테스트] AWS 비용 이상 탐지 알림!" if is_test else "🚨 AWS 비용 이상 탐지 알림!"
    body = {'channel': channel, 'text': text}
    if blocks:
        if not (blocks[0].get("type") == "header"):
            blocks.insert(0, {"type": "header", "text": {"type": "plain_text", "text": header_text, "emoji": True}})
        body['blocks'] = blocks

    req = Request(
        'https://slack.com/api/chat.postMessage',
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': 'Bearer ' + SLACK_BOT_TOKEN,
            'Content-Type': 'application/json'
        }
    )
    try:
        with urlopen(req) as res:
            print(f"Slack message sent successfully. Response: {res.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error sending to Slack: {e}")
