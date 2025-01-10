import boto3
import json
import os

"""
AWS ECS Task Definition Update and Execution Script

This script automates the process of updating and running ECS (Elastic Container Service) tasks. It performs the following operations:

Task Definition Management:

Identifies all task definition families matching a specified pattern.
For each task definition family: 
a. Updates the task definition with a new Docker image URI from ECR. 
b. Registers a new revision of the task definition with ECS.

Task Execution:

For each updated task definition: 
a. Attempts to run a new task in the specified ECS cluster. 
b. Configures the task with the appropriate network settings (subnets and security group).

"""

def update_task_definition_image(task_definition_family, repository_name, tag, region):
    ecs_client = boto3.client('ecs', region_name=region)
    ecr_client = boto3.client('ecr', region_name=region)
    response = ecr_client.describe_repositories(repositoryNames=[repository_name])
    repository_uri = response['repositories'][0]['repositoryUri']
    image_uri = f"{repository_uri}:{tag}"
    
    # Get the current task definition
    response = ecs_client.describe_task_definition(taskDefinition=task_definition_family)
    task_definition = response['taskDefinition']

    # Update the container definition with the new image URI
    container_definitions = task_definition['containerDefinitions']
    for container in container_definitions:
        if container['name'] == 'MyContainer':  
            container['image'] = image_uri

    # Prepare arguments for register_task_definition
    register_args = {
        'family': task_definition['family'],
        'taskRoleArn': task_definition['taskRoleArn'],
        'executionRoleArn': task_definition['executionRoleArn'],
        'networkMode': task_definition['networkMode'],
        'containerDefinitions': container_definitions,
        'volumes': task_definition.get('volumes', []),
        'placementConstraints': task_definition.get('placementConstraints', []),
        'requiresCompatibilities': task_definition['requiresCompatibilities'],
        'cpu': task_definition['cpu'],
        'memory': task_definition['memory'],
    }

    if 'tags' in task_definition and task_definition['tags']:
        register_args['tags'] = task_definition['tags']

    # Register the new task definition and get the revised ARN
    new_task_definition = ecs_client.register_task_definition(**register_args)

    revised_arn = new_task_definition['taskDefinition']['taskDefinitionArn']
    
    print(f"New task definition registered for {task_definition_family}")
    print(f"Revised ARN: {revised_arn}")
    
    return revised_arn

def run_task(ecs_client, cluster_name, task_definition, subnet_ids, security_group_id):
    
    try:
        task_def_description = ecs_client.describe_task_definition(taskDefinition=task_definition)
        container_defs = task_def_description['taskDefinition']['containerDefinitions']
        
        # Check if any container in the task definition has a credentialSpecs field
        has_cred_specs = any('credentialSpecs' in container and container['credentialSpecs'] 
                             for container in container_defs)
        
        if not has_cred_specs:
            print(f"Skipping task definition {task_definition} as it does not have credentialSpecs")
            return None
        
        task = ecs_client.run_task(
            cluster=cluster_name,
            taskDefinition=task_definition,
            count=1,
            launchType='EC2',
            networkConfiguration={
                'awsvpcConfiguration': {
                'subnets': subnet_ids,
                'securityGroups': [security_group_id],
            }
            }
        )
        print(f"Started task: {json.dumps(task['tasks'][0]['taskArn'], default=str)}")
        return task['tasks'][0]['taskArn']
    except ecs_client.exceptions.ClientException as e:
        print(f"Error starting task for {task_definition}: {str(e)}")
        return None

def get_task_definition_families(ecs_client, pattern):
    paginator = ecs_client.get_paginator('list_task_definitions')
    task_families = set()

    for page in paginator.paginate():
        for arn in page['taskDefinitionArns']:
            if pattern in arn:
                family = arn.split('/')[1].split(':')[0]
                task_families.add(family)

    return list(task_families)

try:

    with open('data.json', 'r') as file:
        data = json.load(file)

    def get_value(key):
        return os.environ.get(key, data.get(key.lower()))

    directory_name = data["directory_name"]
    netbios_name = data["netbios_name"]
    number_of_gmsa_accounts = data["number_of_gmsa_accounts"]
    stack_name = data["stack_name"]
    cluster_name = data["cluster_name"]
    vpc_name = data["vpc_name"]
    task_definition_template_name = data["task_definition_template_name"]
    repository_name = data["ecr_repo_name"]
    region = get_value("AWS_REGION")
    tag = data["docker_image_tag"]

    ecs_client = boto3.client('ecs', region_name=region)
    ec2_client = boto3.client('ec2', region_name=region)

    response = ec2_client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])
    if not response['Vpcs']:
        raise ValueError(f"No VPC found with name: {vpc_name}")
    vpc_id = response['Vpcs'][0]['VpcId']

    # Get subnets
    response = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    if not response['Subnets']:
        raise ValueError(f"No subnets found in VPC: {vpc_id}")
    subnet_ids = [subnet['SubnetId'] for subnet in response['Subnets']]

    # Get security group
    response = ec2_client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    if not response['SecurityGroups']:
        raise ValueError(f"No security groups found in VPC: {vpc_id}")
    security_group_id = response['SecurityGroups'][0]['GroupId']

    # Get all task definition families
    task_families = get_task_definition_families(ecs_client, task_definition_template_name)
    if not task_families:
        raise ValueError(f"No task definition families found matching pattern: {task_definition_template_name}")

    for task_family in task_families:
        try:
            # Update task definition and get the new ARN
            new_task_definition_arn = update_task_definition_image(task_family, repository_name, tag, region)
            task_arn = run_task(ecs_client, cluster_name, new_task_definition_arn, subnet_ids, security_group_id)
            if task_arn:
                print(f"Task started for family {task_family}: {task_arn}")
            else:
                print(f"Failed to start task for family {task_family}")
        except Exception as e:
            print(f"Error processing task family {task_family}: {str(e)}")

    print("All tasks have been processed.")

except Exception as e:
    print(f"An unexpected error occurred: {str(e)}")
    

