
# This script does the following:
# 1) Install/Update SSM agent - without this the domain-join can fail
# 2) Create a new OU
# 3) Create a new security group
# 4) Create a new standard user account, this account's username and password needs to be stored in a secret store like AWS secrets manager.
# 5) Add members to the security group that is allowed to retrieve gMSA password
# 6) Create gMSA accounts with PrincipalsAllowedToRetrievePassword set to the security group created in 4)

# 1) Install SSM agent
function Test-SSMAgentUpdate {
    $ssm = Get-Service -Name "AmazonSSMAgent" -ErrorAction SilentlyContinue
    if (-not $ssm) { return $false }
    # Add additional version checking logic if needed
    return $true
}

# To install the AD module on Windows Server, run Install-WindowsFeature RSAT-AD-PowerShell
# To install the AD module on Windows 10 version 1809 or later, run Add-WindowsCapability -Online -Name 'Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0'
# To install the AD module on older versions of Windows 10, see https://aka.ms/rsat
try {
# 1) Check and Update SSM agent if needed
    if (-not (Test-SSMAgentUpdate)) {
        Write-Output "Updating SSM agent..."
        [System.Net.ServicePointManager]::SecurityProtocol = 'TLS12'
        $progressPreference = 'silentlyContinue'
        Invoke-WebRequest https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe -OutFile $env:USERPROFILE\Desktop\SSMAgent_latest.exe
        Start-Process -FilePath $env:USERPROFILE\Desktop\SSMAgent_latest.exe -ArgumentList "/S"
    }

# Check if AD tools are installed
    if (-not (Get-WindowsFeature -Name "RSAT-AD-Tools").Installed) {
        Write-Output "Installing Active Directory management tools..."
        Install-WindowsFeature -Name "RSAT-AD-Tools" -IncludeAllSubFeature
        Install-WindowsFeature RSAT-AD-PowerShell
        Install-Module CredentialSpec -Force
        Install-Module -Name SqlServer -AllowClobber -Force
    }

    $username = "admin@DOMAINNAME"
    $password = "INPUTPASSWORD" | ConvertTo-SecureString -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential($username, $password)
    $groupAllowedToRetrievePassword = "WebAppAccounts_OU"
    # This is the basedn path that needs to be in secrets manager as "distinguishedName" :  "OU=MYOU,OU=Users,OU=ActiveDirectory,DC=contoso,DC=com"
    $path = "OU=MYOU,OU=Users,OU=contoso,DC=NETBIOS_NAME,DC=com"

    # 2) Create OU if it doesn't exist
    if (-not (Get-ADOrganizationalUnit -Filter "Name -eq 'MYOU'" -ErrorAction SilentlyContinue)) {
        New-ADOrganizationalUnit -Name "MYOU" -Path "OU=Users,OU=contoso,DC=NETBIOS_NAME,DC=com" -Credential $credential
    }

    # 3) Create security group if it doesn't exist
    if (-not (Get-ADGroup -Filter "SamAccountName -eq '$groupAllowedToRetrievePassword'" -ErrorAction SilentlyContinue)) {
        New-ADGroup -Name "WebApp Authorized Accounts in OU" -SamAccountName $groupAllowedToRetrievePassword -Credential $credential -GroupScope DomainLocal -Server DOMAINNAME
    }

    # 4) Create standard user if it doesn't exist
    if (-not (Get-ADUser -Filter "SamAccountName -eq 'StandardUser01'" -ErrorAction SilentlyContinue)) {
        New-ADUser -Name "StandardUser01" -AccountPassword (ConvertTo-SecureString -AsPlainText "********" -Force) -Enabled 1 -Credential $credential -Path $path -Server DOMAINNAME
    }

    # 5) Add members to security group if not already members
    $group = Get-ADGroup $groupAllowedToRetrievePassword
    $members = Get-ADGroupMember $group | Select-Object -ExpandProperty SamAccountName

    foreach ($member in @("StandardUser01", "admin")) {
        if ($member -notin $members) {
            Add-ADGroupMember -Identity $groupAllowedToRetrievePassword -Members $member -Credential $credential -Server DOMAINNAME
        }
    }

    # 6) Create gMSA accounts if they don't exist
    for (($i = 1); $i -le $NUMBER_OF_GMSA_ACCOUNTS; $i++) {
        $gmsa_account_name = "WebApp0" + $i
        $gmsa_account_with_domain = $gmsa_account_name + ".DOMAINNAME"
        $gmsa_account_with_host = "host/" + $gmsa_account_name
        $gmsa_account_with_host_and_domain = $gmsa_account_with_host + ".DOMAINNAME"

        if (-not (Get-ADServiceAccount -Filter "Name -eq '$gmsa_account_name'" -ErrorAction SilentlyContinue)) {
            New-ADServiceAccount -Name $gmsa_account_name `
                                           -DnsHostName $gmsa_account_with_domain `
                                           -ServicePrincipalNames $gmsa_account_with_host, $gmsa_account_with_host_and_domain `
                                           -PrincipalsAllowedToRetrieveManagedPassword $groupAllowedToRetrievePassword `
                                           -Path $path `
                                           -Credential $credential `
                                           -Server DOMAINNAME
        }
    }

    # SQL Server Configuration
    $sqlInstance = $env:computername

    # Create firewall rules if they don't exist
    $firewallRules = Get-NetFirewallRule | Select-Object -ExpandProperty DisplayName

    if ("SQLServer default instance" -notin $firewallRules) {
        New-NetFirewallRule -DisplayName "SQLServer default instance" -Direction Inbound -LocalPort 1433 -Protocol TCP -Action Allow
    }
    if ("SQLServer Browser service" -notin $firewallRules) {
        New-NetFirewallRule -DisplayName "SQLServer Browser service" -Direction Inbound -LocalPort 1434 -Protocol UDP -Action Allow
    }
    if ("AllowRDP" -notin $firewallRules) {
        New-NetFirewallRule -DisplayName "AllowRDP" -Direction Inbound -Protocol TCP -LocalPort 3389 -Action Allow
    }
    if ("AllowSQLServer" -notin $firewallRules) {
        New-NetFirewallRule -DisplayName "AllowSQLServer" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow
    }

    # SQL Database creation and configuration
    $connectionString0 = "Server=$sqlInstance;Integrated Security=True;"
    $connectionString1 = "Server=$sqlInstance;Database=EmployeesDB;Integrated Security=True;"

    # Check if database exists
    $dbExists = Invoke-Sqlcmd -ConnectionString $connectionString0 -Query "SELECT name FROM sys.databases WHERE name = 'EmployeesDB'"

    if (-not $dbExists) {
        Invoke-Sqlcmd -ConnectionString $connectionString0 -Query "CREATE DATABASE EmployeesDB"

        $query = @"
CREATE TABLE dbo.EmployeesTable (
    EmpID INT IDENTITY(1,1) PRIMARY KEY,
    EmpName VARCHAR(50) NOT NULL,
    Designation VARCHAR(50) NOT NULL,
    Department VARCHAR(50) NOT NULL,
    JoiningDate DATETIME NOT NULL
);

INSERT INTO EmployeesDB.dbo.EmployeesTable (EmpName, Designation, Department, JoiningDate)
VALUES
    ('CHIN YEN', 'LAB ASSISTANT', 'LAB', '2022-03-05 03:57:09.967'),
    ('MIKE PEARL', 'SENIOR ACCOUNTANT', 'ACCOUNTS', '2022-03-05 03:57:09.967'),
    ('GREEN FIELD', 'ACCOUNTANT', 'ACCOUNTS', '2022-03-05 03:57:09.967'),
    ('DEWANE PAUL', 'PROGRAMMER', 'IT', '2022-03-05 03:57:09.967'),
    ('MATTS', 'SR. PROGRAMMER', 'IT', '2022-03-05 03:57:09.967'),
    ('PLANK OTO', 'ACCOUNTANT', 'ACCOUNTS', '2022-03-05 03:57:09.967');
alter authorization on database::[EmployeesDB] to [WebApp01$]
"@

        Invoke-Sqlcmd -ConnectionString $connectionString1 -Query $query
    }

    # Check if login exists before creating
    $loginExists = Invoke-Sqlcmd -ConnectionString $connectionString0 -Query "SELECT name FROM sys.server_principals WHERE name = 'NETBIOS_NAME\webapp01$'"

    if (-not $loginExists) {
        $createLoginQuery = "CREATE LOGIN [NETBIOS_NAME\webapp01$] FROM WINDOWS WITH DEFAULT_DATABASE = [master], DEFAULT_LANGUAGE = [us_english]; EXEC sp_addrolemember 'db_owner', 'NETBIOS_NAME\webapp01$';"
        Invoke-Sqlcmd -ConnectionString $connectionString0 -Query $createLoginQuery
    }

} catch {
    Write-Error "An error occurred: $_"
    throw
}