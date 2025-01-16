# Use this script to create new Domain Joined gMSA accounts and add them to
# the AD. This script is run on the Windows Instance with access to Managed AD.

$username = "admin@CONTOSO.COM"
$password = "Qn:51eJsORJNL@~{HY@?" | ConvertTo-SecureString -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($username, $password)

$groupAllowedToRetrievePassword = "WebAppAccounts_OU"
$path = "OU=MYOU,OU=Users,OU=contoso,DC=contoso,DC=com"

for (($i = 1); $i -le 10;$i++)
{
    # Create the gMSA account
    $gmsa_account_name = "DJ_WebApp0" + $i
    $gmsa_account_with_domain = $gmsa_account_name + "." + $env:USERDNSDOMAIN
    $gmsa_account_with_host = "host/" + $gmsa_account_name
    $gmsa_account_with_host_and_domain = $gmsa_account_with_host + "." + $env:USERDNSDOMAIN

    try {
        New-ADServiceAccount -Name $gmsa_account_name `
                             -DnsHostName $gmsa_account_with_domain `
                             -ServicePrincipalNames $gmsa_account_with_host, $gmsa_account_with_host_and_domain `
                             -PrincipalsAllowedToRetrieveManagedPassword $groupAllowedToRetrievePassword `
                             -Path $path `
                             -Credential $credential `
                             -Server $env:USERDNSDOMAIN `
                             -KerberosEncryptionType AES256
        Write-Output "Created gMSA account: $gmsa_account_name"
    } catch {
        $string_err = $_ | Out-String
        Write-Output "Error while gMSA account creation: " + $string_err
    }
}