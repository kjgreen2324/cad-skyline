import boto3
import json
import os
import time

lambda_client = boto3.client('lambda')
WORKER_LAMBDA_NAME = os.environ.get('WORKER_LAMBDA_NAME')

def lambda_handler(event, context):
    print("Interaction router received event from API Gateway.")
    print(f"Received event: {json.dumps(event)}")
    
    # 먼저 Slack에 즉시 응답 (3초 내 응답 보장)
    slack_response = {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({})
    }
    
    try:
        # Worker Lambda를 비동기적으로 호출
        lambda_client.invoke(
            FunctionName=WORKER_LAMBDA_NAME,
            InvocationType='Event',
            Payload=json.dumps(event)
        )
        print(f"Successfully invoked {WORKER_LAMBDA_NAME}")
    except Exception as e:
        print(f"Failed to invoke worker Lambda: {e}")
        # Worker Lambda 호출 실패해도 Slack에는 성공 응답 (에러는 로그로만)
    
    return slack_response