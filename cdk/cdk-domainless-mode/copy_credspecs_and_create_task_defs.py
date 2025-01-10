import boto3
import json
import os

"""
ECS Task Definition and gMSA Credential Spec Generator

This script performs the following operations:

1. Generates gMSA credential specs for a specified number of accounts.
2. Uploads the generated credential specs to an S3 bucket.
3. Retrieves an existing ECS task definition template.
4. Modifies the task definition for each gMSA account:
   - Adds Fargate compatibility
   - Updates the credential specs to use the newly generated ones
   - Adds the gMSA domainless capability
5. Registers new task definitions for each gMSA account based on the modified template.

It's designed to automate the process of setting up ECS tasks with gMSA authentication 
for multiple accounts in an Active Directory environment.

"""

# Open the input file
with open('data.json', 'r') as file:
    # Load the JSON data
    data = json.load(file)

def get_value(key):
    return os.environ.get(key, data.get(key.lower()))

directory_name = data["directory_name"]
netbios_name = data["netbios_name"]
number_of_gmsa_accounts = data["number_of_gmsa_accounts"]
s3_bucket = get_value("S3_PREFIX") + data["s3_bucket_suffix"]
task_definition_template_name = data["task_definition_template_name"]
stack_name = data["stack_name"]
max_tasks = data["max_tasks_per_instance"]

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

secrets_manager_client = boto3.client('secretsmanager')
secret_id = "aws/directoryservice/" + netbios_name + "/gmsa"
# get secrets manager arn from secret name
print("Secret id = " + secret_id)
gmsa_secret_arn = secrets_manager_client.get_secret_value(SecretId=secret_id)['ARN']
credspec_template = credspec_template.replace("GMSA_SECRET_ARN", gmsa_secret_arn)

aws_profile_name = data["aws_profile_name"]

boto3.setup_default_session(profile_name=aws_profile_name)

# list iam roles with a given name
list_roles = boto3.client('iam').list_roles(MaxItems=1000)
for role in list_roles['Roles']:
    print(role['RoleName'])
for role in list_roles['Roles']:
    role_name = role['RoleName']
    if 'CredentialsFetcher-ECSTaskExecutionRolegMSA' == role_name:
        ecs_task_execution_role_arn = role['Arn']
        break

# list ECS task definitions
ecs_client = boto3.client('ecs')

# task_definition_prefix = 'ecs-task-definition'
# Call the list_task_definitions method with a prefix filter

task_definition_arn = ""
task_definition = ""
response = ecs_client.list_task_definitions()
# Check if any task definitions match the prefix
if 'taskDefinitionArns' in response:
    task_definitions = response['taskDefinitionArns']
    if task_definitions == []:
        print("No task definitions found")
        exit()
    for arn in task_definitions:
        if task_definition_template_name in arn:
            matching_task_definitions = arn
            # Get task definition details
            task_definition = ecs_client.describe_task_definition(taskDefinition=arn)
            task_definition_arn = arn
            break
else:
    print(f"No task definitions found matching '{response}'")
    exit()

# Get ecs cluster
ecs_clusters = ecs_client.list_clusters()
ecs_cluster_arn = ""
ecs_cluster_instance = ""
ecs_cluster_name = "Credentials-fetcher-ecs-load-test"
for cluster_arn in ecs_clusters['clusterArns']:
    cluster_name = cluster_arn.split('/')[1]
    if cluster_name == ecs_cluster_name:
        ecs_cluster_arn = cluster_arn
        # Get instance-id attached running ecs cluster
        ecs_cluster_instance_arn = ecs_client.list_container_instances(cluster=ecs_cluster_arn)['containerInstanceArns'][0]
        break

credspecs = []
for i in range(1, number_of_gmsa_accounts+1):
    credspec_template_copy = credspec_template.replace("GMSA_NAME", f"WebApp0{i}")
    credspec = json.loads(credspec_template_copy)
    credspec_str = json.dumps(credspec)
    
    # Copy credspec to S3 folder
    s3_client = boto3.client('s3')
    bucket_location = ""
    bucket_arn = ""
    s3_key = ""
    try:
        s3_key = f"WebApp0{i}_credspec.json"
        print(f"Putting object: {s3_key}")
        s3_client.put_object(Body=credspec_str, Bucket=s3_bucket, Key=s3_key)
        bucket_location = s3_client.get_bucket_location(Bucket=s3_bucket)
        bucket_arn = f"arn:aws:s3:::{s3_bucket}"
        credspecs.append(f"credentialspecdomainless:{bucket_arn}/{s3_key}")
    except Exception as e:
        print(e)

task_definition_orig = task_definition
for i in range(1, max_tasks + 1):
    task_definition = task_definition_orig
    #print(task_defnition)
    task_definition = task_definition["taskDefinition"]
    task_definition["compatibilities"].append("FARGATE")

    container_defs = []
    for j in range(1, 11):
        container_def = task_definition['containerDefinitions'][0].copy()  # Use the first container as a template
        container_def['name'] = f"MyContainer{j}"
        container_def['credentialSpecs'] = [credspecs[j-1]]  # Use the corresponding credspec
        container_defs.append(container_def)
    pretty_json = json.dumps(container_defs, indent=4)
    print(pretty_json)
    attributes = task_definition['requiresAttributes']
    attribute = {}
    attribute["name"] = "ecs.capability.gmsa-domainless"
    attribute["targetId"] = ecs_cluster_arn
    attributes.append(attribute)
    family = task_definition['family'] + "-" + str(i)
    ecs_client.register_task_definition(family=family, 
                                    taskRoleArn=ecs_task_execution_role_arn,
                                    executionRoleArn=ecs_task_execution_role_arn,
                                    networkMode=task_definition['networkMode'],
                                    containerDefinitions=container_defs,
                                    requiresCompatibilities=["EC2", "FARGATE"],
                                    runtimePlatform={'cpuArchitecture': 'X86_64', 'operatingSystemFamily' : 'LINUX'},
                                    cpu=task_definition['cpu'],
                                    memory=task_definition['memory'])
    #print(ecs_cluster_arn)

