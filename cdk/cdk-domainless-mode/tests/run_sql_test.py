import boto3
import sys
from parse_data_from_json import stack_name, windows_instance_tag, region

"""
This script executes a shell script on the Linux instance via SSM that: 
a. Lists Docker containers 
b. Identifies a specific Docker container (my-ecr-repo:latest) 
c. If the container is found, runs 'klist' and a SQL query inside the container

This script validates that the Kerberos ticket can be used to access SQL server.

"""

def run_shell_script(instance_id, hostname):

    commands = [
        'systemctl restart credentials-fetcher',
        'systemctl restart ecs',
        f'HOSTNAME="{hostname}"',
        'echo "Listing all Docker containers:"',
        'IMAGEID=$(docker ps --format "{{.ID}}  {{.Image}}" | grep "my-ecr-repo:latest" | awk \'{print $1}\' | head -n 1)',
        'echo "IMAGEID: $IMAGEID"',
        'if [ -n "$IMAGEID" ]; then',
        '    echo "Container ID: $IMAGEID"',
        '    echo "Running commands inside the container:"',
        '    echo "klist && sqlcmd -S $HOSTNAME.contoso.com -C -Q \'SELECT * FROM employeesdb.dbo.employeestable;\'" | docker exec -i $IMAGEID env PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/mssql-tools/bin bash',
        '    SQL_EXIT_CODE=$?',
        '    echo "SQL_SUCCESS_MARKER: $SQL_EXIT_CODE"', 
        'else',
        '    echo "No container found with my-ecr-repo:latest"',
        'fi'
        ]
    ssm = boto3.client('ssm')

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': commands}
    )

    command_id = response['Command']['CommandId']

    waiter = ssm.get_waiter('command_executed')
    try:
        waiter.wait(
            CommandId=command_id,
            InstanceId=instance_id,
            WaiterConfig={
                'Delay': 30,
                'MaxAttempts': 100
            }
        )
    except Exception as e:
        print(f"Command failed: {commands}")
        print(f"Error: {str(e)}")
        raise

    output = ssm.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id
    )
    
    print(f"Command output:\n{output.get('StandardOutputContent', '')}")

    sql_success = False 

    if output['Status'] == 'Success':
        print(f"Command status: Success")
        # Look for the SQL success marker in the output
        output_content = output.get('StandardOutputContent', '')
        for line in output_content.splitlines():
            if line.startswith('SQL_SUCCESS_MARKER: '):
                exit_code = int(line.split(': ')[1])
                if exit_code == 0:
                    sql_success = True
                break
    else:
        print(f"Command failed with status: {output['Status']}")
        print(f"Error: {output.get('StandardErrorContent', 'No error content available')}")
        raise Exception(f"Command execution failed with status: {output['Status']}")
    
    return sql_success 
    
def get_windows_hostname(instance_id):
    commands = [
        'hostname'
        ]
    ssm = boto3.client('ssm')

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={'commands': commands}
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
        print(f"Command failed: {commands}")
        print(f"Error: {str(e)}")
        raise

    output = ssm.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id
    )
    
    print(f"Command output:\n{output.get('StandardOutputContent', '')}")

    if output['Status'] == 'Success':
        hostname = output['StandardOutputContent'].strip()
        return hostname
    else:
        print(f"Command failed with status: {output['Status']}")
        print(f"Error: {output.get('StandardErrorContent', 'No error content available')}")
        raise Exception(f"Command execution failed with status: {output['Status']}")

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


# instance_name_linux = stack_name + '/MyAutoScalingGroup'
# instance_name_windows = windows_instance_tag
# instance_id_linux = get_instance_id_by_name(region, instance_name_linux)
# instance_id_windows = get_instance_id_by_name(region, instance_name_windows)
#
# hostname = get_windows_hostname(instance_id_windows)
# run_shell_script(instance_id_linux, hostname)

