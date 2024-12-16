import boto3
import json
import os

with open('data.json', 'r') as file:
    data = json.load(file)

directory_name = data["directory_name"]
instance_name = "Credentials-fetcher-AD-Stack/MyAutoScalingGroup"

def add_security_group_to_instance(directory_name, instance_name):

    ds = boto3.client('ds') 
    ec2 = boto3.client('ec2')

    directories = ds.describe_directories()['DirectoryDescriptions']
    directory = next((d for d in directories if d['Name'] == directory_name), None)
    
    if not directory:
        raise ValueError(f"Directory '{directory_name}' not found")

    directory_id = directory['DirectoryId']
    print(f"Found directory ID: {directory_id}")

    directory_details = ds.describe_directories(DirectoryIds=[directory_id])['DirectoryDescriptions'][0]
    security_group_id = directory_details['VpcSettings']['SecurityGroupId']

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

    if not response['Reservations']:
        raise ValueError(f"No instances found with tag:Name '{instance_name}'")
    
    instances = response['Reservations'][0]['Instances']
    if not instances:
        raise ValueError(f"No instances found in the reservation")
    
    instance = instances[0]
    
    if 'SecurityGroups' not in instance or not instance['SecurityGroups']:
        raise ValueError(f"No security groups found for the instance")
    
    instance_sg_id = instance['SecurityGroups'][0]['GroupId']

    # Add the new inbound rule to the security group
    try:
        ec2.authorize_security_group_ingress(
            GroupId=instance_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': '-1',  # All traffic
                    'FromPort': -1,      # All ports
                    'ToPort': -1,        # All ports
                    'UserIdGroupPairs': [{'GroupId': security_group_id}]
                }
            ]
        )
        print(f"Successfully added inbound rule to security group {instance_sg_id}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

try:
    add_security_group_to_instance(directory_name, instance_name)
except Exception as e:
    print(f"An error occurred: {str(e)}")
