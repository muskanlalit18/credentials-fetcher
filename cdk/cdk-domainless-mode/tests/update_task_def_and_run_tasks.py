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
    

