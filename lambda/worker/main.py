import boto3
import json
import os
import urllib.parse
from urllib.request import Request, urlopen

# --- 클라이언트 초기화 ---
ssm_client = boto3.client('ssm')

# --- 환경 변수 ---
# 이 함수는 response_url을 사용하므로 Bot Token만 있어도 되지만, 
# 만약을 위해 Channel ID도 추가할 수 있습니다.
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN') 
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def lambda_handler(event, context):
    print("Interaction worker received event:", json.dumps(event))

    if 'body' in event and event.get('body'):
        try:
            body_str = urllib.parse.unquote(event['body']).replace('payload=', '')
            payload = json.loads(body_str)
            if 'actions' in payload:
                handle_slack_interaction(payload)
        except Exception as e:
            print(f"Could not parse Slack interaction: {e}")
    
    return {'statusCode': 200, 'body': 'Worker processing complete.'}

def handle_slack_interaction(payload):
    action = payload.get('actions', [{}])[0]
    action_id = action.get('action_id')
    resource_id = action.get('value')
    response_url = payload.get('response_url')
    
    response_text = ""
    if action_id == 'stop_instance':
        try:
            ssm_client.start_automation_execution(
                DocumentName='AWS-StopEC2Instance',
                Parameters={'InstanceId': [resource_id]}
            )
            response_text = f"✅ 관리자가 승인하여 *{resource_id}* 인스턴스 중지 명령을 전송했습니다."
        except Exception as e:
            response_text = f"❌ *{resource_id}* 인스턴스 중지 실패: `{str(e)}`"
            
    elif action_id == 'keep_instance':
        response_text = f"ℹ️ 관리자가 *{resource_id}* 인스턴스를 유지하기로 결정했습니다."
    
    if response_url and response_text:
        updated_message = {
            "text": response_text,
            "replace_original": True # True: 원본 버튼 메시지가 이 텍스트로 바뀜
        }
        req = Request(response_url, data=json.dumps(updated_message).encode('utf-8'), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(req) as res:
                print(f"Successfully updated original Slack message. Response: {res.read().decode('utf-8')}")
        except Exception as e:
            print(f"Failed to update original message: {e}")