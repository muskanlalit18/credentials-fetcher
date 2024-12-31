import boto3
import os
import json

with open('data.json', 'r') as file:
    data = json.load(file)

def run_powershell_script(instance_id, script_path):

    with open(script_path, 'r') as file:
        script_content = file.read()

    ssm = boto3.client('ssm')

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={'commands': [script_content]}
    )

    command_id = response['Command']['CommandId']

    waiter = ssm.get_waiter('command_executed')
    try:
        waiter.wait(
            CommandId=command_id,
            InstanceId=instance_id,
            WaiterConfig={
                'Delay': 30,
                'MaxAttempts': 50
            }
        )
    except Exception as e:
        print(f"Command failed: {script_content}")
        print(f"Error: {str(e)}")
        raise

    output = ssm.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id
    )
    
    print(f"Command output:\n{output.get('StandardOutputContent', '')}")

    if output['Status'] == 'Success':
        print(f"Command status: Success")
    
    if output['Status'] != 'Success':
        print(f"Command failed: {script_content}")
        print(f"Error: {output['StandardErrorContent']}")
        raise Exception(f"Command execution failed: {script_content}")

def get_instance_id_by_name(region, instance_name):

    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': [instance_name]
            },
            {
                'Name': 'instance-state-name',
                'Values': ['running']
            }
        ]
    )

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            return instance['InstanceId']
    
    return None

region = os.environ["AWS_REGION"] 
instance_name = data["windows_instance_tag"]

instance_id = get_instance_id_by_name(region, instance_name)
script_path = os.path.join(os.path.dirname(__file__), 'gmsa.ps1')

run_powershell_script(instance_id, script_path)
