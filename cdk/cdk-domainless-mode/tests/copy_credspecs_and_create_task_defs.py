import boto3
import json
import os

def setup_aws_session(aws_profile_name):
    boto3.setup_default_session(profile_name=aws_profile_name)

def get_ecs_task_execution_role_arn():
    iam_client = boto3.client('iam')
    list_roles = iam_client.list_roles(MaxItems=1000)
    for role in list_roles['Roles']:
        if 'CredentialsFetcher-ECSTaskExecutionRolegMSA' == role['RoleName']:
            return role['Arn']
    return None

def get_task_definition_template(ecs_client, task_definition_template_name):
    response = ecs_client.list_task_definitions()
    if 'taskDefinitionArns' in response:
        for arn in response['taskDefinitionArns']:
            if task_definition_template_name in arn:
                return ecs_client.describe_task_definition(taskDefinition=arn)
    print(f"No task definitions found matching '{task_definition_template_name}'")
    return None

def get_ecs_cluster_info(ecs_client, ecs_cluster_name):
    ecs_clusters = ecs_client.list_clusters()
    for cluster_arn in ecs_clusters['clusterArns']:
        cluster_name = cluster_arn.split('/')[1]
        if cluster_name == ecs_cluster_name:
            ecs_cluster_instance_arn = ecs_client.list_container_instances(cluster=cluster_arn)['containerInstanceArns'][0]
            return cluster_arn, ecs_cluster_instance_arn
    return None, None

def create_credspec(directory_name, netbios_name, gmsa_name, gmsa_secret_arn):
    credspec_template = """
    {
      "CmsPlugins": ["ActiveDirectory"],
      "DomainJoinConfig": {
        "Sid": "S-1-5-21-2421564706-1737585382-3854682907",
        "MachineAccountName": "GMSA_NAME",
        "Guid": "6a91814c-e151-4fb0-96f0-f517566fc883",
        "DnsTreeName": "DOMAINNAME",
        "DnsName": "DOMAINNAME",
        "NetBiosName": "NETBIOS_NAME"
      },
      "ActiveDirectoryConfig": {
        "GroupManagedServiceAccounts": [
          {
            "Name": "GMSA_NAME",
            "Scope": "DOMAINNAME"
          },
          {
            "Name": "GMSA_NAME",
            "Scope": "NETBIOS_NAME"
          }
        ],
        "HostAccountConfig": {
          "PortableCcgVersion": "1",
          "PluginGUID": "{859E1386-BDB4-49E8-85C7-3070B13920E1}",
          "PluginInput": {
            "CredentialArn": "GMSA_SECRET_ARN"
          }
        }
      }
    }
    """
    credspec_template = credspec_template.replace("DOMAINNAME", directory_name)
    credspec_template = credspec_template.replace("NETBIOS_NAME", netbios_name)
    credspec_template = credspec_template.replace("GMSA_NAME", gmsa_name)
    credspec_template = credspec_template.replace("GMSA_SECRET_ARN", gmsa_secret_arn)
    return json.loads(credspec_template)

def upload_credspec_to_s3(s3_client, s3_bucket, gmsa_name, credspec):
    s3_key = f"{gmsa_name}_credspec.json"
    try:
        s3_client.put_object(Body=json.dumps(credspec), Bucket=s3_bucket, Key=s3_key)
        bucket_location = s3_client.get_bucket_location(Bucket=s3_bucket)
        bucket_arn = f"arn:aws:s3:::{s3_bucket}"
        return bucket_arn, s3_key
    except Exception as e:
        print(f"Error uploading credspec to S3: {e}")
        return None, None

def modify_task_definition(task_definition, ecs_cluster_arn, bucket_arn, s3_key):
    task_definition = task_definition["taskDefinition"]
    task_definition["compatibilities"].append("FARGATE")

    for container_def in task_definition['containerDefinitions']:
        container_def['credentialSpecs']=[]
        credspec = container_def['credentialSpecs']
        credspec = [d for d in credspec if 'credentialspecdomainless' not in d]
        credspec.append(f"credentialspecdomainless:{bucket_arn}/{s3_key}")
        container_def['credentialSpecs'] = credspec

    attributes = task_definition['requiresAttributes']
    attributes.append({
        "name": "ecs.capability.gmsa-domainless",
        "targetId": ecs_cluster_arn
    })

    return task_definition

def register_new_task_definition(ecs_client, task_definition, family, ecs_task_execution_role_arn):
    return ecs_client.register_task_definition(
        family=family,
        taskRoleArn=ecs_task_execution_role_arn,
        executionRoleArn=ecs_task_execution_role_arn,
        networkMode=task_definition['networkMode'],
        containerDefinitions=task_definition['containerDefinitions'],
        requiresCompatibilities=["EC2", "FARGATE"],
        runtimePlatform={'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'},
        cpu=task_definition['cpu'],
        memory=task_definition['memory']
    )
