from time import sleep

import boto3
import os
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
                                  windows_instance_tag, repository_name)
from setup_windows_instance import get_instance_id_by_name, run_powershell_script
from update_inbound_rules import add_security_group_to_instance
from update_task_def_and_run_tasks import (get_task_definition_families,
                                           update_task_definition_image, run_task)
from run_sql_test import get_windows_hostname, run_shell_script
from delete_secrets import delete_secrets
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

def create_and_register_tasks():
    setup_aws_session(aws_profile_name)
    ecs_task_execution_role_arn = get_ecs_task_execution_role_arn()
    task_definition_template = get_task_definition_template(ecs_client, task_definition_template_name)
    ecs_cluster_arn, ecs_cluster_instance_arn = get_ecs_cluster_info(ecs_client, "Credentials-fetcher-ecs-load-test")

    if not all([ecs_task_execution_role_arn, task_definition_template, ecs_cluster_arn]):
        print("Failed to retrieve necessary resources.")
        return

    if not all([ecs_task_execution_role_arn, task_definition_template, ecs_cluster_arn]):
        print("Failed to retrieve necessary resources.")
        return

    for i in range(1, number_of_gmsa_accounts + 1):
        gmsa_name = f"WebApp0{i}"
        secret_id = f"aws/directoryservice/{netbios_name}/gmsa/{gmsa_name}"
        gmsa_secret_arn = secrets_manager_client.get_secret_value(SecretId=secret_id)['ARN']

        credspec = create_credspec(directory_name, netbios_name, gmsa_name, gmsa_secret_arn)
        bucket_arn, s3_key = upload_credspec_to_s3(s3_client, bucket_name, gmsa_name, credspec)

        if not bucket_arn:
            print(f"Failed to upload credspec for {gmsa_name}")
            continue

        modified_task_definition = modify_task_definition(task_definition_template, ecs_cluster_arn, bucket_arn, s3_key)
        family = f"{task_definition_template['taskDefinition']['family']}-{i}"

        response = register_new_task_definition(ecs_client, modified_task_definition, family, ecs_task_execution_role_arn)
        print(f"Registered new task definition for {gmsa_name}: {response['taskDefinition']['taskDefinitionArn']}")

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
        # Delete all objects
        print(f"Deleting all objects in bucket '{bucket_name}'...")
        bucket.objects.all().delete()

        # Delete all object versions (if versioning is enabled)
        print(f"Deleting all object versions in bucket '{bucket_name}'...")
        bucket.object_versions.all().delete()

        print(f"Bucket '{bucket_name}' has been emptied successfully.")
    except ClientError as e:
        print(f"An error occurred while emptying the bucket: {e}")

def update_windows_instance():
    instance_id = get_instance_id_by_name(region, instance_name)
    script_path = os.path.join(os.path.dirname(__file__), 'gmsa.ps1')
    run_powershell_script(instance_id, script_path)

def update_task_defs_and_run_tasks():
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

                print(task_def)
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

    except ClientError as e:
        print(f"Error: {e}")

def run_sql_test():
    instance_name_linux = stack_name + '/MyAutoScalingGroup'
    instance_id_linux = get_instance_id_by_name(region, instance_name_linux)
    instance_id_windows = get_instance_id_by_name(region, windows_instance_tag)
    hostname = get_windows_hostname(instance_id_windows)
    run_shell_script(instance_id_linux, hostname)

def run_e2e_test():
    if not check_s3_bucket_exists():
        if not create_s3_bucket():
            print("s3 bucket was not created properly, exiting...")
            return
    if not is_s3_bucket_empty():
        empty_s3_bucket()
    print("Using s3 bucket: " + bucket_name)
    print("----------S3 bucket created and ready for use-----------------")
    create_secrets()
    print("\n" * 3)
    print("-----------------Secret Creation Complete.-------------------")
    print("\n" * 3)
    create_and_register_tasks()
    print("\n" * 3)
    print("-----------------Created and Registered Tasks.---------------")
    print("\n" * 3)
    print("-----------------Windows instance is Ready--------------------")
    add_security_group_to_instance(directory_name, instance_name)
    print("\n" * 3)
    print("--------Linux instance has necessary Security groups Added----")
    print("\n" * 3)
    update_task_defs_and_run_tasks()
    print("\n" * 3)
    print("--------Task definition updated, ready to run SQL Test--------")
    print("Waiting 15 seconds before running SQL Test")
    print("\n" * 3)
    sleep(15)
    print("Sleep complete. Executing SQL test now.")
    run_sql_test()
    print("###################################################")
    print("###################################################")
    print("###################################################")
    print("###################################################")
    print("\n" * 3)
    print("------------E2E Test Successful!!------------------")
    print("\n" * 3)
    print("###################################################")
    print("###################################################")
    print("###################################################")
    print("###################################################")

def cleanup_after_test_complete():
    print("\n" * 3)
    print("------------Initiating cleanup after test--------------")
    print("\n" * 3)
    delete_secrets()
    empty_s3_bucket()
    delete_unused_task_definitions()
    print("\n" * 3)
    print("------------Cleanup Complete!!--------------")
    print("\n" * 3)

run_e2e_test()
cleanup_after_test_complete()


