What this CDK does:
CDK automation to run Linux gMSA in ECS with EC2 instance in domainless mode . This CDK can be used to test RPMs for AL2023.

This CDK does the following:
Creates directory in Directory Service (Active Directory)
Launch Windows instance, domain-join with Active Directory and create gMSA accounts
Create ECS cluster
Launch ECS-optimized Linux instance and attaches to ECS cluster
Runs a couple of tasks in the ECS-optimized Linux instance using gMSA in domainless mode.

Disclaimer
This CDK and scripts are only for test, please modify as needed.

Create the following environment variables: 
1. AWS_REGION
2. S3_PREFIX
3. KEY_PAIR_NAME
4. PREFIX_LIST

Pre-requisites
Please take a look at data.json for default values.
If you're testing a new RPM, upload it in the S3 bucket.
Ensure you have docker running in the background.
1) Create secret in Secrets Manager as per https://docs.aws.amazon.com/AmazonECS/latest/developerguide/linux-gmsa.html#linux-gmsa-setup with the following values:
   This is the same secret in data.json.
   ```
    Secret key  Secret value
    username    StandardUser01
    password    p@ssw0rd
    domainName  contoso.com
    ```
2) 'default' AWS profile with administrator access is needed, a separate/burner AWS account would suffice.

Steps to run tasks in ECS with Credentials-fetcher.

3) Create a virtual env
        Go to cdk directory

        ```
        $ cd cdk/
        ```
        To manually create a virtualenv on MacOS and Linux:

        ```
        $ python3 -m venv .venv
        ```

        After the init process completes and the virtualenv is created, you can use the following
        step to activate your virtualenv.

        ```
        $ source .venv/bin/activate
        ```

        Once the virtualenv is activated, you can install the required dependencies.

        ```
        $ pip install -r requirements.txt
        ```

        Install AWS cdk

        ```
        $ brew install aws-cdk
        ```

5) Run start_stack.sh (this is a bash script) to create a CloudFormation stack
   2.1) Update start_stack.sh with your aws account number

   2.2) This creates Managed Active Directory, launches Windows instance and domain-joins it and creates the gMSA accounts, launches an ECS-optimized Linux instance, creates a new ECS cluster and attaches it to ECS cluster.
    ```
    (.venv) cdk % ./start_stack.sh
        [10:29:46] CDK toolkit version: 2.156.0 (build 2966832)
        [10:29:46] Command line arguments: {
        _: [ 'bootstrap' ],
    ```

7) Run copy_credspecs_and_create_task_defs.py to create and copy credspecs to S3 bucket and also to register ECS task definitions.
    ```
     (.venv) cdk % python3 copy_credspecs_and_create_task_defs.py
     
    ```
8) Run the following scripts in order to setup the windows instance and update inbound rules of the security group
    ```
        (.venv) cdk % python3 setup_windows_instance.py
        (.venv) cdk % python3 update_inbound_rules.py
    ```

9) After CloudFormation stack is complete, update and run tasks using update_task_def_and_run_tasks.py. (You can install a test RPM into the ECS intance here, if you like)
    ```
        (.venv) cdk % python3 update_task_def_and_run_tasks.py
    ```

10) For the final check that the container is able to access SQL using the Kerberos ticket, run run_sql_test.py
    ```
        (.venv) cdk % python3 run_sql_test.py
    ```

11) Done: If everything worked as expected, you should see an output like this in the console:
    ```
            EmpID EmpName Designation DepartmentJoiningDate
    ----------- -------------------------------------------------- -------------------------------------------------- -------------------------------------------------------------------------
    1 CHIN YEN LAB ASSISTANT LAB2022-03-05 03:57:09.967
    2 MIKE PEARL SENIOR ACCOUNTANT ACCOUNTS2022-03-05 03:57:09.967
    3 GREEN FIELD ACCOUNTANT ACCOUNTS2022-03-05 03:57:09.967
    4 DEWANE PAUL PROGRAMMER IT2022-03-05 03:57:09.967
    5 MATTS SR. PROGRAMMER IT2022-03-05 03:57:09.967
    6 PLANK OTO ACCOUNTANT ACCOUNTS2022-03-05 03:57:09.967

    (6 rows affected)
    ```



