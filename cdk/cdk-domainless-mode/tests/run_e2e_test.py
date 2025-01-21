from time import sleep

import boto3
import os
import math
import copy
import json
from create_secrets import create_secrets
from copy_credspecs_and_create_task_defs import (setup_aws_session,
                                                 get_ecs_task_execution_role_arn,
                                                 get_task_definition_template,
                                                 get_ecs_cluster_info,
                                                 create_credspec,
                                                 upload_credspec_to_s3,
                                                 modify_task_definition,
                                                 register_new_task_definition)
from parse_data_from_json import (number_of_gmsa_accounts, netbios_name,
                                  directory_name, stack_name, vpc_name, tag,
                                  task_definition_template_name,
                                  cluster_name, region, bucket_name,
                                  aws_profile_name, instance_name,
                                  windows_instance_tag, repository_name, containers_per_instance)
from setup_windows_instance import get_instance_id_by_name, run_powershell_script
from update_inbound_rules import add_security_group_to_instance
from update_task_def_and_run_tasks import (get_task_definition_families,
                                           update_task_definition_image, run_task)
from run_sql_test import get_windows_hostname, run_shell_script
from botocore.exceptions import ClientError

s3_client = boto3.client('s3')
ecs_client = boto3.client('ecs')
secrets_manager_client = boto3.client('secretsmanager')


def check_s3_bucket_exists():
    s3_client = boto3.client('s3')
    try:
        # Try to head the bucket
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"Bucket {bucket_name} exists and you have access to it.")
        return True
    except ClientError as e:
        error_code = int(e.response['Error']['Code'])
        if error_code == 403:
            print(f"Bucket {bucket_name} exists, but you don't have permission to access it.")
            return True
        elif error_code == 404:
            print(f"Bucket {bucket_name} does not exist.")
            return False
        else:
            print(f"An error occurred: {e}")
            return False

def create_s3_bucket():
    """Create an S3 bucket in a specified region

    If a region is not specified, the bucket is created in the S3 default
    region (us-east-1).

    :param bucket_name: Bucket to create
    :param region: String region to create bucket in, e.g., 'us-west-2'
    :return: True if bucket created, else False
    """

    # Create bucket
    try:
        if region is None:
            s3_client = boto3.client('s3')
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client = boto3.client('s3', region_name=region)
            location = {'LocationConstraint': region}
            s3_client.create_bucket(Bucket=bucket_name,
                                    CreateBucketConfiguration=location)
    except ClientError as e:
        print(f"Couldn't create bucket {bucket_name}.")
        print(f"Error: {e}")
        return False

    print(f"Bucket {bucket_name} created successfully.")
    return True

def update_asg_min_capacity(capacity):
    try:
        autoscaling_client = boto3.client('autoscaling', region_name=region)
        response = autoscaling_client.describe_auto_scaling_groups()
        asg_found = False
        for asg in response['AutoScalingGroups']:
            if stack_name in asg['AutoScalingGroupName']:
                asg_found = True
                response = autoscaling_client.update_auto_scaling_group(
                    AutoScalingGroupName=asg['AutoScalingGroupName'],
                    MinSize=capacity,
                    MaxSize=capacity,
                    DesiredCapacity=capacity
                )
                print(f"Successfully updated ASG {asg['AutoScalingGroupName']} desired capacity to {capacity}")
                return True
        
        if not asg_found:
            print(f"No Auto Scaling Group found containing '{stack_name}'")
            return False
    except Exception as e:
        print(f"Error updating ASG: {str(e)}")
        return False
def create_task_definition_groups(number_of_gmsa_accounts, max_containers=10):
    """
    Create groups of GMSA accounts for task definitions
    """
    groups = []
    current_group = []
    
    for i in range(1, number_of_gmsa_accounts + 1):
        current_group.append(i)
        if len(current_group) == max_containers:
            groups.append(current_group)
            current_group = []
    
    if current_group:  # Add any remaining accounts
        groups.append(current_group)
    
    return groups

def create_and_register_tasks():
    try:
        setup_aws_session(aws_profile_name)
        ecs_task_execution_role_arn = get_ecs_task_execution_role_arn()
        task_definition_template = get_task_definition_template(ecs_client, task_definition_template_name)
        ecs_cluster_arn, ecs_cluster_instance_arn = get_ecs_cluster_info(ecs_client, "Credentials-fetcher-ecs-load-test")

        if not all([ecs_task_execution_role_arn, task_definition_template, ecs_cluster_arn]):
            print("Failed to retrieve necessary resources.")
            return False

        # Print template structure for debugging
        # print(f"Template structure: {json.dumps(task_definition_template, indent=2)}")

        # Get the new image URI
        try:
            ecr_client = boto3.client('ecr', region_name=region)
            response = ecr_client.describe_repositories(repositoryNames=[repository_name])
            repository_uri = response['repositories'][0]['repositoryUri']
            image_uri = f"{repository_uri}:{tag}"
        except Exception as e:
            print(f"Failed to get ECR repository URI: {str(e)}")
            return False

        required_instances = math.ceil(number_of_gmsa_accounts / containers_per_instance)
        if not update_asg_min_capacity(required_instances):
            print(f"Error updating desired capacity to {required_instances}, exiting...")
            return False

        # Group GMSA accounts into sets of 10 or fewer
        account_groups = create_task_definition_groups(number_of_gmsa_accounts)
        
        template_task_def = task_definition_template['taskDefinition']  # Get the task definition part once
        
        for group_index, group in enumerate(account_groups):
            # Create container definitions for this group
            container_definitions = []
            
            for account_number in group:
                gmsa_name = f"WebApp0{account_number}"
                secret_id = f"aws/directoryservice/{netbios_name}/gmsa"
                gmsa_secret_arn = secrets_manager_client.get_secret_value(SecretId=secret_id)['ARN']
                
                credspec = create_credspec(directory_name, netbios_name, gmsa_name, gmsa_secret_arn)
                bucket_arn, s3_key = upload_credspec_to_s3(s3_client, bucket_name, gmsa_name, credspec)
                
                if not bucket_arn:
                    print(f"Failed to upload credspec for {gmsa_name}")
                    continue
                    
                # Create a container definition for this GMSA account
                container_def = create_container_definition(
                    template_task_def['containerDefinitions'][0],
                    bucket_arn,
                    s3_key,
                    gmsa_name,
                    image_uri
                )
                container_definitions.append(container_def)
            
            # Create family name for this group
            base_family = template_task_def['family']
            family = f"{base_family}-group-{group_index + 1}"

            # Create the complete task definition
            modified_task_def = {
                'networkMode': template_task_def['networkMode'],
                'containerDefinitions': container_definitions,
                'cpu': template_task_def['cpu'],
                'memory': template_task_def['memory']
            }

            # Register the task definition for this group
            response = register_new_task_definition(
                ecs_client,
                modified_task_def,
                family,
                ecs_task_execution_role_arn
            )
            
            print(f"Registered new task definition for group {group_index + 1}: {response['taskDefinition']['taskDefinitionArn']}")
        
        return True

    except Exception as e:
        print(f"An error occurred in create_and_register_tasks: {str(e)}")
        import traceback
        traceback.print_exc()  # This will print the full stack trace
        return False


def create_container_definition(template_container, bucket_arn, s3_key, gmsa_name, image_uri):
    """
    Create a container definition based on the template and GMSA details
    """
    container_def = copy.deepcopy(template_container)
    container_def['name'] = f"MyContainer-{gmsa_name}"
    container_def['image'] = image_uri  # Update the image URI
    container_def['credentialSpecs'] = [f"credentialspecdomainless:{bucket_arn}/{s3_key}"]
    return container_def

def is_s3_bucket_empty():
    try:
        # List objects in the bucket
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)

        # If KeyCount is 0, the bucket is empty
        if response['KeyCount'] == 0:
            print(f"The bucket '{bucket_name}' is empty.")
            return True
        else:
            print(f"The bucket '{bucket_name}' is not empty.")
            return False

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"The bucket '{bucket_name}' does not exist.")
        elif e.response['Error']['Code'] == 'AccessDenied':
            print(f"Access denied to bucket '{bucket_name}'. Check your permissions.")
        else:
            print(f"An error occurred: {e}")
        return None

def empty_s3_bucket():
    
    """
   Empty an S3 bucket by deleting all objects and versions.

   :param bucket_name: Name of the S3 bucket to empty
   """
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)

    try:
        # Delete objects (excluding .rpm files)
        print(f"Deleting objects in bucket '{bucket_name}' (only credspec.json files)...")
        objects_to_delete = [obj for obj in bucket.objects.all() if obj.key.endswith('credspec.json')]
        
        if objects_to_delete:
            bucket.delete_objects(
                Delete={
                    'Objects': [{'Key': obj.key} for obj in objects_to_delete]
                }
            )

        # Delete object versions (excluding .rpm files)
        print(f"Deleting object versions in bucket '{bucket_name}' (only credspec.json files)...")
        versions_to_delete = [ver for ver in bucket.object_versions.all() 
                            if ver.object_key.endswith('credspec.json')]
        
        if versions_to_delete:
            bucket.delete_objects(
                Delete={
                    'Objects': [{'Key': ver.object_key, 'VersionId': ver.id} 
                               for ver in versions_to_delete]
                }
            )
        print(f"Removed all credspec.json files from {bucket_name}")
        return True
    except ClientError as e:
        print(f"An error occurred while emptying the bucket: {e}")
        return False

def update_windows_instance():
    instance_id = get_instance_id_by_name(region, instance_name)
    script_path = os.path.join(os.path.dirname(__file__), 'gmsa.ps1')
    return run_powershell_script(instance_id, script_path)

def run_tasks():
    try:
        ecs_client = boto3.client('ecs', region_name=region)
        ec2_client = boto3.client('ec2', region_name=region)

        # Get VPC info
        response = ec2_client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])
        if not response['Vpcs']:
            print(f"No VPC found with name: {vpc_name}")
            return False
        vpc_id = response['Vpcs'][0]['VpcId']

        # Get subnets
        response = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        if not response['Subnets']:
            print(f"No subnets found in VPC: {vpc_id}")
            return False
        subnet_ids = [subnet['SubnetId'] for subnet in response['Subnets']]

        # Get security group
        response = ec2_client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        if not response['SecurityGroups']:
            print(f"No security groups found in VPC: {vpc_id}")
            return False
        security_group_id = response['SecurityGroups'][0]['GroupId']

        # Get all task definition families
        task_families = get_task_definition_families(ecs_client, task_definition_template_name)
        if not task_families:
            print(f"No task definition families found matching pattern: {task_definition_template_name}")
            return False
        
        # Run tasks for each family
        for task_family in task_families:
            try:
                # Get the latest task definition ARN for this family
                response = ecs_client.describe_task_definition(taskDefinition=task_family)
                task_definition_arn = response['taskDefinition']['taskDefinitionArn']
                
                task_arn = run_task(ecs_client, cluster_name, task_definition_arn, subnet_ids, security_group_id)
                if task_arn:
                    print(f"Task started for family {task_family}: {task_arn}")
                else:
                    print(f"Failed to start task for family {task_family}")

            except Exception as e:
                print(f"Error processing task family {task_family}: {str(e)}")

        print("All tasks have been processed.")
        return True

    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        return False


def get_running_task_definitions():
    """
    Get a set of task definition ARNs that are currently running.
    """
    running_task_defs = set()

    try:
        # List all clusters
        clusters = ecs_client.list_clusters()['clusterArns']

        for cluster in clusters:
            # Get running tasks in each cluster
            running_tasks = ecs_client.list_tasks(
                cluster=cluster,
                desiredStatus='RUNNING'
            )['taskArns']

            if running_tasks:
                # Get task details including task definition
                tasks = ecs_client.describe_tasks(
                    cluster=cluster,
                    tasks=running_tasks
                )['tasks']

                # Add task definition ARNs to set
                for task in tasks:
                    running_task_defs.add(task['taskDefinitionArn'])

    except ClientError as e:
        print(f"Error getting running tasks: {e}")
        return None

    return running_task_defs

def delete_unused_task_definitions():
    """
    Delete task definitions that are not running and have credentialSpecs defined.
    """
    try:
        # Get running task definitions
        running_task_defs = get_running_task_definitions()
        if running_task_defs is None:
            return

        # Get all task definition families
        families = ecs_client.list_task_definition_families()['families']

        deleted_count = 0
        skipped_count = 0
        # List all task definitions for this family
        task_defs = ecs_client.list_task_definitions()

        if 'taskDefinitionArns' in task_defs:
            for arn in task_defs['taskDefinitionArns']:
                # Skip if task definition is running
                if arn in running_task_defs:
                    print(f"Skipping running task definition: {arn}")
                    skipped_count += 1
                    continue

                # Get task definition details
                task_def = ecs_client.describe_task_definition(
                    taskDefinition=arn
                )['taskDefinition']

                # print(task_def)
                # Check if any container has credentialSpecs
                for container in task_def['containerDefinitions']:
                    if 'credentialSpecs' in container:
                        try:
                            # Deregister task definition
                            ecs_client.deregister_task_definition(
                                taskDefinition=arn
                            )
                            print(f"Deleted task definition: {arn}")
                            deleted_count += 1
                        except ClientError as e:
                            print(f"Error deleting task definition {arn}: {e}")
                    else:
                        print(f"Skipping task definition without credentialSpecs: {arn}")
                        skipped_count += 1

        print(f"\nSummary:")
        print(f"Deleted task definitions: {deleted_count}")
        print(f"Skipped task definitions: {skipped_count}")
        return True

    except ClientError as e:
        print(f"Error: {e}")
        return False

def run_sql_test():
    instance_name_linux = stack_name + '/MyAutoScalingGroup'
    instance_id_linux = get_instance_id_by_name(region, instance_name_linux)
    instance_id_windows = get_instance_id_by_name(region, windows_instance_tag)
    hostname = get_windows_hostname(instance_id_windows)
    return run_shell_script(instance_id_linux, hostname)

def run_e2e_test():
    if not check_s3_bucket_exists():
        print("Please create S3 bucket and try again, exiting...")
        return
    if not is_s3_bucket_empty():
        if not empty_s3_bucket():
            print("s3 bucket was not emptied properly, exiting...")
            return
    print("Using s3 bucket: " + bucket_name)
    print("----------S3 bucket ready for use-----------------")
    if not create_secrets():
        print("secrets were not created properly, exiting...")
        return
    print("\n" * 3)
    print("-----------------Secret Creation Complete.-------------------")
    if not update_windows_instance():
        print("Error updating Windows instance, exiting...")
        return 
    print("\n" * 3)
    print("-----------------Windows instance is Ready--------------------")
    if not add_security_group_to_instance(directory_name, instance_name):
        print("Error adding inbound rule to security group, exiting...")
        return
    print("\n" * 3)
    print("--------Linux instance has necessary Security groups Added----")
    print("\n" * 3)
    if not delete_unused_task_definitions():
        print("Old task definitions weren't deleted properly, will try to create and register new task definitions still. If the next step fails, please manually delete old and unused task definitions and try again...")
    if not create_and_register_tasks():
        print("Not able to create and register new task definitions, exiting...")
        return
    print("\n" * 3)
    print("-----------------Created and Registered Tasks.----------------")
    print("\n" * 3)
    if not run_tasks():
        print("Error running tasks, exiting...")
        return
    print("\n" * 3)
    print("--------Tasks running, ready to run SQL Test--------")
    print("Waiting 15 seconds before running SQL Test")
    print("\n" * 3)
    sleep(15)
    print("Sleep complete. Executing SQL test now.")
    if run_sql_test():
        print("###################################################")
        print("\n" * 3)
        print("------------E2E Test Successful!!------------------")
        print("\n" * 3)
        print("###################################################")
    else:
        print("Error running E2E test, exiting...")
        retry = input("Do you want to retry? (yes/no): ").lower().strip()
        if retry in ['yes', 'y']:
            print("Retrying E2E test...")
            if run_sql_test():
                print("###################################################")
                print("\n" * 3)
                print("------------E2E Test Successful!!------------------")
                print("\n" * 3)
                print("###################################################")
            else:
                print("Error running E2E test, exiting...")
        return
    response = input("\nAre you ready to run cleanup? (yes/no): ").lower().strip()
    if response in ['yes', 'y']:
        return True
    elif response in ['no', 'n']:
        return False
    else:
        print("Please enter 'yes' or 'no'")
    
    
def cleanup_after_test_complete():
    print("\n" * 3)
    print("------------Initiating cleanup after test--------------")
    print("\n" * 3)
    empty_s3_bucket()
    delete_unused_task_definitions()
    print("\n" * 3)
    print("------------Cleanup Complete!!--------------")
    print("\n" * 3)

if run_e2e_test():
    cleanup_after_test_complete()
else:
    print("Cleanup skipped, please cleanup manually later...")

