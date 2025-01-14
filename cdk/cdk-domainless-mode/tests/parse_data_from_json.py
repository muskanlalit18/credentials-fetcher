import json
import os

def load_data():
    with open('../data.json', 'r') as file:
        return json.load(file)

def get_value(key):
    return os.environ.get(key, data.get(key.lower()))

data = load_data()

number_of_gmsa_accounts = data["number_of_gmsa_accounts"]
netbios_name = data["netbios_name"]
directory_name = data["directory_name"]
instance_name = data["windows_instance_tag"]
region = data["aws_region"]
stack_name = data["stack_name"]
cluster_name = data["cluster_name"]
vpc_name = data["vpc_name"]
task_definition_template_name = data["task_definition_template_name"]
repository_name = data["ecr_repo_name"]
tag = data["docker_image_tag"]
bucket_name = get_value("S3_PREFIX") + data["s3_bucket_suffix"]
aws_profile_name = data["aws_profile_name"]
username = data["username"]
password = data["password"]
windows_instance_tag = data["ActiveDirectoryManagementInstance"]
domain_admin_password = data["domain_admin_password"]
